"""Shared utilities: login, Turnstile solving, session management, API calls."""
import re
import os
import uuid
import sys
import json
import time
import html as html_mod
from urllib.parse import quote, urlencode

import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, redirect, url_for, session, jsonify


LOGIN_URL = "https://ums.lpu.in/lpuums/"
BASE = "https://ums.lpu.in/lpuums/"


def get_page_with_turnstile():
    """Fetch login page - try HTTP-only first, fall back to browser-based solving."""
    import requests as _req
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    try:
        resp = _req.get(LOGIN_URL, headers=headers, timeout=30)
        html = resp.text
        if 'cf-turnstile-response' in html:
            print(f"  [FETCH] HTTP-only: fetched {len(html)} chars, cf-turnstile-response found", file=sys.stderr)
            return html
        print(f"  [FETCH] HTTP-only missing cf-turnstile-response, trying Fetcher...", file=sys.stderr)
    except Exception as e:
        print(f"  [FETCH] HTTP-only failed: {e}", file=sys.stderr)

    last_err = None
    for attempt in range(3):
        try:
            from scrapling.fetchers import Fetcher
            response = Fetcher.fetch(
                LOGIN_URL,
                impersonate='chrome',
                timeout=120,
                follow_redirects=True,
            )
            html = response.html_content if hasattr(response, 'html_content') else response.text
            if 'cf-turnstile-response' in html:
                print(f"  [FETCH] Fetcher (curl_cffi): fetched {len(html)} chars, cf-turnstile-response found", file=sys.stderr)
                return html
            print(f"  [RETRY {attempt+1}] Fetcher: no cf-turnstile-response found", file=sys.stderr)
        except Exception as e:
            last_err = e
            print(f"  [RETRY {attempt+1}] Fetcher failed: {e}", file=sys.stderr)

    raise RuntimeError(f"Failed to fetch login page with Turnstile after 3 attempts: {last_err}")


def parse_form_fields(html: str) -> dict:
    """Extract all required form fields from the login page HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    fields = {}
    v = soup.find('input', {'name': '__VIEWSTATE'})
    fields['viewstate'] = v['value'] if v else ''
    v = soup.find('input', {'name': '__VIEWSTATEGENERATOR'})
    fields['viewstategenerator'] = v['value'] if v else ''
    v = soup.find('input', {'name': '__EVENTVALIDATION'})
    fields['eventvalidation'] = v['value'] if v else ''
    pw_input = soup.find('input', {'type': 'password'})
    fields['password_field'] = pw_input['name'] if pw_input else ''
    submit_input = soup.find('input', {'type': 'submit', 'value': 'Login'})
    fields['submit_button'] = submit_input['name'] if submit_input else ''
    turnstile_tag = soup.find('input', {'name': 'cf-turnstile-response'})
    fields['turnstile_token'] = turnstile_tag.get('value', '') if turnstile_tag else ''
    print(f"[DEBUG] turnstile token length: {len(fields['turnstile_token'])}")
    return fields


def login(session: requests.Session, userid: str, password: str, fields: dict) -> bool:
    """Log in to LPU UMS using extracted form fields and Turnstile token."""
    pw_field = fields['password_field']
    submit_btn = fields['submit_button']
    data = {
        'txtU': userid,
        pw_field: password,
        'cf-turnstile-response': fields['turnstile_token'],
        submit_btn: 'Login',
        'DropDownList1': '1',
        '__VIEWSTATE': fields['viewstate'],
        '__VIEWSTATEGENERATOR': fields['viewstategenerator'],
        '__EVENTVALIDATION': fields['eventvalidation'],
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://ums.lpu.in',
        'Referer': LOGIN_URL,
    }
    resp = session.post(LOGIN_URL, data=data, headers=headers,
                        allow_redirects=True, timeout=30)
    success = 'StudentDashboard' in resp.text or 'Student Dashboard' in resp.text
    return success


def call_api(session: requests.Session, url: str) -> str:
    """Call an ASP.NET WebMethod that returns JSON."""
    headers = {
        'Content-Type': 'application/json; charset=utf-8',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://ums.lpu.in/lpuums/StudentDashboard.aspx',
    }
    resp = session.post(url, data='{}', headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get('d', '')


def call_api_json(session: requests.Session, url: str):
    """Call an ASP.NET WebMethod and return the raw parsed JSON."""
    headers = {
        'Content-Type': 'application/json; charset=utf-8',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://ums.lpu.in/lpuums/StudentDashboard.aspx',
    }
    resp = session.post(url, data='{}', headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json().get('d', '')


def fetch_all_data(sess: requests.Session) -> dict:
    """Fetch all available data from UMS and return as a dict."""
    data = {}
    api_base = BASE + "StudentDashboard.aspx/"

    apis = {
        'attendance_summary': api_base + 'StudentAttendanceSummary',
        'attendance_detail': api_base + 'StudentAttendanceDetail',
        'marks': api_base + 'TermWiseCGPA',
        'courses': api_base + 'GetStudentCourses',
        'messages': api_base + 'GetStudentMessages',
        'all_messages': api_base + 'ViewAllMessages',
        'fee': api_base + 'PendingFee',
        'payments': api_base + 'GetPaymentDetails',
        'happenings': api_base + 'GetHappeningPosts',
        'promotions': api_base + 'GetPromotionPosts',
        'placements': api_base + 'GetPlacementDrives',
        'assignments': api_base + 'GetStudenPendingAssignments',
        'profile': api_base + 'GetStudentBasicInformation',
        'timetable': api_base + 'GetTimetableDetails',
        'heads': api_base + 'GetHeads',
        'placement_popup': api_base + 'GetPlacementPopupMessages',
    }

    print(f"  Fetching from {len(apis)} endpoints:", file=sys.stderr)
    for key, url in apis.items():
        try:
            print(f"    -> {url}", file=sys.stderr)
            raw = call_api(sess, url)
            if raw:
                data[key] = raw
                print(f"       [OK] {key}: {len(str(raw))} chars", file=sys.stderr)
            else:
                print(f"       [EMPTY] {key}", file=sys.stderr)
        except Exception as e:
            print(f"       [FAIL] {key}: {e}", file=sys.stderr)

    return data


def extract_result_token(sess: requests.Session) -> str | None:
    """Get examination result token via openapp.aspx redirect."""
    try:
        resp = sess.get(
            BASE + "openapp.aspx",
            params={'from': 'ums', 'toApp': 'nextproject',
                    'pagename': 'dashboard/examination/result/resultsummary'},
            timeout=30, allow_redirects=False
        )
        loc = resp.headers.get('Location', '')
        m = re.search(r'token=([a-zA-Z0-9_-]+)', loc)
        return m.group(1) if m else None
    except Exception as e:
        print(f"  [FAIL] extract_result_token: {e}", file=sys.stderr)
        return None


def _scrapling_fetch_credits(sess: requests.Session, url: str) -> dict[str, float]:
    """Fetch the Next.js resultsummary page via Scrapling Fetcher and
    extract course credits from the rendered HTML.

    Falls back to requests if Fetcher is unavailable.
    """
    try:
        from scrapling.fetchers import Fetcher
        cjar = tuple(sess.cookies)
        resp = Fetcher.fetch(
            url, impersonate='chrome',
            timeout=120, follow_redirects=True,
            cookies={c.name: c.value for c in cjar},
        )
        html = resp.html_content if hasattr(resp, 'html_content') else resp.text
        # Try parsing inline first, then fetch via requests fallback
        credits = parse_credit_table(html)
        if credits:
            print(f"  [OK] Fetcher: {len(credits)} course credits", file=sys.stderr)
            return credits
        print(f"  [INFO] Fetcher: page fetched ({len(html)} chars), no credit table", file=sys.stderr)
    except Exception as e:
        print(f"  [FAIL] Scrapling Fetcher: {e}", file=sys.stderr)

    try:
        resp = sess.get(url, timeout=30)
        credits = parse_credit_table(resp.text)
        if credits:
            print(f"  [OK] requests fallback: {len(credits)} course credits", file=sys.stderr)
            return credits
    except Exception:
        pass
    return {}


def fetch_credits_from_api(sess: requests.Session, reg_no: str) -> dict[str, float]:
    """Fetch course credits via openapp.aspx → studentums.lpu.in resultsummary page.

    Flow (matches Scrapling MCP testing):
      1. Get fresh token from openapp.aspx redirect (requests)
      2. Fetch rendered Next.js page via Scrapling browser (StealthyFetcher)
      3. Parse credit data from fully-rendered DOM

    Returns {course_code: credits} mapping, e.g. {"CHE110": 4.0, ...}.
    """
    token = extract_result_token(sess)
    if not token:
        print(f"  [FAIL] fetch_credits_from_api: no token from openapp.aspx", file=sys.stderr)
        return {}
    url = f"https://studentums.lpu.in/dashboard/examination/result/resultsummary?token={token}"
    print(f"  -> {url}", file=sys.stderr)

    credits = _scrapling_fetch_credits(sess, url)
    if credits:
        return credits

    try:
        resp = sess.get(url, timeout=30)
        credits = parse_credit_table(resp.text)
        if credits:
            print(f"  [OK] requests fallback: {len(credits)} course credits", file=sys.stderr)
            return credits
    except Exception:
        pass

    return {}


def _parse_text_for_credits(text: str) -> dict[str, float]:
    """Parse plain text for credit patterns after Grades tab is clicked.

    Handles format:
        CODE :: NAME
        Credit-X.XX
    """
    credits = {}

    for match in re.finditer(
        r'([A-Z]{3,4}\d{3})\s*::[^\n]*\n\s*Credit[-\s]*(\d+(?:\.\d+)?)',
        text, re.I
    ):
        code = match.group(1).strip()
        try:
            cr = float(match.group(2))
            if cr > 0:
                credits[code] = cr
        except ValueError:
            pass

    for match in re.finditer(
        r'([A-Z]{3,4}\d{3})\s*(?:::?\s*.+?)?\s*[(-]?\s*(\d+(?:\.\d+)?)\s*(?:credit|cr|Credits?)',
        text, re.I
    ):
        code = match.group(1).strip()
        if code not in credits:
            try:
                cr = float(match.group(2))
                if cr > 0:
                    credits[code] = cr
            except ValueError:
                pass

    return credits


def _parse_table_for_credits(soup) -> dict[str, float]:
    """Parse HTML tables for credit data (Credit, Cr, Credits column headers)."""
    credits = {}
    for table in soup.find_all('table'):
        headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
        credit_idx = next((i for i, h in enumerate(headers)
                          if h in ('credit', 'credits', 'cr', 'c.', 'credit(s)')), -1)
        if credit_idx == -1:
            continue
        code_idx = next((i for i, h in enumerate(headers) if h in ('code', 'course', 'subject', 'course code')), -1)
        if code_idx == -1:
            code_idx = 0
        for tr in table.find_all('tr')[1:]:
            cols = tr.find_all('td')
            if len(cols) <= max(credit_idx, code_idx):
                continue
            code = cols[code_idx].get_text(strip=True)
            try:
                cr = float(cols[credit_idx].get_text(strip=True))
            except ValueError:
                cr = 0
            if code and cr > 0:
                credits[code] = cr
    return credits


def parse_credit_table(html: str) -> dict[str, float]:
    """Parse the resultsummary HTML for course-wise credits.

    Tries:
    1. HTML tables with any credit-like column header
    2. Text pattern: CODE :: NAME \\n X.X credit
    3. Plain text regex for various credit formats
    """
    soup = BeautifulSoup(html, 'html.parser')

    credits = _parse_table_for_credits(soup)
    if credits:
        return credits

    text = soup.get_text(separator='\n')
    credits = _parse_text_for_credits(text)
    if credits:
        return credits

    for match in re.finditer(r'([A-Z]+\d+)\s*[:(]\s*(\d+(?:\.\d+)?)\s*(?:credit|cr)[^\d]*', html, re.I):
        code = match.group(1)
        if code not in credits:
            try:
                cr = float(match.group(2))
                if cr > 0:
                    credits[code] = cr
            except ValueError:
                pass

    return credits
