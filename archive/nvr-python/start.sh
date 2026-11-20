#!/bin/sh
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt --quiet 2>/dev/null || python3 -m pip install -r requirements.txt --quiet --break-system-packages
python3 app.py "$@"
