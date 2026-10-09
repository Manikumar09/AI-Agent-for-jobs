#!/usr/bin/env bash
set -euo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
exec .venv/bin/python -m jobagent.cli --home "${JOB_AGENT_HOME:-$PWD}" run "$@"
