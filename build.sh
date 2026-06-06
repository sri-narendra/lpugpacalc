#!/usr/bin/env bash
set -e

echo "=== Installing Python dependencies ==="
pip install -r requirements.txt

echo "=== Installing Playwright Chromium (for undetected_chromedriver) ==="
PLAYWRIGHT_BROWSERS_PATH="$(pwd)/.pw-browsers" python -m playwright install chromium 2>&1 || echo "[WARN] Playwright install failed — fallback to curl_cffi will be used"
echo "=== Playwright Chromium path: $(pwd)/.pw-browsers ==="
ls -la "$(pwd)/.pw-browsers"/chromium-*/chrome-linux/chrome 2>/dev/null && echo "[OK] Chromium binary found" || echo "[WARN] No Chromium binary at .pw-browsers"

echo "=== Build complete ==="
