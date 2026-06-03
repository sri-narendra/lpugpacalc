#!/usr/bin/env python3
"""LPU UMS Dashboard — Web UI for attendance, marks, profile, messages, fee & more.

Usage:
    python main.py          # start web server
    python main.py --cli <userid> <password>   # CLI mode

Requires: flask, scrapling, requests, beautifulsoup4
"""

import os
import re
import sys
import uuid
import time
import json

from flask import Flask, render_template, request, redirect, url_for, session, jsonify

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    get_page_with_turnstile, parse_form_fields, login,
    call_api, call_api_json, fetch_all_data,
    fetch_credits_from_api,
    LOGIN_URL, BASE,
)
from attendance import parse_summary, parse_detail, extract_summary_stats
from marks import parse_term_cgpa, parse_courses
from profile import parse_profile, extract_profile_fields
from messages import parse_messages, parse_all_messages
from fee import parse_pending_fee, parse_payments
from events import parse_happenings, parse_placements, parse_assignments, parse_timetable, parse_heads, parse_placement_popup

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

_data_cache: dict[str, dict] = {}
DATA_API = BASE + "StudentDashboard.aspx/"


def _parse_all_cached(raw: dict) -> dict:
    """Parse all raw API responses into structured data."""
    result = {}

    summary_html = raw.get('attendance_summary', '')
    result['attendance_summary'] = parse_summary(summary_html)
    result['attendance_stats'] = extract_summary_stats(result['attendance_summary'])

    detail_html = raw.get('attendance_detail', '')
    result['attendance_detail'] = parse_detail(detail_html)

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
    elif not credit_map:
        print(f"  [DEBUG] credit_map empty or missing", file=sys.stderr)

    courses_raw = raw.get('courses', '')
    result['courses'] = parse_courses(courses_raw)

    profile_raw = raw.get('profile', '')
    parsed_profile = parse_profile(profile_raw)
    result['profile'] = extract_profile_fields(parsed_profile) if isinstance(parsed_profile, dict) else {}

    msg_html = raw.get('messages', '')
    result['messages'] = parse_messages(msg_html)

    all_msg_html = raw.get('all_messages', '')
    result['all_messages'] = parse_all_messages(all_msg_html)

    fee_raw = raw.get('fee', '')
    result['fee'] = parse_pending_fee(fee_raw)

    pay_raw = raw.get('payments', '')
    result['payments'] = parse_payments(pay_raw)

    happening_html = raw.get('happenings', '')
    result['happenings'] = parse_happenings(happening_html)

    placement_html = raw.get('placements', '')
    result['placements'] = parse_placements(placement_html)

    assign_raw = raw.get('assignments', '')
    result['assignments'] = parse_assignments(assign_raw)

    tt_raw = raw.get('timetable', '')
    result['timetable'] = parse_timetable(tt_raw)

    heads_html = raw.get('heads', '')
    result['heads'] = parse_heads(heads_html)

    placement_popup_raw = raw.get('placement_popup', '')
    result['placement_popup'] = parse_placement_popup(placement_popup_raw)

    return result


def _cleanup_cache():
    stale = [k for k, v in _data_cache.items()
             if time.time() - v.get('_ts', 0) > 1800]
    for k in stale:
        del _data_cache[k]


@app.route('/')
def login_page():
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def do_login():
    data = request.get_json()
    userid = data.get('userid', '').strip()
    password = data.get('password', '').strip()
    if not userid or not password:
        return jsonify({'ok': False, 'error': 'User ID and password are required.'})

    print("[1/4] Fetching login page with Turnstile solve...", file=sys.stderr)
    try:
        html = get_page_with_turnstile()
    except Exception as e:
        print(f"[ERROR] get_page_with_turnstile failed: {e}", file=sys.stderr)
        return jsonify({'ok': False, 'error': f'Failed to fetch login page: {e}'})

    print("[2/4] Parsing form fields, Turnstile token received", file=sys.stderr)
    fields = parse_form_fields(html)
    if not fields['turnstile_token']:
        print(f"  [WARN] No turnstile token in page (page size: {len(html)}b, cf-turnstile in html: {'cf-turnstile-response' in html}, form inputs: {len(re.findall(r'<input', html))})", file=sys.stderr)
    if not fields['password_field']:
        return jsonify({'ok': False, 'error': 'Password field not found on page.'})

    print("[3/4] Logging in...", file=sys.stderr)
    sess = __import__('requests').Session()
    if not login(sess, userid, password, fields):
        return jsonify({'ok': False, 'error': 'Login failed. Check your credentials.'})

    print("[4/4] Fetching all dashboard data from UMS...", file=sys.stderr)
    try:
        raw_data = fetch_all_data(sess)
        print(f"  Fetching course credits via API...", file=sys.stderr)
        raw_data['credit_map'] = fetch_credits_from_api(sess, userid)
        print(f"  Credits fetched: {len(raw_data['credit_map'])} courses", file=sys.stderr)
        parsed = _parse_all_cached(raw_data)
    except Exception as e:
        print(f"[ERROR] fetch_all_data failed: {e}", file=sys.stderr)
        return jsonify({'ok': False, 'error': f'Failed to fetch dashboard data: {e}'})

    cache_id = str(uuid.uuid4())
    _data_cache[cache_id] = {'data': parsed, 'raw': raw_data, '_ts': time.time()}
    session['cache_id'] = cache_id
    _cleanup_cache()
    return jsonify({'ok': True})


@app.route('/dashboard')
def dashboard():
    if 'cache_id' not in session or session['cache_id'] not in _data_cache:
        return redirect(url_for('login_page'))
    return render_template('dashboard.html')


@app.route('/dashboard/data')
def dashboard_data():
    cache_id = session.get('cache_id')
    if not cache_id or cache_id not in _data_cache:
        return jsonify({'ok': False, 'error': 'Session expired'})
    cached = _data_cache[cache_id]['data']
    return jsonify({'ok': True, **cached})


@app.route('/data/<section>')
def section_data(section):
    """Return individual section data. Sections: marks, messages, fee, etc."""
    cache_id = session.get('cache_id')
    if not cache_id or cache_id not in _data_cache:
        return jsonify({'ok': False, 'error': 'Session expired'})
    cached = _data_cache[cache_id]['data']
    if section in cached:
        return jsonify({'ok': True, 'data': cached[section]})
    # Try raw
    raw = _data_cache[cache_id].get('raw', {})
    if section in raw:
        return jsonify({'ok': True, 'data': raw[section]})
    return jsonify({'ok': False, 'error': f'Section "{section}" not found'})


@app.route('/refresh')
def refresh_data():
    """Refresh all data from UMS."""
    cache_id = session.get('cache_id')
    if not cache_id or cache_id not in _data_cache:
        return jsonify({'ok': False, 'error': 'Session expired'})
    cached = _data_cache[cache_id].get('raw', {})
    sess = cached.get('_session')
    if not sess:
        return jsonify({'ok': False, 'error': 'Session not available for refresh'})
    print("[REFRESH] Re-fetching all data from UMS...", file=sys.stderr)
    raw_data = fetch_all_data(sess)
    parsed = _parse_all_cached(raw_data)
    _data_cache[cache_id] = {'data': parsed, 'raw': raw_data, '_ts': time.time()}
    return jsonify({'ok': True})


def main():
    if len(sys.argv) < 4:
        print("Usage: python main.py --cli <userid> <password>", file=sys.stderr)
        sys.exit(1)

    userid = sys.argv[2]
    password = sys.argv[3]

    print("1. Fetching login page with Turnstile solve...", file=sys.stderr)
    html = get_page_with_turnstile()
    fields = parse_form_fields(html)
    if not fields['turnstile_token'] or not fields['password_field']:
        print("Error: Form fields not found!", file=sys.stderr)
        sys.exit(1)

    print("2. Logging in...", file=sys.stderr)
    sess = __import__('requests').Session()
    login(sess, userid, password, fields)
    print("   Login OK!", file=sys.stderr)

    print("3. Fetching all data...", file=sys.stderr)
    raw_data = fetch_all_data(sess)
    print(f"  Fetching course credits via API...", file=sys.stderr)
    raw_data['credit_map'] = fetch_credits_from_api(sess, userid)
    print(f"  Credits fetched: {len(raw_data['credit_map'])} courses", file=sys.stderr)
    parsed = _parse_all_cached(raw_data)

    print("\n" + "=" * 60)
    print("PROFILE")
    print("=" * 60)
    p = parsed.get('profile', {})
    for k, v in p.items():
        if v:
            print(f"  {k.replace('_', ' ').title()}: {v}")

    print("\n" + "=" * 60)
    print("ATTENDANCE SUMMARY")
    print("=" * 60)
    for r in parsed.get('attendance_summary', []):
        print(f"  {r['subject'][:48]:<50} {r['percentage']:>4}% ({r['attended']}/{r['total']})")

    print("\n" + "=" * 60)
    print("MARKS (TERM-WISE)")
    print("=" * 60)
    m = parsed.get('marks', {})
    if m.get('cgpa'):
        print(f"  CGPA: {m['cgpa']}")
    for term in m.get('terms', []):
        print(f"\n  {term['term']} — TGPA: {term.get('tgpa', 'N/A')}")
        print(f"  {'─' * 50}")
        for c in term.get('courses', []):
            print(f"    {c['name'][:42]:<44} {c['grade']}")

    print("\n" + "=" * 60)
    print("FEE")
    print("=" * 60)
    f = parsed.get('fee', {})
    print(f"  Pending: ₹{f.get('amount', 'N/A')}")
    for p in parsed.get('payments', []):
        print(f"  Payment: {p}")

    print("\n" + "=" * 60)
    print("NEWS / HAPPENINGS")
    print("=" * 60)
    for h in parsed.get('happenings', [])[:5]:
        print(f"  {h.get('text', '')[:100]}")

    print("\n" + "=" * 60)
    print("MESSAGES")
    print("=" * 60)
    for msg in parsed.get('messages', [])[:5]:
        print(f"  {msg.get('title', '')[:80]}")

    print("\n" + "=" * 60)
    print("PLACEMENTS (YOUR DRIVES)")
    print("=" * 60)
    for pl in parsed.get('placement_popup', []):
        print(f"  {pl.get('company','?'):30s} | {pl.get('drive_type','?'):25s} | Register by: {pl.get('register_by','?')}")
    print(f"\n  General drives: {len(parsed.get('placements', []))}")

    print(f"\nTotal courses: {len(parsed.get('attendance_summary', []))}")
    print(f"Total messages: {len(parsed.get('messages', []))}")


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == '--cli':
        main()
    else:
        _cleanup_cache()
        print("Starting web server at http://127.0.0.1:5000")
        app.run(host='127.0.0.1', port=5000, debug=True)
