"""Orchestration: login -> fetch -> process -> display."""
import re
import sys
import json
import os
import time
import glob
import subprocess
from bs4 import BeautifulSoup
from utils import (
    fetch_login_page, parse_form_fields, login,
    call_api, fetch_credits_from_api, BASE,
    _emit_progress, import_cookies_to_session,
)

LOGIN_URL = "https://ums.lpu.in/lpuums/"


def _find_playwright_chromium() -> str | None:
    """Find Playwright's bundled Chromium binary for undetected_chromedriver."""
    project_dir = os.path.dirname(os.path.abspath(__file__))
    known = [
        os.path.join(project_dir, ".pw-browsers", "chromium-*", "chrome-*", "chrome"),
        os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-*/chrome"),
        "/opt/render/.cache/ms-playwright/chromium-*/chrome-*/chrome",
        "/root/.cache/ms-playwright/chromium-*/chrome-*/chrome",
    ]
    for pattern in known:
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[0]
    pw_root = os.path.join(project_dir, ".pw-browsers")
    if os.path.isdir(pw_root):
        for root, _dirs, files in os.walk(pw_root):
            if "chrome" in files:
                return os.path.join(root, "chrome")
    return None


def login_via_browser(userid: str, password: str) -> tuple[list[dict], str]:
    """Login using undetected_chromedriver to bypass Turnstile.

    Launches Chrome via undetected_chromedriver (which patches ChromeDriver
    to avoid bot detection). Turnstile auto-executes in this environment
    because Chrome appears as a real browser.

    Returns (cookies, dashboard_html) on success.
    Raises RuntimeError on failure.
    """
    display = None
    try:
        from pyvirtualdisplay import Display
        display = Display(visible=False, size=(1280, 720))
        display.start()
        print("  [XVFB] Virtual display started", file=sys.stderr)
    except Exception:
        pass

    driver = None
    try:
        _emit_progress('turnstile', 'Launching browser for Turnstile…', 10)
        import undetected_chromedriver as uc
        chrome_path = os.environ.get('CHROME_PATH') or _find_playwright_chromium()
        if chrome_path:
            print(f"  [CHROME] Using: {chrome_path}", file=sys.stderr)
        else:
            print("  [CHROME] No Chrome found, letting uc auto-detect", file=sys.stderr)
        driver = uc.Chrome(
            headless=False,
            use_subprocess=True,
            driver_executable_path=os.environ.get('CHROMEDRIVER_PATH'),
            browser_executable_path=chrome_path,
        )
        _emit_progress('turnstile', 'Browser launched, loading LPU UMS…', 20)
        driver.get(LOGIN_URL)

        token = None
        for i in range(30):
            time.sleep(1)
            token = driver.execute_script("""
                const el = document.querySelector(
                    'input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]'
                );
                return el ? el.value : '';
            """)
            if token and len(token) > 20:
                print(f"  [TURNSTILE] Token obtained at {i+1}s (len={len(token)})",
                      file=sys.stderr)
                _emit_progress('turnstile', 'Turnstile solved!', 50)
                break

        if not token or len(token) < 20:
            raise RuntimeError(
                f"Turnstile token not obtained after 30s (got len={len(token or '')})"
            )

        _emit_progress('turnstile', 'Logging in…', 60)
        driver.execute_script("""
            document.querySelectorAll(
                '.swal2-container, .swal2-overlay, .modal-backdrop'
            ).forEach(el => el.remove());
            document.body.style.overflow = 'auto';
        """)
        time.sleep(0.5)

        driver.execute_script("""
            document.querySelector('input[name="txtU"]').value = arguments[0];
            document.querySelector('input[type="password"]').value = arguments[1];
        """, userid, password)

        submit_name = driver.execute_script(
            "return document.querySelector('input[type=\"submit\"]').name;"
        )
        driver.execute_script(f"__doPostBack('{submit_name}', '');")

        for i in range(15):
            time.sleep(1)
            if 'studentdashboard' in driver.current_url.lower():
                break

        if 'studentdashboard' not in driver.current_url.lower():
            msg = driver.execute_script("""
                const swal = document.querySelector('.swal2-html-container');
                return swal ? swal.innerText : '';
            """)
            raise RuntimeError(f"Login failed: {msg or 'unknown error'}")

        _emit_progress('turnstile', 'Login successful! Transferring session…', 80)
        cookies = driver.get_cookies()
        html = driver.page_source
        return cookies, html

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        if display:
            try:
                display.stop()
            except Exception:
                pass


def login_flow(sess, userid: str, password: str) -> bool:
    """Log in to LPU UMS.

    Tries browser-based login first (bypasses Turnstile via
    undetected_chromedriver). Falls back to stateless curl_cffi if
    the browser isn't available.
    """
    # Try browser-based login (bypasses Turnstile)
    try:
        cookies, html = login_via_browser(userid, password)
        import_cookies_to_session(sess, cookies)
        _emit_progress('turnstile', 'Session transferred to API client', 90)
        return True
    except Exception as e:
        print(f"  [BROWSER] Login failed: {e}", file=sys.stderr)

    _emit_progress('turnstile', 'Falling back to curl_cffi (no Turnstile)…', 5)
    try:
        resp = sess.get(LOGIN_URL, timeout=30)
        html = resp.text
        if not html or len(html) < 100:
            raise ValueError(f"too short ({len(html or '')} chars)")
        print(f"  [FETCH] session: {len(html)} chars, status={resp.status_code}",
              file=sys.stderr)
    except Exception as e:
        print(f"  [FETCH] session failed: {e}, falling back to stateless fetch",
              file=sys.stderr)
        html = fetch_login_page()
    _emit_progress('turnstile', f'Got login page ({len(html)} chars)', 40)

    fields = parse_form_fields(html)
    if not fields.get('password_field'):
        print("Error: password field not found in login page", file=sys.stderr)
        return False
    return login(sess, userid, password, fields)


def fetch_dashboard_data(sess, userid: str) -> dict:
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
    try:
        raw['credit_map'] = fetch_credits_from_api(sess, userid)
        print(f"  Credits fetched: {len(raw['credit_map'])} courses", file=sys.stderr)
    except Exception as e:
        print(f"  [FAIL] credits: {e}", file=sys.stderr)
        raw['credit_map'] = {}
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
