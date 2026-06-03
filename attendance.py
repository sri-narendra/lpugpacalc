"""Attendance data fetching and parsing."""
from bs4 import BeautifulSoup

API_SUMMARY = "StudentDashboard.aspx/StudentAttendanceSummary"
API_DETAIL = "StudentDashboard.aspx/StudentAttendanceDetail"


def parse_summary(html_text: str) -> list[dict]:
    """Parse attendance summary HTML into a list of dicts."""
    if not html_text:
        return []
    rows = []
    soup = BeautifulSoup(html_text, 'html.parser')
    for tr in soup.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) >= 6:
            subject = tds[0].get_text(strip=True)
            last_date = tds[1].get_text(strip=True)
            total = tds[3].get_text(strip=True)
            attended = tds[4].get_text(strip=True)
            pct = tds[5].get_text(strip=True)
            if subject and total.isdigit():
                rows.append({
                    'subject': subject,
                    'last_date': last_date,
                    'total': int(total),
                    'attended': int(attended),
                    'percentage': pct,
                })
    return rows


def parse_detail(html_text: str) -> list[dict]:
    """Parse attendance detail HTML into a list of course dicts."""
    if not html_text:
        return []
    courses = []
    soup = BeautifulSoup(html_text, 'html.parser')
    for course_div in soup.find_all('div', class_='border'):
        heading = course_div.find('p', class_='main-heading')
        if heading:
            text = heading.get_text(strip=True)
            code = text.replace('Course code :', '').strip()
            table = course_div.find('table')
            course_rows = []
            if table:
                headers = [th.get_text(strip=True) for th in table.find_all('th')]
                for tr in table.find_all('tr')[1:]:
                    cols = [td.get_text(strip=True) for td in tr.find_all('td')]
                    if len(cols) >= 4:
                        row = dict(zip(headers, cols)) if headers else {}
                        course_rows.append(row)
            if code:
                courses.append({'code': code, 'rows': course_rows})
    return courses


def extract_summary_stats(rows: list[dict]) -> dict:
    """Extract aggregate stats from attendance summary."""
    total_attended = sum(r['attended'] for r in rows if not r['subject'].startswith('*'))
    total_held = sum(r['total'] for r in rows if not r['subject'].startswith('*'))
    aggregate = [r for r in rows if r['subject'].startswith('*')]
    agg_pct = aggregate[0]['percentage'] if aggregate else ''
    return {
        'total_attended': total_attended,
        'total_held': total_held,
        'overall_percentage': agg_pct,
        'course_count': len([r for r in rows if not r['subject'].startswith('*')]),
    }
