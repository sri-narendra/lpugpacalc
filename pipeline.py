"""Orchestration: login -> fetch -> process -> display."""
import re
import sys
import json
import requests
from bs4 import BeautifulSoup
from utils import (
    get_page_with_turnstile, parse_form_fields, login,
    call_api, fetch_credits_from_api, BASE,
)


def login_flow(sess: requests.Session, userid: str, password: str) -> bool:
    html = get_page_with_turnstile()
    fields = parse_form_fields(html)
    if not fields.get('turnstile_token') or not fields.get('password_field'):
        print("Error: Turnstile token or password field not found", file=sys.stderr)
        return False
    return login(sess, userid, password, fields)


def fetch_dashboard_data(sess: requests.Session, userid: str) -> dict:
    raw = {}
    api_base = BASE + "StudentDashboard.aspx/"
    endpoints = {
        'profile': api_base + 'GetStudentBasicInformation',
        'marks': api_base + 'TermWiseCGPA',
    }
    for key, url in endpoints.items():
        try:
            raw[key] = call_api(sess, url)
        except Exception as e:
            print(f"  [FAIL] {key}: {e}", file=sys.stderr)
    print(f"  Fetching course credits via API...", file=sys.stderr)
    raw['credit_map'] = fetch_credits_from_api(sess, userid)
    print(f"  Credits fetched: {len(raw['credit_map'])} courses", file=sys.stderr)
    return raw


def process_dashboard_data(raw: dict) -> dict:
    result = {}

    profile_raw = raw.get('profile', '')
    parsed_profile = parse_profile(profile_raw)
    result['profile'] = extract_profile_fields(parsed_profile) if isinstance(parsed_profile, dict) else {}

    marks_raw = raw.get('marks', '')
    result['marks'] = parse_term_cgpa(marks_raw)

    credit_map = raw.get('credit_map', {})
    if credit_map and result['marks'].get('terms'):
        matched = 0; total = 0
        for term in result['marks']['terms']:
            for course in term.get('courses', []):
                total += 1
                parts = course['name'].split('::')
                code = parts[0].strip() if len(parts) > 1 else course['name'].strip().split()[0] if course['name'].strip() else ''
                if code not in credit_map:
                    code = ''.join(filter(str.isalnum, course['name'].split()[0])) if course['name'].strip() else ''
                cr = credit_map.get(code, 4)
                if cr != 4:
                    matched += 1
                course['credits'] = cr
        print(f"  [DEBUG] matched {matched}/{total} courses with credit_map", file=sys.stderr)

    total_weighted = 0.0
    total_credits = 0
    for term in result['marks'].get('terms', []):
        term_credits = sum(c.get('credits', 0) for c in term.get('courses', []))
        tgpa = float(term.get('tgpa') or 0)
        if tgpa and term_credits:
            total_weighted += tgpa * term_credits
            total_credits += term_credits
    if total_credits > 0:
        result['marks']['cgpa'] = round(total_weighted / total_credits, 2)
    else:
        result['marks']['cgpa'] = None

    return result


def print_dashboard_report(data: dict) -> None:
    print("\n" + "=" * 60)
    print("PROFILE")
    print("=" * 60)
    p = data.get('profile', {})
    for k, v in p.items():
        if v:
            print(f"  {k.replace('_', ' ').title()}: {v}")

    print("\n" + "=" * 60)
    print("MARKS (TERM-WISE)")
    print("=" * 60)
    m = data.get('marks', {})
    if m.get('cgpa'):
        print(f"  CGPA: {m['cgpa']}")
    for term in m.get('terms', []):
        print(f"\n  {term['term']} -- TGPA: {term.get('tgpa', 'N/A')}")
        print(f"  {'-' * 50}")
        for c in term.get('courses', []):
            print(f"    {c['name'][:42]:<44} {c['grade']}")


def parse_term_cgpa(html_text: str) -> dict:
    """Parse TermWiseCGPA HTML response into structured data."""
    if not html_text:
        return {'terms': [], 'total_courses': 0}
    soup = BeautifulSoup(html_text, 'html.parser')
    term_headers = soup.find_all('div', class_=lambda c: c and 'row' in c and 'mt-2' in c)
    tables = soup.find_all('table')
    terms = []
    for i, header in enumerate(term_headers):
        h4s = header.find_all('h4')
        term_name = ''
        tgpa = ''
        for h4 in h4s:
            t = h4.get_text(strip=True)
            m = re.match(r'Term\s*:\s*(\w+)', t)
            if m:
                term_name = m.group(1)
            m = re.match(r'TGPA\s*:\s*([\d.]+)', t)
            if m:
                tgpa = m.group(1)
        courses = []
        if i < len(tables):
            for tr in tables[i].find_all('tr')[1:]:
                tds = tr.find_all('td')
                if len(tds) >= 2:
                    course_name = tds[0].get_text(strip=True)
                    grade_text = tds[1].get_text(strip=True)
                    g = re.search(r'Grade\s*:\s*(\S+)', grade_text)
                    grade = g.group(1) if g else grade_text
                    if course_name:
                        courses.append({'name': course_name, 'grade': grade})
        if term_name:
            terms.append({
                'term': f"Term {term_name}",
                'term_num': term_name,
                'tgpa': tgpa,
                'courses': courses,
            })
    total = sum(len(t['courses']) for t in terms)
    return {'terms': terms, 'total_courses': total, 'cgpa': None}


def parse_courses(html_text: str) -> list[dict]:
    """Parse GetStudentCourses response into a list of course dicts."""
    if not html_text:
        return []
    soup = BeautifulSoup(html_text, 'html.parser')
    courses = []
    for div in soup.find_all('div', class_='mycoursesdiv'):
        pct_div = div.find('div', class_='c100')
        pct = ''
        if pct_div:
            span = pct_div.find('span')
            if span:
                pct = span.get_text(strip=True)
        name_divs = div.find_all('div',
                                  class_=lambda c: c and 'font-weight-medium' in c)
        name = ''
        for nd in name_divs:
            t = nd.get_text(strip=True)
            if t and len(t) > 3:
                name = t
                break
        if name:
            courses.append({'name': name, 'attendance_pct': pct})
    return courses


def parse_profile(raw_data):
    """Parse GetStudentBasicInformation response (JSON list or dict)."""
    if not raw_data:
        return {}
    if isinstance(raw_data, list):
        return raw_data[0] if raw_data else {}
    if isinstance(raw_data, str):
        try:
            data = json.loads(raw_data)
            if isinstance(data, list):
                return data[0] if data else {}
            return data
        except (json.JSONDecodeError, TypeError):
            pass
    return raw_data


def extract_profile_fields(profile: dict) -> dict:
    """Extract readable fields from profile dict."""
    if not profile:
        return {}
    return {
        'reg_no': profile.get('Registrationnumber') or profile.get('RegistrationNo') or '',
        'program': profile.get('Program', ''),
        'section': profile.get('Section', ''),
        'batch': profile.get('BatchYear') or profile.get('Batch') or '',
        'admission_session': profile.get('AdmissionSession', ''),
        'student_name': profile.get('StudentName') or profile.get('Name') or '',
        'email': profile.get('Email') or profile.get('EmailId') or '',
        'phone': profile.get('PhoneNo') or profile.get('Mobile') or '',
        'profile_image': profile.get('StudentPicture', ''),
    }
