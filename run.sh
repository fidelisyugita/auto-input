#!/bin/bash
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt -q
python3 -m playwright install chromium
python3 main.py "$@"
