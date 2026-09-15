# 实现记录（阶段 3B）

> 记录各波次的实现过程、集成期发现的缺陷与修复方式，作为阶段 4 测试与后续维护的输入。
> 日期：2026-09-16 · 配套文档：`tasks.md`（状态回填）、`api-design.md`（状态列已回填为「已可用」）

---

## 1. 实现过程概览

| 波次 | 交付内容 | 后端测试 |
|---|---|---|
| Wave 0 | 工程骨架、vault 存储与链接层、写入队列与 SSE、审计与 git 底座、LLM 客户端与成本记账、Schema | test_workspace / test_jobs / test_audit / test_llm |
| Wave 1 | 素材接入（web/pdf/note 解析器 + 生命周期服务）、编译引擎（生成 / 增量分区与矛盾 / 分段与成本上限）、素材与编译 API、前端四页 | test_ingest_* / test_compile_engine / test_sources_api / test_compile_api |
| Wave 2 | 页面 / 反链 / 搜索 / 图谱 / 分区读接口 + PAGE-005 ~ 008 | test_read_api |
| Wave 3 | 问答引擎、问答 API 与答案回填 + PAGE-001 / 009 | test_ask |
| Wave 4 | 体检五类扫描、体检 API 与修复 + PAGE-011 | test_lint |
| Wave 5 | 设置 / 成本 / 系统 API、PAGE-012、部署脚本、端到端验证、收尾 | test_settings_api + `code/scripts/e2e.sh` |

最终规模：后端 117 项 pytest 全部通过，`ruff check` 零告警；前端 `npm run build` 通过；
`code/scripts/e2e.sh` 端到端全绿（导入 → 编译 → 变更清单 → 问答 → 体检）。

---

## 2. 集成期发现的缺陷与修复（本轮收尾）

Wave 2~5 的提交信息曾给出「35/36 完成」的估计，实际盘点发现 **Wave 1 的 API 接口层
从未接线**：`api/sources.py` 与 `api/compile.py` 还是返回硬编码空值的路由桩，服务层
（ingest/compile）虽然实现并有单元测试，但 HTTP 入口不存在。本轮补齐并顺带完成
TASK-014 / 015 的引擎侧缺口。逐项记录如下。

### 2.1 素材 API（TASK-012）

- `GET /api/sources` 支持 `status` 逗号分隔多值筛选；`page/size` 分页，`size ≤ 200`。
- `POST /sources/web|note|pdf` 返回完整 `SourceDetail`（导入后经 `SourceService.get_source`
  补齐派生页与 `content_editable`），`compile: true` 时附带 `job_id`。
  设计文档中的 `/sources/url`、`/sources/upload` 保留为别名路由（前端使用 `/web`、`/pdf`）。
- `PATCH`（note 可改正文，web/pdf 传 content 返回 422）、软删除 / 恢复、重编译、
  原件下载（`?download=1` 回文件流，默认返回 `{path, opened:false}`）。
- 上传限流：超过 100 MB 返回 `E_VALIDATION` 并说明上限。

### 2.2 编译 API 与变更清单（TASK-016）

- `POST /api/compile`：空请求体按「编译全部待编译」处理（前端「立即编译」的语义）。
  「待编译」= `status=stale`，或 `normal` 且 frontmatter 无 `compiled_at`。
  编译成功后引擎回写 `compiled_at`，避免「全部编译」每次全量重跑。
- `GET /api/compile/current` 返回完整 `JobSnapshot`（含步骤条 / 当前素材页 / 成本）。
  有活动任务优先，否则回最近一次编译任务，全空才返回 `idle`。
- `GET /api/changes` 读取 `.llmwiki/compile/{job_id}.json` manifest；
  `cost` 从 vault 成本账本按 `job_id` 汇总。

### 2.3 编译引擎扩展（TASK-014 / 015）

- **分区变更**：同源更新时对比旧 `zone`，变化记 `zone_changed` 并保留 `zone_before`；
  `human_edited` 页面继续走改名保护，不由编译改写。
- **矛盾标记**：`contradictions` 同时进摘要页 frontmatter（lint 扫描器直接消费）
  和正文「矛盾记录」小节。
- **长文分段**：超过 `segment_threshold_chars`（默认 24000）的素材先按段落边界分段，
  逐段摘要（围观页步骤条停在「生成摘要页」），再合成一次最终编译请求。
  未超阈值保持单次调用（有测试断言调用次数不增加）。
- **成本上限**：每次 LLM 调用前检查本任务累计花费，超过 `max_cost_per_task_usd`
  立即中止并置任务失败，原因含上限与已花费金额。
- **失败隔离**：单个素材编译失败不再拖垮整个任务——标记素材 `failed` + 失败原因，
  其余素材继续；全部失败时任务整体失败并抛出首个业务错误；部分失败时任务
  `done` 且 `failed_sources` 进入变更清单。

### 2.4 契约缺口补齐

- `PUT /api/settings/api-key`（API-039）：密钥单独写入，只回显末 4 位。
- `GET /api/costs`（API-042 设计路径）：与 `/api/settings/costs` 同一实现的路由别名。
- `GET /api/system/bootstrap`：`pending_lint_count` / `failed_source_count` /
  `stale_source_count` 从硬编码 0 改为真实统计（体检报告 + 素材四态计数）。

### 2.5 前端接线核对

- Wave 1 四页与后端路径 / 载荷形状逐一对上；`npm run build` 通过。
- 修复 `SourceDetailPage` 原件下载链接缺少 `?download=1`（否则点击会下载到 JSON）。
- 视觉验收项（1440×900 布局、断线重连体验等）留待阶段 4，TASK-017 ~ 020 标「待验证」。

---

## 3. 端到端验证（TASK-035）

`code/scripts/e2e.sh` + `code/scripts/e2e_mock_llm.py`：

- mock LLM 是仅标准库的 OpenAI 兼容服务器，按 system 提示词区分编译 / 分段 / 问答
  三类请求并返回确定性 JSON，因此 E2E 全程无外部网络依赖、可重复执行。
- 配置隔离：新增 `LLMWIKI_CONFIG_DIR` 环境变量覆盖应用配置目录（macOS 默认
  `~/Library/Application Support/llmwiki/`），E2E 在临时目录写入独立的
  `settings.json` 与 vault，不触碰用户真实配置。
- 脚本先自检 mock LLM 可用再跑流程；任一步失败打印服务端日志尾部并以非 0 退出。
- 已验证连续两次执行均通过且临时目录无残留（幂等）。

---

## 4. 集成期踩坑（供阶段 4 参考）

1. **TestClient 每次请求一个新事件循环**：`TestClient` 不加 `with client:` 时，
   每个请求各建一个 loop，请求结束即销毁——后台编译 worker 在 await 点被取消，
   任务永远停在 `running` 且 `finished_at` 已写入，极具迷惑性。涉及后台任务的接口测试
   必须用 `with client:` 让所有请求共享同一 loop（`test_ask.py` 早已如此，本轮复踩）。
2. **「已实现」要查到 HTTP 层**：服务层有代码、有测试 ≠ 接口可用。本次盘点以
   `grep 路由装饰器` + 前端调用清单对照，才发现 Wave 1 API 桩。验收必须穿透到
   前端实际请求的路径。
3. **bash 中 `$VAR` 紧邻全角字符会吞变量名**：`$LLM_PORT）` 被解析成一个更长的
   变量名导致 unbound variable。双引号内一律写 `${VAR}`。
4. **heredoc 会覆盖管道 stdin**：`echo "$JSON" | python - <<EOF` 里
   `json.load(sys.stdin)` 读到的是空（脚本本身来自 heredoc）。JSON 走临时文件传参更稳。
5. **多素材编译顺序由文件名排序决定**：`raw/*.md` 按文件名排序编译，测试里
   「哪个素材先失败」要用可排序的标题控制，不能靠中文语义直觉。
6. **`_find_source_path` 要求素材 id 是 12 位十六进制**：mock 数据用 `web123456789`
   这类含非 hex 字符的 id 会在校验层 422，报错位置与直觉不符。
