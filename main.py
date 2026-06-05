#!/usr/bin/env python3
"""LPU UMS Dashboard -- stripped to profile + CGPA calculator."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uuid
import time
from curl_cffi import requests as cffi_requests
from flask import Flask, render_template, request, jsonify, session as flask_session

from pipeline import login_flow, fetch_dashboard_data, process_dashboard_data, print_dashboard_report
from utils import set_proxy_worker_url

# Set Cloudflare Worker proxy fallback (curl_cffi tries this if direct fetch fails or gets challenged)
set_proxy_worker_url("https://lpu-proxy.narendra-p7893.workers.dev")

app = Flask(__name__, template_folder='.')
app.secret_key = os.urandom(24).hex()

_cache: dict[str, dict] = {}

@app.route('/')
def landing_page():
    return render_template('landing.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def do_login():
    try:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({'ok': False, 'error': 'Invalid request: expected JSON body'})
        userid = data.get('userid', '').strip()
        password = data.get('password', '').strip()
        if not userid or not password:
            return jsonify({'ok': False, 'error': 'User ID and password are required.'})

        sess = cffi_requests.Session(impersonate="chrome120")
        if not login_flow(sess, userid, password):
            return jsonify({'ok': False, 'error': 'Login failed. Check your credentials.'})

        raw_data = fetch_dashboard_data(sess, userid)
        parsed = process_dashboard_data(raw_data)

        cache_id = str(uuid.uuid4())
        _cache[cache_id] = {'data': parsed, 'ts': time.time()}
        flask_session['cache_id'] = cache_id
        return jsonify({'ok': True})
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/dashboard')
def dashboard():
    if 'cache_id' not in flask_session or flask_session['cache_id'] not in _cache:
        return render_template('login.html')
    return render_template('dashboard.html')

@app.route('/dashboard/data')
def dashboard_data():
    cache_id = flask_session.get('cache_id')
    if not cache_id or cache_id not in _cache:
        return jsonify({'ok': False, 'error': 'Session expired.'})
    cached = _cache[cache_id].get('data')
    if not cached:
        return jsonify({'ok': False, 'error': 'No data.'})
    return jsonify({'ok': True, 'profile': cached.get('profile', {}), 'marks': cached.get('marks', {})})


def cli_main():
    if len(sys.argv) < 4:
        print("Usage: python main.py --cli <userid> <password>", file=sys.stderr)
        sys.exit(1)
    userid = sys.argv[2]
    password = sys.argv[3]

    sess = cffi_requests.Session(impersonate="chrome120")
    if not login_flow(sess, userid, password):
        sys.exit(1)

    raw_data = fetch_dashboard_data(sess, userid)
    data = process_dashboard_data(raw_data)
    print_dashboard_report(data)


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == '--cli':
        cli_main()
    else:
        print("Starting web server at http://127.0.0.1:5000")
        app.run(host='127.0.0.1', port=5000, debug=True, use_reloader=False)
