"""Shared utilities: login, Turnstile solving, session management, API calls."""
import re
import os
import uuid
import sys
import json
import time
import html as html_mod
from urllib.parse import quote, urlencode

from bs4 import BeautifulSoup
from flask import Flask, render_template, request, redirect, url_for, session, jsonify


LOGIN_URL = "https://ums.lpu.in/lpuums/"
BASE = "https://ums.lpu.in/lpuums/"

# Cloudflare Worker proxy — falls back when the Render IP is blocked.
# Set via set_proxy_worker_url().
_PROXY_URL = None


# Optional progress callback — set via set_progress_callback() from main.py.
# Signature: callback(step: str, message: str, pct: int) -> None
# When unset, progress updates are no-ops (safe to call from CLI / tests).
_progress_callback = None


def set_progress_callback(fn):
    """Register a progress callback. Pass None to clear."""
    global _progress_callback
    _progress_callback = fn


def set_proxy_worker_url(url: str) -> None:
    global _PROXY_URL
    _PROXY_URL = url


def _emit_progress(step: str, message: str, pct: int) -> None:
    if _progress_callback is not None:
        try:
            _progress_callback(step, message, pct)
        except Exception:
            pass


def fetch_page(url: str, method: str = 'GET', data: dict | None = None) -> str:
    """Fetch a page using curl_cffi (TLS impersonation), falling back to the
    Cloudflare Worker proxy if the direct request fails or gets a challenge."""
    from curl_cffi import requests as cffi_req

    impersonate = 'chrome120'
    last_err = None

    strategies = []

    # Strategy 1: direct curl_cffi (TLS impersonation bypasses JS challenge)
    strategies.append(('direct', lambda: cffi_req.request(
        method, url,
        data=data,
        impersonate=impersonate,
        timeout=30,
        allow_redirects=True,
    )))

    # Strategy 2: via Cloudflare Worker proxy (if configured)
    if _PROXY_URL:
        strategies.append(('worker-proxy', lambda: cffi_req.request(
            method, _PROXY_URL,
            params={'url': url},
            data=data,
            impersonate=impersonate,
            timeout=30,
            allow_redirects=True,
        )))

    for label, fn in strategies:
        try:
            print(f"  [FETCH] {label}: {url[:60]}...", file=sys.stderr)
            resp = fn()
            html = resp.text
            if not html or len(html) < 100:
                print(f"  [FAIL] {label}: too short ({len(html or '')} chars)", file=sys.stderr)
                continue
            print(f"  [OK] {label}: {len(html)} chars, status={resp.status_code}", file=sys.stderr)
            return html
        except Exception as e:
            last_err = e
            print(f"  [FAIL] {label}: {e}", file=sys.stderr)

    raise RuntimeError(
        f"Failed to fetch {url}. Last error: {last_err}. "
        "Cloudflare may be blocking this IP/network."
    )


def fetch_login_page() -> str:
    """Fetch the LPU UMS login page HTML using curl_cffi."""
    _emit_progress('turnstile', 'Fetching login page via TLS impersonation…', 5)
    html = fetch_page(LOGIN_URL)
    _emit_progress('turnstile', f'Got login page ({len(html)} chars)', 40)
    return html


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


# Login error patterns are checked as whole word/phrase only (so common JS words
# like "error" don't false-positive). These are the exact phrases LPU UMS uses
# in its error label/messages on failed login.
_LOGIN_ERROR_PHRASES = (
    'invalid username or password',
    'invalid user name or password',
    'invalid credentials',
    'invalid login',
    'login failed',
    'authentication failed',
    'userid or password is invalid',
    'username or password is incorrect',
    'please enter valid',
    'please enter correct',
    'try again later',
    'too many attempts',
    'account is locked',
    'account locked',
    'captcha verification failed',
    'turnstile verification failed',
)


def _body_has_login_error(html: str) -> bool:
    """True only if the response body contains a clear login-error phrase.

    Uses lowercase matching of distinct error phrases (not single common words)
    to avoid false positives from words like 'error' or 'failed' appearing in
    JavaScript, CSS, or unrelated dashboard widgets.
    """
    body_lower = html.lower()
    for phrase in _LOGIN_ERROR_PHRASES:
        if phrase in body_lower:
            return phrase
    return False


def login(session, userid: str, password: str, fields: dict) -> bool:
    """Log in to LPU UMS using extracted form fields.

    Tries submitting with an empty Turnstile token first (some servers don't
    validate it). Logs a warning if token is missing.

    Success is verified by the URL changing to StudentDashboard.aspx (the
    strongest signal — LPU only redirects there after a successful login).
    We also accept new auth cookies as a fallback. Login error phrases in
    the response body are checked but only against specific phrases, to
    avoid false positives on common dashboard words.
    """
    token = fields.get('turnstile_token', '')
    if not token or len(token) < 20:
        print("  [LOGIN] Turnstile token is empty — submitting anyway "
              "(server may or may not require it)", file=sys.stderr)

    pw_field = fields['password_field']
    submit_btn = fields['submit_button']
    data = {
        'txtU': userid,
        pw_field: password,
        'cf-turnstile-response': token,
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
    cookies_before = {c.name for c in session.cookies}
    resp = session.post(LOGIN_URL, data=data, headers=headers,
                        allow_redirects=True, timeout=30)

    url_ok = 'studentdashboard' in resp.url.lower()
    matched_phrase = _body_has_login_error(resp.text)
    new_auth_cookies = any(
        c.name.lower() in ('.aspxauth', 'asp.net_sessionid', 'ums_auth', 'auth')
        for c in session.cookies if c.name not in cookies_before
    )

    if url_ok:
        success = True
    elif new_auth_cookies:
        success = matched_phrase is False
    else:
        success = False

    print(f"  [LOGIN] url_ok={url_ok} new_cookies={new_auth_cookies} "
          f"matched_phrase={matched_phrase!r} final_url={resp.url[:80]}", file=sys.stderr)
    return success


def call_api(session, url: str) -> str:
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


def call_api_json(session, url: str):
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


def fetch_all_data(sess) -> dict:
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


def extract_result_token(sess) -> str | None:
    """Get examination result token via openapp.aspx redirect."""
    _emit_progress('credits', 'Getting exam-result token from UMS…', 94)
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


def _click_grades_tab(page) -> bool:
    """Find and click the Grades tab on the resultsummary page."""
    selectors = [
        '[role="tab"]:has-text("Grades")',
        'button:has-text("Grades")',
        'text=Grades >> visible=true',
    ]
    for selector in selectors:
        try:
            tab = page.wait_for_selector(selector, timeout=5000)
            if tab and tab.is_visible():
                tab.click()
                page.wait_for_timeout(3000)
                page.wait_for_load_state('networkidle', timeout=15000)
                return True
        except Exception:
            continue
    return False


def _transfer_cookies(sess) -> list[dict]:
    """Transfer session cookies to Playwright-compatible format."""
    cookies = []
    for c in sess.cookies:
        cookies.append({
            'name': c.name,
            'value': c.value,
            'domain': c.domain or 'ums.lpu.in',
            'path': c.path or '/',
            'httpOnly': False,
            'secure': c.secure if hasattr(c, 'secure') else True,
        })
    return cookies


def fetch_credits_from_api(sess, reg_no: str) -> dict[str, float]:
    """Fetch course credits via Playwright going through openapp.aspx.

    The resultsummary page is a Next.js SPA behind a short-lived auth token.
    Instead of extracting the token ahead of time (which expires), we open
    openapp.aspx INSIDE Playwright with UMS session cookies transferred,
    let it redirect to resultsummary with a fresh token, then click the
    Grades tab to reveal per-course credit data.

    Returns {course_code: credits} mapping, e.g. {"CHE110": 4.0, ...}.
    Returns {} if credits cannot be fetched.
    """
    import traceback as _tb

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"  [FAIL] playwright not installed", file=sys.stderr)
        return {}

    _emit_progress('credits', 'Launching browser for credits…', 93)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
            )

            # Transfer UMS session cookies to Playwright
            pw_cookies = _transfer_cookies(sess)
            context = browser.new_context(
                user_agent=(
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                ),
                locale='en-IN',
            )
            context.add_cookies(pw_cookies)
            page = context.new_page()

            # Navigate to openapp.aspx — it redirects to resultsummary with fresh token
            openapp_url = BASE + "openapp.aspx?from=ums&toApp=nextproject&pagename=dashboard/examination/result/resultsummary"
            print(f"  [CREDITS] Navigating to openapp.aspx...", file=sys.stderr)

            _emit_progress('credits', 'Getting fresh auth token…', 94)
            page.goto(openapp_url, wait_until='networkidle', timeout=60000)

            current_url = page.url
            print(f"  [CREDITS] Redirected to: {current_url[:100]}", file=sys.stderr)

            # Check if we got the results page (not login)
            body_text = page.inner_text('body')
            if 'Log in' in body_text and 'HeadOffice' in body_text:
                print(f"  [FAIL] Got login page — cookie auth failed or session expired", file=sys.stderr)
                browser.close()
                return {}

            _emit_progress('credits', 'Clicking Grades tab…', 95)
            clicked = _click_grades_tab(page)
            if clicked:
                print(f"  [CLICK] Grades tab clicked", file=sys.stderr)
            else:
                print(f"  [WARN] Grades tab not found, using current DOM", file=sys.stderr)

            html = page.content()
            browser.close()

        print(f"  [CREDITS] Page: {len(html)} chars", file=sys.stderr)

        credits = _parse_text_for_credits(BeautifulSoup(html, 'html.parser').get_text(separator='\n'))
        if credits:
            _emit_progress('credits', f'Found {len(credits)} course credits', 97)
            print(f"  [OK] {len(credits)} course credits parsed", file=sys.stderr)
            return credits

        print(f"  [FAIL] No credit data found in rendered page", file=sys.stderr)

    except Exception as e:
        print(f"  [FAIL] fetch_credits_from_api: {e}", file=sys.stderr)
        _tb.print_exc(file=sys.stderr)
    return {}


def _parse_text_for_credits(text: str) -> dict[str, float]:
    """Parse plain text for credit patterns after Grades tab is clicked.

    Handles format:
        CHE110 :: ENVIRONMENTAL STUDIES
        Credit-2.00
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
    return credits


def parse_credit_table(html: str) -> dict[str, float]:
    """Parse the resultsummary HTML for course-wise credits.

    Extracts credit data from rendered text after clicking the Grades tab.
    Format: CODE :: NAME \\n Credit-X.XX
    """
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(separator='\n')
    return _parse_text_for_credits(text)
