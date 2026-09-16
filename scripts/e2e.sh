#!/usr/bin/env bash
# TASK-035 端到端验证脚本：
# 建临时 vault → 启动 mock LLM 与服务 → 导入笔记 → 编译 → 断言页面与索引
# → 提问断言引用真实存在 → 跑体检 → 关闭服务 → 清理。
#
# 特性：全流程使用临时目录（重复执行不残留状态）；任一步失败会打印
# 服务端日志尾部并以非 0 退出码结束。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"

# --- Python 解释器：优先用已建好的 venv，其次退回 uv run ---
if [ -x "$BACKEND_DIR/.venv/bin/python" ]; then
  PY="$BACKEND_DIR/.venv/bin/python"
else
  PY="uv run --project $BACKEND_DIR python"
fi

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/atlaswiki-e2e.XXXXXX")"
VAULT_DIR="$WORK_DIR/vault"
CONFIG_DIR="$WORK_DIR/config"
APP_LOG="$WORK_DIR/app.log"
LLM_LOG="$WORK_DIR/mock_llm.log"
APP_PID=""
LLM_PID=""

cleanup() {
  [ -n "$APP_PID" ] && kill "$APP_PID" 2>/dev/null || true
  [ -n "$LLM_PID" ] && kill "$LLM_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

fail() {
  echo "❌ E2E 失败：$1" >&2
  echo "----- 服务日志尾部（${APP_LOG}）-----" >&2
  tail -n 40 "$APP_LOG" 2>/dev/null >&2 || true
  echo "----- mock LLM 日志尾部（${LLM_LOG}）-----" >&2
  tail -n 20 "$LLM_LOG" 2>/dev/null >&2 || true
  exit 1
}

assert_eq() { # assert_eq <描述> <期望> <实际>
  if [ "$2" != "$3" ]; then
    fail "$1：期望 [$2]，实际 [$3]"
  fi
}

step() { echo "▶ $1"; }

# --- 1. 准备临时 vault 与隔离配置（不触碰用户设置） ---
step "准备临时 vault 与配置：$WORK_DIR"
mkdir -p "$VAULT_DIR/wiki" "$VAULT_DIR/raw" "$CONFIG_DIR"
LLM_PORT=$( "$PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()' )
APP_PORT=$( "$PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()' )
"$PY" - "$CONFIG_DIR" "$VAULT_DIR" "$LLM_PORT" <<'PYEOF'
import json, sys
from pathlib import Path

config_dir, vault, llm_port = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
settings = {
    "vault_path": vault,
    "llm": {
        "provider": "openai-compatible",
        "base_url": f"http://127.0.0.1:{llm_port}/v1",
        "model": "mock-model",
        "api_key": "e2e-mock-key",
    },
    "git": {"auto_commit": True, "auto_push": False},
}
(config_dir / "settings.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
PYEOF

# --- 2. 启动 mock LLM 与应用服务 ---
step "启动 mock LLM（端口 ${LLM_PORT}）与应用服务（端口 ${APP_PORT}）"
( cd "$BACKEND_DIR" && exec "$PY" "$SCRIPT_DIR/e2e_mock_llm.py" --port "$LLM_PORT" ) >"$LLM_LOG" 2>&1 &
LLM_PID=$!
( cd "$BACKEND_DIR" && ATLASWIKI_CONFIG_DIR="$CONFIG_DIR" exec "$PY" -m uvicorn atlaswiki.main:app --host 127.0.0.1 --port "$APP_PORT" --log-level warning ) >"$APP_LOG" 2>&1 &
APP_PID=$!

API="http://127.0.0.1:$APP_PORT/api"

step "等待服务就绪"
for _ in $(seq 1 60); do
  if curl -fsS "$API/system/health" >/dev/null 2>&1; then break; fi
  kill -0 "$LLM_PID" 2>/dev/null || fail "mock LLM 提前退出"
  kill -0 "$APP_PID" 2>/dev/null || fail "应用服务提前退出"
  sleep 0.5
done
curl -fsS "$API/system/health" >/dev/null 2>&1 || fail "服务未就绪"

# --- 3. 环境自检（脚本必须先证明自己可用） ---
step "自检 mock LLM 可响应"
LLM_HEALTH=$(curl -fsS "http://127.0.0.1:$LLM_PORT/healthz" 2>/dev/null || echo "unreachable")
assert_eq "mock LLM 健康检查" '{"ok": true}' "$LLM_HEALTH"

# --- 4. 导入素材（三类素材之一：手写笔记，无外部网络依赖） ---
step "导入手写笔记素材"
IMPORT_BODY='{"title":"测试素材","content":"这是一篇端到端验证笔记，讨论测试概念与测试实体的关系。","tags":["e2e"]}'
IMPORTED=$(curl -fsS -X POST "$API/sources/note" -H 'Content-Type: application/json' -d "$IMPORT_BODY" || fail "导入笔记接口失败")
SOURCE_ID=$(echo "$IMPORTED" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["id"])')
[ -n "$SOURCE_ID" ] || fail "导入成功但未返回素材 id"
echo "  素材 id：$SOURCE_ID"

# --- 5. 触发编译并等待完成 ---
step "触发编译并等待完成"
COMPILE=$(curl -fsS -X POST "$API/compile" -H 'Content-Type: application/json' -d '{}' || fail "触发编译失败")
JOB_ID=$(echo "$COMPILE" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')
echo "  编译任务：$JOB_ID"

STATUS=""
for _ in $(seq 1 60); do
  SNAPSHOT=$(curl -fsS "$API/compile/current")
  STATUS=$(echo "$SNAPSHOT" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  [ "$STATUS" = "done" ] && break
  [ "$STATUS" = "failed" ] && { echo "  快照：$SNAPSHOT"; fail "编译任务失败"; }
  sleep 0.5
done
assert_eq "编译任务状态" "done" "$STATUS"

# --- 6. 断言 wiki 出现页面与索引（直接检查磁盘文件） ---
step "断言 wiki 页面与索引落盘"
for f in "wiki/index.md" "wiki/sources/测试素材摘要.md" "wiki/concepts/测试概念.md" "wiki/entities/测试实体.md"; do
  [ -f "$VAULT_DIR/$f" ] || fail "编译产物缺失：$f"
done
"$PY" - "$VAULT_DIR/wiki/index.md" <<'PYEOF'
import sys
index = open(sys.argv[1], encoding="utf-8").read()
missing = [name for name in ("测试素材摘要", "测试概念", "测试实体") if f"[[{name}]]" not in index]
if missing:
    raise SystemExit(f"索引缺少页面：{missing}")
PYEOF
echo "  页面与索引 ✔"

# --- 7. 断言变更清单 ---
step "断言变更清单"
CHANGES=$(curl -fsS "$API/changes") || fail "变更清单接口失败"
CHANGES_FILE="$WORK_DIR/changes.json"
printf '%s' "$CHANGES" > "$CHANGES_FILE"
"$PY" - "$CHANGES_FILE" <<'PYEOF' || fail "变更清单断言失败"
import json, sys
changes = json.load(open(sys.argv[1], encoding="utf-8"))
assert changes["status"] == "done", changes["status"]
created = [item for item in changes["items"] if item["change_type"] == "created"]
assert len(created) >= 3, changes["items"]
assert changes["failed_sources"] == [], changes["failed_sources"]
print("  变更清单 ✔（created =", len(created), "）")
PYEOF

# --- 8. 提问并断言引用页真实存在 ---
step "提问并断言引用"
ANSWER=$(curl -fsS -X POST "$API/ask" -H 'Content-Type: application/json' -d '{"question":"什么是测试概念？"}') || fail "问答接口失败"
ANSWER_FILE="$WORK_DIR/answer.json"
printf '%s' "$ANSWER" > "$ANSWER_FILE"
"$PY" - "$ANSWER_FILE" "$API" <<'PYEOF' || fail "问答断言失败"
import json, sys
import urllib.parse
import urllib.request

answer = json.load(open(sys.argv[1], encoding="utf-8"))
api = sys.argv[2]
assert answer["sufficient"] is True, answer
assert answer["pages_considered"] >= 1, answer
assert answer["citations"], answer
for citation in answer["citations"]:
    page = citation["page"]
    with urllib.request.urlopen(f"{api}/pages/{urllib.parse.quote(page)}") as response:
        assert response.status == 200, page
print("  引用页全部真实存在 ✔（citations =", len(answer["citations"]), "）")
PYEOF

# --- 9. 跑体检并断言五类检查可执行 ---
step "跑体检并断言报告可生成"
curl -fsS -X POST "$API/lint/run" >/dev/null || fail "触发体检失败"
REPORT=$(curl -fsS "$API/lint/report") || fail "体检报告不可得"
REPORT_FILE="$WORK_DIR/lint-report.json"
printf '%s' "$REPORT" > "$REPORT_FILE"
"$PY" - "$REPORT_FILE" <<'PYEOF' || fail "体检报告断言失败"
import json, sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report.get("generated_at"), report
issues = report.get("issues")
assert isinstance(issues, list), report
metrics = report.get("metrics", {})
assert metrics.get("issue_count") == len(issues), metrics
assert set(metrics.get("kind_counts", {})) <= {
    "contradiction", "orphan", "dead_link", "missing_index", "zone_mix"
}, metrics
print("  体检 ✔（issue_count =", metrics.get("issue_count"), "）")
PYEOF

# --- 10. 收尾 ---
step "关闭服务"
kill "$APP_PID" "$LLM_PID" 2>/dev/null || true
wait "$APP_PID" 2>/dev/null || true
wait "$LLM_PID" 2>/dev/null || true
APP_PID=""
LLM_PID=""

echo "✅ E2E 全部通过：导入 → 编译 → 变更清单 → 问答 → 体检"
