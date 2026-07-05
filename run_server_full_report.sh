#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'EOF'
用法:
  ./run_server_full_report.sh <工号> <取数月份YYYYMM> <报告截止月份YYYYMM> [姓名]

示例:
  ./run_server_full_report.sh 06427 202606 202605 刘晨

首次运行会创建 .env，请填写 SKSHU_BI_API_KEY 和 AI_API_KEY 后重跑。
EOF
}

if [ "$#" -lt 3 ]; then
  usage
  exit 1
fi

JOB_ID="$1"
CALMONTH="$2"
REPORT_PERIOD="$3"
NAME="${4:-}"

if [ ! -f ".env" ]; then
  cp ".env.example" ".env"
  cat >&2 <<'EOF'
已创建 .env。
请填写 SKSHU_BI_API_KEY 和 AI_API_KEY 后，重新执行本命令。
EOF
  exit 1
fi

set -a
# shellcheck disable=SC1091
source ".env"
set +a

if [ -z "${SKSHU_BI_API_KEY:-}" ] || [ "${SKSHU_BI_API_KEY}" = "填写你的apikey" ]; then
  echo ".env 里缺少有效的 SKSHU_BI_API_KEY" >&2
  exit 1
fi

if [ -z "${AI_API_KEY:-}" ] || [ "${AI_API_KEY}" = "填写你的大模型apikey" ]; then
  echo ".env 里缺少有效的 AI_API_KEY" >&2
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi

".venv/bin/python" -m pip install --upgrade pip
".venv/bin/python" -m pip install -r requirements.txt
".venv/bin/python" -m playwright install chromium

".venv/bin/python" run_full_report_strict.py \
  --job-id "$JOB_ID" \
  --calmonth "$CALMONTH" \
  --report-period "$REPORT_PERIOD" \
  --name "$NAME" \
  --output-root "Reports/server_live_strict" \
  --timeout 60
