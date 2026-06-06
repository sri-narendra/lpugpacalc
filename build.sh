#!/usr/bin/env bash
set -e

echo "=== Installing Python dependencies ==="
pip install -r requirements.txt

echo "=== Installing Playwright Chromium (for undetected_chromedriver) ==="
PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.pw-browsers python -m playwright install chromium 2>&1
echo "Playwright Chromium path: $(pwd)/.pw-browsers"

echo "=== Build complete ==="
