#!/usr/bin/env bash
# AtlasWiki 启动脚本（macOS / Linux）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIST="$REPO_ROOT/frontend/dist"

# 检查前端构建产物
if [ ! -f "$FRONTEND_DIST/index.html" ]; then
  echo "⚠️  未找到前端构建产物，请先执行:"
  echo "    cd frontend && npm install && npm run build"
  echo "然后重新运行本脚本。"
  exit 1
fi

echo "🚀 启动 AtlasWiki..."
cd "$BACKEND_DIR"
exec uv run atlaswiki
