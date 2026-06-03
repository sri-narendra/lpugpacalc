"""Messages and announcements."""
from bs4 import BeautifulSoup


def parse_messages(html_text: str) -> list[dict]:
    """Parse GetStudentMessages HTML into message list."""
    if not html_text:
        return []
    soup = BeautifulSoup(html_text, 'html.parser')
    messages = []
    for div in soup.find_all('div', class_='mycoursesdiv'):
        text_divs = div.find_all('div',
                                  class_=lambda c: c and 'font-weight-medium' in c)
        text_parts = [d.get_text(strip=True) for d in text_divs if d.get_text(strip=True)]
        if text_parts:
            messages.append({
                'title': text_parts[0] if len(text_parts) > 0 else '',
                'snippet': text_parts[1] if len(text_parts) > 1 else '',
            })
    return messages


def parse_all_messages(html_text: str) -> list[dict]:
    """Parse ViewAllMessages HTML into structured message list."""
    if not html_text:
        return []
    soup = BeautifulSoup(html_text, 'html.parser')
    messages = []
    for div in soup.find_all('div', class_='row'):
        text = div.get_text(strip=True)
        if text and len(text) > 20:
            messages.append({'text': text[:300]})
    if not messages:
        lines = [l.strip() for l in html_text.split('\n') if l.strip()]
        for line in lines[:50]:
            if len(line) > 20:
                messages.append({'text': line[:300]})
    return messages
