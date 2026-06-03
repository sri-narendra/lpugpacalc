"""Happenings, news, promotions, placements, assignments, timetable."""
import json
import re

from bs4 import BeautifulSoup


def parse_happenings(html_text: str) -> list[dict]:
    """Parse GetHappeningPosts into news items."""
    if not html_text:
        return []
    soup = BeautifulSoup(html_text, 'html.parser')
    items = []
    for li in soup.find_all('li'):
        text = li.get_text(strip=True)
        if text and len(text) > 10:
            items.append({'text': text})
    if not items:
        lines = [l.strip() for l in html_text.split('\n') if l.strip()]
        for line in lines[:30]:
            if len(line) > 20:
                items.append({'text': line[:300]})
    return items


def parse_placements(html_text: str) -> list[dict]:
    """Parse GetPlacementDrives into placement items."""
    if not html_text:
        return []
    soup = BeautifulSoup(html_text, 'html.parser')
    items = []
    for div in soup.find_all('div', class_='mycoursesdiv'):
        title_div = div.find('div', class_=lambda c: c and 'font-weight-medium' in c)
        company = title_div.get_text(strip=True) if title_div else ''
        streams = ''
        salary = ''
        for p in div.find_all('p', class_='text-muted'):
            text = p.get_text(strip=True)
            if text.startswith('Stream'):
                streams = text.replace('Stream :', '').strip()
            elif text.startswith('Salary'):
                salary = text.replace('Salary Package :', '').strip()
        if company:
            items.append({
                'company': company,
                'streams': streams,
                'salary': salary,
            })
    return items


def parse_assignments(raw: str) -> list[dict]:
    """Parse assignments response."""
    if not raw or 'No Assignments' in raw:
        return []
    return [{'text': raw[:300]}]


def parse_timetable(raw: str) -> list[dict]:
    """Parse timetable response."""
    if not raw or 'No Timetable' in raw:
        return []
    return [{'text': raw[:300]}]


def parse_placement_popup(raw_json_str: str) -> list[dict]:
    """Parse GetPlacementPopupMessages JSON.
    
    Returns list of {drive_type, company, register_by}
    """
    if not raw_json_str:
        return []
    try:
        parsed = json.loads(raw_json_str)
        if isinstance(parsed, list) and len(parsed) > 0:
            msg = parsed[0].get('Message', '')
        else:
            return []
    except (json.JSONDecodeError, KeyError, IndexError):
        return []

    if not msg or msg == '0':
        return []

    soup = BeautifulSoup(msg, 'html.parser')
    items = []
    for li in soup.find_all('li'):
        text = li.get_text(strip=True)
        m = re.match(r'(.+?)\s+of\s+(.+?)\s+notified later\.?\s*Registration/De-registration open till\s+(.*)', text)
        if m:
            drive_type = m.group(1).strip()
            company = m.group(2).strip()
            reg_date = m.group(3).strip()
            items.append({
                'company': company,
                'drive_type': drive_type,
                'register_by': reg_date,
                'drive_date': 'Will be Notified Later',
                'status': 'Open',
            })
        else:
            items.append({'text': text})
    return items


def parse_heads(html_text: str) -> list[dict]:
    """Parse GetHeads (mentors/authorities) response."""
    if not html_text:
        return []
    soup = BeautifulSoup(html_text, 'html.parser')
    heads = []
    for div in soup.find_all('div', class_='card'):
        name_tag = div.find('h5') or div.find('b') or div.find('strong')
        role_tag = div.find(['p', 'span', 'small'])
        name = name_tag.get_text(strip=True) if name_tag else ''
        role = role_tag.get_text(strip=True) if role_tag else ''
        if name:
            heads.append({'name': name, 'role': role})
    if not heads:
        text_lines = soup.get_text(strip=True)
        parts = text_lines.split('\n') if '\n' in text_lines else [text_lines[:500]]
        for part in parts[:30]:
            if part.strip():
                heads.append({'text': part.strip()[:200]})
    return heads
