#!/usr/bin/env bash
# LLM Wiki 启动脚本
#   ./run.sh           启动服务
#   ./run.sh --setup   创建本地 .venv 并安装依赖
#   ./run.sh --port N  指定端口
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PY="${LLMWIKI_PYTHON:-}"
PORT=""

for arg in "$@"; do
  case "$arg" in
    --port=*) PORT="${arg#--port=}" ;;
  esac
done
if [[ "${1:-}" == "--port" && -n "${2:-}" ]]; then PORT="$2"; fi

pick_python() {
  if [[ -n "$PY" && -x "$PY" ]]; then printf '%s' "$PY"; return; fi
  if [[ -x "$ROOT/.venv/bin/python" ]]; then printf '%s' "$ROOT/.venv/bin/python"; return; fi
  if [[ -x "$HOME/.workbuddy-ai/binaries/python/envs/llmwiki/bin/python" ]]; then
    printf '%s' "$HOME/.workbuddy-ai/binaries/python/envs/llmwiki/bin/python"; return
  fi
  command -v python3
}

install_into() {
  local target_python="$1"
  echo "==> 安装依赖到 $(dirname "$(dirname "$target_python")")"
  "$target_python" -m pip install --upgrade pip >/dev/null 2>&1 || true
  if ! "$target_python" -m pip install --no-cache-dir -r requirements.txt; then
    echo "==> 常规安装失败，尝试手动安装 jieba（pip 的构建目录偶发冲突）"
    local tmp; tmp="$(mktemp -d)"
    local url="https://files.pythonhosted.org/packages/c6/cb/18eeb235f833b726522d7ebed54f2278ce28ba9438e3135ab0278d9792a2/jieba-0.42.1.tar.gz"
    curl -sL -o "$tmp/jieba.tar.gz" "$url"
    tar -xzf "$tmp/jieba.tar.gz" -C "$tmp"
    local sp; sp="$("$target_python" -c 'import site;print(site.getsitepackages()[0])')"
    cp -R "$tmp/jieba-0.42.1/jieba" "$sp/"
    rm -rf "$tmp"
    "$target_python" -m pip install --no-cache-dir -r requirements.txt
  fi
}

if [[ "${1:-}" == "--setup" ]]; then
  if [[ ! -d "$ROOT/.venv" ]]; then
    BASE="${LLMWIKI_BASE_PYTHON:-python3}"
    "$BASE" -m venv "$ROOT/.venv"
  fi
  install_into "$ROOT/.venv/bin/python"
  echo "==> 完成。运行 ./run.sh 启动。"
  exit 0
fi

PY="$(pick_python)"
if [[ -z "$PY" ]]; then
  echo "找不到可用的 Python，请安装 Python 3.11+ 后重试。" >&2
  exit 1
fi

if ! "$PY" - <<'PYCHECK' 2>/dev/null
import importlib, sys
missing = [m for m in ("fastapi", "uvicorn", "httpx", "bs4", "lxml", "docx", "jieba", "yaml")
           if importlib.util.find_spec(m) is None]
sys.exit(1 if missing else 0)
PYCHECK
then
  echo "==> 缺少依赖，正在安装（首次运行需要一两分钟）"
  install_into "$PY"
fi

HOST="$("$PY" -c 'from app.config import load_config;print(load_config()["server"]["host"])' 2>/dev/null || echo 127.0.0.1)"
if [[ -z "$PORT" ]]; then
  PORT="$("$PY" -c 'from app.config import load_config;print(load_config()["server"]["port"])' 2>/dev/null || echo 8765)"
fi

echo ""
echo "  LLM Wiki  →  http://${HOST}:${PORT}"
echo "  知识库    →  $ROOT/data/kb"
echo ""
exec "$PY" -m uvicorn app.main:app --host "$HOST" --port "$PORT" --log-level info
