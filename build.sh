#!/usr/bin/env bash
set -e

echo "=== Installing Python dependencies ==="
pip install -r requirements.txt

echo "=== Installing Playwright Chromium (for undetected_chromedriver) ==="
python -m playwright install chromium

echo "=== Build complete ==="
