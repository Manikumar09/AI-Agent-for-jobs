#!/usr/bin/env bash
set -euo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/playwright install chromium
if [[ ! -f .env ]]; then cp .env.example .env; fi
printf '%s\n' 'Setup complete. Run .venv/bin/job-agent init --resume /path/to/resume.docx'
