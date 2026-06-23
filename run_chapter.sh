#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

PYTHON_BIN="/Users/ppp/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

usage() {
  cat <<'EOF'
用法:
  ./run_chapter.sh <章节号|all> <区域经理工号> <月份> [额外参数]

示例:
  ./run_chapter.sh 3 86002542 202606
  ./run_chapter.sh all 86002542 202606
  ./run_chapter.sh 5 86002542 202606 --skip-api --fixture Data/fixtures/chapter5_mock.json

第一次使用:
  cp .env.example .env
  然后把 .env 里的 SKSHU_BI_API_KEY 改成真实 apikey
EOF
}

if [ "$#" -lt 3 ]; then
  usage
  exit 1
fi

CHAPTER="$1"
JOB_ID="$2"
CALMONTH="$3"
shift 3

HAS_INLINE_API_KEY=0
HAS_SKIP_API=0
for arg in "$@"; do
  if [ "$arg" = "--api-key" ]; then
    HAS_INLINE_API_KEY=1
  fi
  if [ "$arg" = "--skip-api" ]; then
    HAS_SKIP_API=1
  fi
done

if [ "$HAS_SKIP_API" -eq 0 ] && [ "$HAS_INLINE_API_KEY" -eq 0 ] && [ -z "${SKSHU_BI_API_KEY:-}" ]; then
  cat >&2 <<'EOF'
缺少接口 apikey。

请先执行:
  cp .env.example .env
  open -e .env

然后把 SKSHU_BI_API_KEY 改成真实 apikey，再重新运行命令。
EOF
  exit 1
fi

run_one() {
  local chapter="$1"
  shift
  local script="run_chapter${chapter}_api.py"
  if [ ! -f "$script" ]; then
    echo "找不到脚本: $script" >&2
    exit 1
  fi
  echo "==> 生成第 ${chapter} 章: job-id=${JOB_ID}, calmonth=${CALMONTH}"
  "$PYTHON_BIN" "$script" --job-id "$JOB_ID" --calmonth "$CALMONTH" "$@"
}

case "$CHAPTER" in
  2|3|4|5|6|7|8)
    run_one "$CHAPTER" "$@"
    ;;
  all)
    run_one 2 "$@"
    run_one 3 "$@"
    run_one 4 "$@"
    run_one 5 "$@"
    run_one 6 "$@"
    run_one 7 "$@"
    run_one 8 "$@"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "章节号只能是 2、3、4、5、6、7、8 或 all。" >&2
    usage
    exit 1
    ;;
esac
