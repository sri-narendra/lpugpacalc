# YUMS — LPU UMS Dashboard Clone

A self-hosted Flask web application that scrapes and re-displays academic data from LPU's **University Management System (UMS)**. Provides a modern dark-mode dashboard for attendance, marks, CGPA, profile, fee, messages, timetable, news, and placement drives.

## Features

- **Attendance** — Per-subject summary with percentage, day-wise detail, safe-bunk calculator, and donut-chart visualization.
- **Marks & CGPA** — Term-wise course grades, TGPA/CGPA display, and an interactive what-if CGPA calculator.
- **Profile** — Student name, registration number, program, section, batch, email, phone.
- **Fee** — Pending amount and payment transaction history.
- **Messages** — Latest announcements and all-messages view.
- **Timetable** — Weekly schedule display.
- **News / Happenings** — Campus updates and news feed.
- **Placements** — Your placement drives with company, drive type, and registration deadlines.
- **Cloudflare Turnstile bypass** — Uses Scrapling's StealthyFetcher to solve the Turnstile challenge on login.
- **Dual mode** — Run as a web server (Flask) or in CLI mode for terminal output.

## Tech Stack

| Component      | Technology                            |
| -------------- | ------------------------------------- |
| Backend        | Python 3 + Flask                      |
| Web Scraping   | requests, BeautifulSoup 4             |
| Anti-bot       | Scrapling (StealthyFetcher)           |
| Frontend       | Tailwind CSS (CDN), Inter font        |
| Templates      | Jinja2                                |
| Testing        | unittest                              |

## Requirements

- Python 3.10+
- `flask`, `requests`, `beautifulsoup4`, `scrapling`

## Installation

```bash
pip install flask requests beautifulsoup4 scrapling
```

## Usage

### Web Server

```bash
python main.py
```

Opens at `http://127.0.0.1:5000`. Log in with your LPU UMS credentials.

### CLI Mode

```bash
python main.py --cli <userid> <password>
```

Prints profile, attendance summary, marks (term-wise), fee, news, messages, and placements to the terminal.

## Project Structure

```
yumsclonesite/
├── main.py                          # Flask app — routes, caching, orchestration
├── utils.py                         # Login flow, Turnstile solving, API calls
├── attendance.py                    # Attendance summary & detail parsers
├── events.py                        # Happenings, placements, assignments,
│                                    # timetable, heads parsers
├── fee.py                           # Pending fee & payment history parsers
├── lpu_attendance.py                # Older standalone version (monolithic)
├── marks.py                         # Term-wise CGPA & course grade parsers
├── messages.py                      # Messages & announcements parsers
├── profile.py                       # Student profile JSON parser
├── placements.html                  # Raw UMS login page (reference)
├── placements_page.html             # Raw UMS login page (reference)
├── placements_authenticated.html    # Raw UMS login page (reference)
├── templates/
│   ├── login.html                   # Login page — clean, minimal UI
│   └── dashboard.html               # Dashboard — dark theme, tabbed views
└── tests/
    ├── __init__.py
    └── test_login_errors.py         # Unit tests for login error handling
```

## How It Works

1. **Login** — The app fetches the UMS login page via Scrapling (which solves Cloudflare Turnstile), extracts ASP.NET form fields (`__VIEWSTATE`, `__VIEWSTATEGENERATOR`, `__EVENTVALIDATION`, the dynamic password field name, and the Turnstile token), then POSTs credentials to authenticate.
2. **Data Fetching** — After login, it calls 16+ ASP.NET WebMethod endpoints (`StudentDashboard.aspx/StudentAttendanceSummary`, `TermWiseCGPA`, `GetStudentMessages`, etc.) using the authenticated session.
3. **Parsing** — Each endpoint returns HTML or JSON, which is parsed by dedicated functions in the `attendance.py`, `marks.py`, `profile.py`, etc. modules.
4. **Caching** — Parsed data is cached server-side per session UUID (30-minute TTL) to avoid repeated calls.
5. **Rendering** — The Flask dashboard route serves `dashboard.html`, which fetches cached data via `/dashboard/data` and renders it client-side with JavaScript.

## Endpoints

| Route              | Method | Description                         |
| ------------------ | ------ | ----------------------------------- |
| `/`                | GET    | Login page                          |
| `/login`           | POST   | Accepts JSON `{userid, password}`   |
| `/dashboard`       | GET    | Dashboard UI                        |
| `/dashboard/data`  | GET    | All parsed data as JSON             |
| `/data/<section>`  | GET    | Individual section data             |
| `/refresh`         | GET    | Re-fetches all data from UMS        |

## Tests

```bash
python -m unittest discover tests
```

## Notes

- Password field names on UMS change dynamically; `utils.py` extracts them from the page HTML automatically.
- The Turnstile token is only valid for a short window — the login must be completed quickly after fetching the page.
- `lpu_attendance.py` is an older, standalone version that only fetches attendance. Use `main.py` for full functionality.
- The `placements*.html` files are raw snapshots of the UMS login page for reference during development.

## License

MIT
