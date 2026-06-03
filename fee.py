"""Fee details and payment history."""
import re
from bs4 import BeautifulSoup


def parse_pending_fee(html_text: str) -> dict:
    """Parse PendingFee response."""
    if not html_text:
        return {'amount': '', 'link': ''}
    soup = BeautifulSoup(html_text, 'html.parser')
    text = soup.get_text(strip=True)
    amount_match = re.search(r'([\d,]+)', text)
    amount = amount_match.group(1) if amount_match else text
    return {
        'amount': amount,
        'raw': text,
    }


def parse_payments(html_text: str) -> list[dict]:
    """Parse GetPaymentDetails response into transaction list."""
    if not html_text:
        return []
    soup = BeautifulSoup(html_text, 'html.parser')
    payments = []
    table = soup.find('table')
    if table:
        headers = [th.get_text(strip=True) for th in table.find_all('th')]
        for tr in table.find_all('tr')[1:]:
            cols = [td.get_text(strip=True) for td in tr.find_all('td')]
            if cols:
                row = dict(zip(headers, cols)) if headers else {'value': ' '.join(cols)}
                payments.append(row)
    if not payments:
        rows_found = re.findall(r'(\d{2}\s+\w+\s+\d{4}).*?(Rs\.?[\d,]+)', html_text)
        for date, amt in rows_found:
            payments.append({'date': date.strip(), 'amount': amt.strip()})
    return payments
