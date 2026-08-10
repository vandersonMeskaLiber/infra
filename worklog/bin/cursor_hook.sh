#!/bin/bash
# Wrapper do hook Cursor (fail-open).
set -u
/usr/bin/python3 /Users/vandersonmeska/.worklog/bin/cursor_log.py || echo '{}'
exit 0
