"""Marks, CGPA, grade and course data parsing."""
import re
import json
from bs4 import BeautifulSoup


def parse_term_cgpa(html_text: str) -> dict:
    """Parse TermWiseCGPA HTML response into structured data.

    HTML format (alternating):
      <div class='row...'><h4>Term : I</h4><h4>TGPA : 6.91</h4></div>
      <hr/>
      <div class='table-responsive'><table>
        <tr><td>Course :: NAME</td><td>Grade : B+</td></tr>
      </table></div>
      <div class='row...'><h4>Term : II</h4><h4>TGPA : 7.96</h4></div>
      ...
    """
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

    tgpas = [float(t['tgpa']) for t in terms if t['tgpa']]
    cgpa = round(sum(tgpas) / len(tgpas), 2) if tgpas else None

    return {
        'terms': terms,
        'total_courses': total,
        'cgpa': cgpa,
    }


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
