#!/usr/bin/env bash
set -e

echo "=== Installing Google Chrome and Xvfb ==="

apt-get update -qq
apt-get install -y -qq wget gnupg xvfb 2>/dev/null || true

# Install Chrome
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - 2>/dev/null || true
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list
apt-get update -qq
apt-get install -y -qq google-chrome-stable 2>/dev/null || true

echo "=== Chrome version ==="
google-chrome --version || echo "Chrome not installed"

echo "=== Installing Python dependencies ==="
pip install -r requirements.txt

echo "=== Installing Playwright browsers ==="
python -m playwright install chromium 2>/dev/null || true

echo "=== Build complete ==="
