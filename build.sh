#!/usr/bin/env bash
set -e

echo "=== Installing Python dependencies ==="
pip install -r requirements.txt

echo "=== Installing Playwright Chromium (for undetected_chromedriver) ==="
PLAYWRIGHT_BROWSERS_PATH="$(pwd)/.pw-browsers" python -m playwright install chromium 2>&1 || echo "[WARN] Playwright install failed — fallback to curl_cffi will be used"
echo "=== Playwright Chromium path: $(pwd)/.pw-browsers ==="
BROWSER_DIR="$(pwd)/.pw-browsers"
echo "=== Contents of $BROWSER_DIR ==="
find "$BROWSER_DIR" -type f -name "chrome" 2>/dev/null || echo "(no chrome binary found)"
echo "=== Full tree ==="
ls -R "$BROWSER_DIR"/chromium-*/ 2>/dev/null | head -20 || echo "(empty)"

echo "=== Build complete ==="
