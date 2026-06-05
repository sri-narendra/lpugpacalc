# GPA Calc — LPU UMS CGPA Calculator

Self-hosted Flask app that signs into LPU's UMS and offers an interactive **what-if CGPA calculator** with a dark, conversion-optimized landing page.

## Features

- **Landing page** — Dashboard mockup preview, benefit-driven copy, trust signals, one-click UMS sign-in.
- **Login** — Cloudflare Turnstile bypass via Scrapling StealthyFetcher.
- **Student Profile** — Name, reg no, batch, email, phone, campus, avatar.
- **CGPA Calculator** — Term-wise grades with live TGPA/CGPA projection on grade change.
- **Dual mode** — Web server or CLI (`--cli`).

## Requirements

- Python 3.10+
- `flask`, `requests`, `beautifulsoup4`, `scrapling`, `playwright`

## Installation

```bash
pip install flask requests beautifulsoup4 scrapling playwright
playwright install chromium
```

## Usage

### Web Server

```bash
python main.py
```

Opens at `http://127.0.0.1:5000`.

### CLI Mode

```bash
python main.py --cli <userid> <password>
```

## Project Structure

```
yumsclonesite/
├── main.py           # Flask app, routes
├── pipeline.py       # Login, fetch, parse, display
├── utils.py          # Turnstile solving, API calls, credit scraping
├── landing.html      # Landing / hero page
├── login.html        # Sign-in page
├── dashboard.html    # Profile + CGPA calculator
├── requirements.txt
└── README.md
```

## How It Works

1. **Landing** → user sees a live dashboard mockup with projected CGPA, clicks "Check Your CGPA".
2. **Login** — Fetches UMS login page via Scrapling (solves Turnstile), extracts ASP.NET fields, POSTs credentials.
3. **Fetch** — Calls `TermWiseCGPA` and `GetStudentBasicInformation` WebMethods, scrapes `openapp.aspx` for course credits.
4. **Render** — Single-page dashboard with profile card and what-if CGPA calculator.

## Endpoints

| Route             | Method | Description                       |
| ----------------- | ------ | --------------------------------- |
| `/`               | GET    | Landing page                      |
| `/login`          | GET    | Login page                        |
| `/login`          | POST   | JSON `{userid, password}`         |
| `/dashboard`      | GET    | Dashboard UI                      |
| `/dashboard/data` | GET    | `{profile, marks}` as JSON        |
