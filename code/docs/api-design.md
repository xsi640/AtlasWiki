# API 设计

> 状态：**已定稿**，作为阶段 4 测试阶段的输入
> 方法：SoloForge 阶段 3B v0.3
> 日期：2026-09-15
> 输入：`code/docs/tech-architecture.md`（第 6 节接口约定）、`code/docs/ux-design.md`

---

## 1. 接口约定

### 1.1 形态与形态说明

本项目是**本机单体 Web 应用**，对外接口全部为 HTTP + JSON，进度推送为 SSE。无本地方法接口、无 CLI 接口、无第三方对外接口。

一切以文件为准：HTTP 接口只是文件系统与 LLM 之上的薄壳，所有接口的最终效果都体现在 vault 目录的 Markdown 文件上。

### 1.2 通用规则

| 项 | 约定 |
|---|---|
| 基路径 | 业务接口统一 `/api`；前端静态资源挂 `/`（非 `/api` 路径全部回落到 SPA 入口） |
| 鉴权 | **无**。服务只绑定 `127.0.0.1`，本机单人使用 |
| 请求体 | `application/json`，文件上传为 `multipart/form-data` |
| 编码 | 全程 UTF-8；响应 `application/json; charset=utf-8` |
| 时间 | ISO 8601 带时区（`2026-09-15T14:03:11+08:00`），字段名以 `_at` 结尾 |
| 命名 | JSON 字段用 `snake_case`（与后端 Pydantic 模型、frontmatter 字段保持一致，避免多层命名转换） |
| 列表分页 | `page`（从 1 起）与 `size`（默认 50，上限 200）；响应含 `total` |
| 幂等 | 所有 `GET` 幂等；`POST /api/compile` 等触发型接口靠写锁串行化，重复触发返回 `E_JOB_CONFLICT` |
| 路径参数 | 页面以**页面名**（wiki 文件去掉 `.md` 的部分）标识，需 URL 编码；素材以无法变动的 `id` 标识 |

### 1.3 页面名与素材 id

- **页面名**：即 `wiki/` 下级目录中的 Markdown 文件名（不含 `.md`）。`[[链接]]` 的目标就是页面名，与图谱节点 id 一致。用户可通过编辑 human 页面标题触发重命名，重命名由 MODULE-003 统一处理并同步更新引用。
- **素材 id**：素材文件名的 slug，另有 frontmatter 中的 `id` 字段（12 位十六进制）作为稳定标识。**API 一律用 `id`**，改标题不影响引用。
- **路径安全**：所有路径类参数都必须是 vault 内相对路径。服务端做归一化（解析 `..`、绝对路径、盘符、UNC）后校验仍位于 vault 内，否则返回 `E_PATH_OUT_OF_VAULT`。

### 1.4 统一错误响应

```json
{
  "error": {
    "code": "E_LLM_TIMEOUT",
    "message": "模型调用超时",
    "details": { "source_id": "a1b2c3d4e5f6" }
  }
}
```

`details` 可为空对象；字段级校验错误固定使用 `details.fields`：

```json
{
  "error": {
    "code": "E_VALIDATION",
    "message": "参数校验失败",
    "details": { "fields": [ { "field": "url", "reason": "必须是 http/https 链接" } ] }
  }
}
```

### 1.5 写入任务与并发

所有会产生文件写入的操作（导入、编译、编辑、删除、修复、回填）都进入**单一写入队列**：

- 队列空闲时立即执行，返回 `job_id`；
- 队列忙时仍接受请求并排队（编译类除外，见下），前端通过 SSE 或 `GET /api/compile/current` 观察进度；
- 同一素材已在该队列中时，再次触发返回 `E_SOURCE_BUSY`（对应 ERROR-009）；
- 已有编译任务运行时，再次 `POST /api/compile` 返回 `E_JOB_CONFLICT`。

`GET` 类接口不写盘（体检报告与搜索为纯内存计算），可并发执行。

---

## 2. 接口清单

「状态」列与 `tasks.md` 的任务状态对齐，实现完成后统一回填。

### 2.1 系统

| 接口编号 | 名称 | 形态 | 对应模块 | 用途 | 状态 |
|---|---|---|---|---|---|
| API-001 | 健康检查 | HTTP GET `/api/system/health` | MODULE-009 | 返回版本、vault 状态、LLM 配置状态、队列状态 | 已可用 |
| API-002 | 冷启动探测 | HTTP GET `/api/system/bootstrap` | MODULE-004 | 判定空库（BRANCH-001）、待处理体检数与失败素材数 | 已可用 |
| API-003 | 打开数据文件夹 | HTTP POST `/api/system/open-folder` | MODULE-004 | 用系统文件管理器打开 vault 目录（G-7 / INTERACTION-017） | 已可用 |

**API-001 响应**

```json
{
  "version": "0.1.0",
  "vault": { "path": "D:\\kb", "initialized": true, "page_count": 18, "source_count": 6 },
  "llm": { "configured": true, "provider": "openai-compatible", "model": "gpt-4o-mini" },
  "jobs": { "running": false, "queued": 0, "current_job_id": null }
}
```

`llm.configured` 为 `false` 时前端在设置页与编译入口给出提示；后端仍可启动（离线降级）。

**API-002 响应**

```json
{
  "vault_initialized": true,
  "isEmpty": false,
  "page_count": 18,
  "pending_lint_count": 3,
  "failed_source_count": 0,
  "stale_source_count": 1
}
```

`isEmpty` 为 `true` 时首页渲染 PAGE-002 内容（STATE-006 / BRANCH-001）。字段名按前端消费习惯，统一为 `vault_initialized` / `page_count` / `pending_lint_count` / `failed_source_count` / `stale_source_count` / `is_empty`。

**API-003 响应**：`{ "opened": true, "path": "D:\\kb" }`。实现方式见 TASK-TBD-003。

### 2.2 页面与图谱（PAGE-005 / 006）

| 接口编号 | 名称 | 形态 | 对应模块 | 用途 | 状态 |
|---|---|---|---|---|---|
| API-004 | 页面列表 | HTTP GET `/api/pages` | MODULE-004 | 按分区/类型筛选的页面列表 | 已可用 |
| API-005 | 页面详情 | HTTP GET `/api/pages/{name}` | MODULE-004 | 正文、元数据、出链、反链、来源区 | 已可用 |
| API-006 | 保存人工编辑 | HTTP PUT `/api/pages/{name}` | MODULE-004 | 人工编辑正文，写 `human_edited` 标记（INTERACTION-016） | 已可用 |
| API-007 | 修改分区 | HTTP PATCH `/api/pages/{name}/zone` | MODULE-004 | 一键改分区（INTERACTION-011 / BRANCH-004） | 已可用 |
| API-008 | 反向链接 | HTTP GET `/api/pages/{name}/backlinks` | MODULE-003 | 反链面板数据 | 已可用 |
| API-009 | 页面 diff | HTTP GET `/api/pages/{name}/diff` | MODULE-008 | 单页差异（变更清单展开用） | 已可用 |
| API-010 | 图谱数据 | HTTP GET `/api/graph` | MODULE-004 | 节点与边，支持分区筛选与 1/2 层深度（UX-TBD-004） | 已可用 |
| API-011 | 分区列表 | HTTP GET `/api/zones` | MODULE-004 | 分区及其页面数 | 已可用 |
| API-012 | 分区内页面 | HTTP GET `/api/zones/{name}/pages` | MODULE-004 | 分区浏览（PAGE-007） | 已可用 |
| API-013 | 全局搜索 | HTTP GET `/api/search` | MODULE-004 | 标题与正文命中，返回片段 | 已可用 |

**API-004 查询参数**：`zone`、`type`、`page`、`size`。响应：

```json
{
  "items": [
    {
      "name": "增量维护",
      "title": "增量维护",
      "type": "concept",
      "zone": "知识管理",
      "source_type": "compiled",
      "human_edited": false,
      "status": "active",
      "link_count": 5,
      "backlink_count": 3,
      "updated_at": "2026-09-15T14:03:11+08:00"
    }
  ],
  "total": 18
}
```

**API-005 响应（`PageDetail`）**

```json
{
  "name": "增量维护",
  "title": "增量维护",
  "type": "concept",
  "zone": "知识管理",
  "source_type": "compiled",
  "human_edited": true,
  "status": "active",
  "created_at": "2026-09-15T13:00:00+08:00",
  "updated_at": "2026-09-15T14:03:11+08:00",
  "origin_source": "a1b2c3d4e5f6",
  "content": "## 定义\n\n……",
  "links": ["知识编译", "向量数据库"],
  "backlinks": [{ "name": "LLM Wiki", "title": "LLM Wiki" }],
  "sources": [{ "id": "a1b2c3d4e5f6", "title": "为什么 LLM Wiki 更适合个人知识库", "kind": "web" }]
}
```

- `content` 是 frontmatter 之后的正文原文（Markdown），前端用 react-markdown 渲染。
- `links` 为出链页面名；`backlinks` 复用 `PageSummary` 的精简形态。
- `sources` 是来源区数据：由 `origin_source` 与页面正文中的素材引用推导。

**API-006 请求**：`{ "content": "……" }`。响应为更新后的 `PageDetail`。写入时 `human_edited` 置 `true`。

**API-007 请求**：`{ "zone": "知识管理" }`。响应 `{ "name": "增量维护", "zone": "知识管理", "zone_before": "RAG", "changed_at": "…" }`。改动记入 MODULE-008 变更记录（REC-### 语义，可被 git 回退）。

**API-010 查询参数**：`zone`（可选）、`depth`（1 或 2，默认 1）、`center`（可选，页面名）。响应：

```json
{
  "nodes": [
    { "id": "增量维护", "title": "增量维护", "type": "concept", "zone": "知识管理", "degree": 8, "status": "active" }
  ],
  "edges": [ { "source": "增量维护", "target": "知识编译" } ],
  "truncated": false,
  "node_count": 18,
  "edge_count": 78
}
```

`truncated` 为 `true` 表示因 `depth` 限制未展示全部节点，前端提示可切换深度。孤立节点必须在节点集合中保留（STATUS 为 `active` 的孤儿页仍要出现在图谱里），否则用户无法发现孤儿页。

**API-013 查询参数**：`q`（必填，长度 1~100）、`page`、`size`。响应：

```json
{
  "items": [
    { "name": "知识编译", "title": "知识编译", "zone": "知识管理", "type": "concept", "snippet": "……把知识<mark>编译</mark>进页面……" }
  ],
  "total": 4,
  "query": "编译"
}
```

`snippet` 由后端生成：命中位置前后各约 40 字，命中词用 `<mark>` 包裹。前端用该片段渲染高亮，不再二次匹配。

### 2.3 素材（PAGE-002 / 010 / 013）

| 接口编号 | 名称 | 形态 | 对应模块 | 用途 | 状态 |
|---|---|---|---|---|---|
| API-014 | 素材列表 | HTTP GET `/api/sources` | MODULE-001 | 素材库总览，按状态筛选（INTERACTION-020） | 已可用 |
| API-015 | 导入网址 | HTTP POST `/api/sources/url` | MODULE-001 | 粘贴 URL 摄入（INTERACTION-003） | 已可用 |
| API-016 | 新建笔记 | HTTP POST `/api/sources/note` | MODULE-001 | 手写笔记成素材（INTERACTION-004） | 已可用 |
| API-017 | 上传文件 | HTTP POST `/api/sources/upload` | MODULE-001 | PDF 等文件上传（INTERACTION-002） | 已可用 |
| API-018 | 素材详情 | HTTP GET `/api/sources/{id}` | MODULE-001 | 原文页数据（PAGE-010） | 已可用 |
| API-019 | 编辑素材 | HTTP PATCH `/api/sources/{id}` | MODULE-001 | 笔记可改正文，其余只改元数据（INTERACTION-021） | 已可用 |
| API-020 | 软删除素材 | HTTP DELETE `/api/sources/{id}` | MODULE-001 | 二次确认后软删除（INTERACTION-018 / ERROR-010） | 已可用 |
| API-021 | 恢复素材 | HTTP POST `/api/sources/{id}/restore` | MODULE-001 | 从已删除恢复（INTERACTION-022） | 已可用 |
| API-022 | 重编译素材 | HTTP POST `/api/sources/{id}/recompile` | MODULE-001 | 对该素材重跑 ingest（INTERACTION-019 / BRANCH-006） | 已可用 |
| API-023 | 打开素材原件 | HTTP GET `/api/sources/{id}/asset` | MODULE-001 | PDF 原件以「打开本地文件」提供（UX-TBD-007） | 已可用 |

**API-014 查询参数**：`status`（`normal` / `failed` / `deleted` / `stale`，可多值）、`page`、`size`。响应：

```json
{
  "items": [
    {
      "id": "a1b2c3d4e5f6",
      "title": "为什么 LLM Wiki 更适合个人知识库",
      "kind": "web",
      "source_url": "https://example.com/post",
      "status": "stale",
      "tags": ["知识管理"],
      "author": "Ada",
      "published_at": "2026-08-01",
      "created_at": "2026-09-15T13:00:00+08:00",
      "updated_at": "2026-09-15T14:00:00+08:00",
      "derived_page_count": 4,
      "failure_reason": null
    }
  ],
  "total": 6,
  "counts": { "normal": 4, "failed": 0, "deleted": 1, "stale": 1 }
}
```

`counts` 供素材库页的筛选标签直接显示数量；`failure_reason` 仅在 `status = failed` 时非空（STATE-010）。

**API-015 请求**：`{ "url": "https://…", "title": null, "tags": [], "compile": false }`
**API-016 请求**：`{ "title": "…", "content": "…", "tags": [], "compile": false }`
**API-017 请求**：multipart，字段 `file`，可选 `title`、`tags`、`compile`

三者响应一致，返回 `SourceDetail`（见 API-018）。`compile: true` 时导入成功后立即排队编译，响应额外带 `"job_id": "…"`。

**重复导入**：命中同源（同 `source_url` 或同内容哈希）时返回 `E_DUPLICATE_SOURCE`（409），`details.existing` 给出已存在素材的 `id` 与 `title`，前端据此提供「重新编译」或「取消」（ERROR-003）。

**API-018 响应（`SourceDetail`）**

```json
{
  "id": "a1b2c3d4e5f6",
  "title": "为什么 LLM Wiki 更适合个人知识库",
  "kind": "web",
  "source_url": "https://example.com/post",
  "status": "stale",
  "tags": ["知识管理"],
  "author": "Ada",
  "published_at": "2026-08-01",
  "note": "值得反复看",
  "content": "……提取出的正文……",
  "content_editable": false,
  "asset_path": null,
  "raw_meta": { "extractor": "trafilatura", "lang": "zh" },
  "derived_pages": [ { "name": "LLM Wiki", "title": "LLM Wiki", "status": "active" } ],
  "created_at": "2026-09-15T13:00:00+08:00",
  "updated_at": "2026-09-15T14:00:00+08:00",
  "failure_reason": null
}
```

- `content_editable` 是**后端给出的权威判定**：`kind = note` 且不在编译中为 `true`；`web` / `pdf` 恒为 `false`（外部来源正文不可改）。
- 素材处于编译中时，`content_editable` 为 `false`，编辑接口返回 `E_SOURCE_BUSY`（ERROR-009）。
- `asset_path` 仅 PDF 等有原件的素材非空，API-023 用它提供下载/打开。

**API-019 请求**（部分更新，未提供的字段不动）：

```json
{ "title": "新标题", "tags": ["a"], "note": "备注", "author": "Ada", "published_at": "2026-08-01", "content": "仅 note 类可传" }
```

对 `web` / `pdf` 传 `content` 返回 `E_VALIDATION`，`details.fields` 说明正文不可编辑。保存成功后素材状态置 `stale`（BRANCH-006：不自动编译，等显式触发），响应带 `"needs_recompile": true` 供前端展示 CONTENT-007 文案。

**API-020 响应**：`{ "id": "…", "status": "deleted", "affected_page_count": 4, "affected_pages": ["LLM Wiki", "知识编译"] }`
前端在删除前先调 `GET /api/sources/{id}` 取 `derived_pages` 以展示「将影响 N 个页面」（ERROR-010）。删除**不级联硬删**，派生页与入链转由体检列出（U-12）。

**API-023 响应**：`{ "path": "D:\\kb\\raw\\assets\\xxx.pdf", "opened": false }`，或按 `?download=1` 直接返回文件流。默认返回路径，由前端触发「打开本地文件」。

### 2.4 编译与变更（PAGE-003 / 004）

| 接口编号 | 名称 | 形态 | 对应模块 | 用途 | 状态 |
|---|---|---|---|---|---|
| API-024 | 触发编译 | HTTP POST `/api/compile` | MODULE-002 | 对指定素材或全部待编译素材发动 ingest | 已可用 |
| API-025 | 当前任务 | HTTP GET `/api/compile/current` | MODULE-002 | 围观页快照，断线重连后恢复状态（ERROR-007） | 已可用 |
| API-026 | 任务详情 | HTTP GET `/api/compile/jobs/{job_id}` | MODULE-002 | 已完成任务的历史查询 | 已可用 |
| API-027 | 变更清单 | HTTP GET `/api/changes` | MODULE-008 | 本次改了哪些页面、新页面、分区结果（PAGE-004） | 已可用 |

**API-024 请求**：`{ "source_ids": ["a1b2c3…"], "all_pending": false }`。二者必选其一。响应 `{ "job_id": "job-20260915-1403", "queued_sources": 3 }`。

**API-025 响应（`JobSnapshot`）**——围观页（STATE-007）的唯一数据源：

```json
{
  "job_id": "job-20260915-1403",
  "status": "running",
  "kind": "compile",
  "total_sources": 3,
  "done_sources": 1,
  "current_source": { "id": "…", "title": "为什么 LLM Wiki 更适合个人知识库" },
  "current_page": "知识编译",
  "steps": [
    { "name": "读取素材原文", "state": "done" },
    { "name": "生成摘要页", "state": "done" },
    { "name": "更新概念页与实体页", "state": "running" },
    { "name": "重建索引与互链", "state": "pending" }
  ],
  "cost": { "currency": "USD", "total": 0.0421 },
  "started_at": "2026-09-15T14:03:11+08:00",
  "finished_at": null,
  "failure_reason": null,
  "can_leave": true
}
```

- `status` 取值：`queued` / `running` / `done` / `failed`。
- `cost` 只给累计金额，不给实时 token 数（UX-TBD-002）。
- `can_leave` 恒为 `true`，用于前端显示「可离开」（BRANCH-002）。
- 无任务时返回 `{ "job_id": null, "status": "idle" }`。

**API-027 查询参数**：`job_id`（缺省取最近一次任务）。响应：

```json
{
  "job_id": "job-20260915-1403",
  "status": "done",
  "started_at": "…",
  "finished_at": "…",
  "cost": { "currency": "USD", "total": 0.0421 },
  "items": [
    { "name": "知识编译", "title": "知识编译", "change_type": "created", "zone": "知识管理", "zone_before": null, "has_diff": false },
    { "name": "LLM Wiki", "title": "LLM Wiki", "change_type": "zone_changed", "zone": "知识管理", "zone_before": "RAG", "has_diff": true },
    { "name": "向量数据库", "title": "向量数据库", "change_type": "updated", "zone": "RAG", "zone_before": "RAG", "has_diff": true }
  ],
  "failed_sources": [ { "id": "…", "title": "…", "reason": "PDF 解析失败" } ]
}
```

`change_type` 取值：`created` / `updated` / `zone_changed`。`has_diff` 为 `true` 时前端可展开调用 API-009 取 diff。`failed_sources` 对应 ERROR-001 / ERROR-002 的「已保留已产出内容 + 可重试」。

### 2.5 问答（PAGE-001 / 009）

| 接口编号 | 名称 | 形态 | 对应模块 | 用途 | 状态 |
|---|---|---|---|---|---|
| API-028 | 提问 | HTTP POST `/api/ask` | MODULE-005 | 跨页综合作答，带可跳转引用 | 已可用 |
| API-029 | 答案存为页面 | HTTP POST `/api/ask/{id}/save-as-page` | MODULE-005 | 回填成 wiki 页面（INTERACTION-008 / BRANCH-003） | 已可用 |
| API-030 | 问答历史 | HTTP GET `/api/queries` | MODULE-005 | 历史列表（PAGE-009） | 已可用 |
| API-031 | 问答详情 | HTTP GET `/api/queries/{id}` | MODULE-005 | 回放单条 | 已可用 |
| API-032 | 删除问答 | HTTP DELETE `/api/queries/{id}` | MODULE-005 | 删除单条（UX-TBD-009） | 已可用 |

**API-028 请求**：`{ "question": "……" }`（长度 1~500）。响应：

```json
{
  "id": "q-20260915-1412",
  "question": "LLM Wiki 和 RAG 在更新机制上的本质区别是什么？",
  "answer": "……答案正文，含 [[知识编译]] 与 [[向量数据库]] 形式的引用……",
  "sufficient": true,
  "citations": [
    { "page": "知识编译", "title": "知识编译", "anchor_text": "编译期写入" },
    { "page": "向量数据库", "title": "向量数据库", "anchor_text": "查询时召回" }
  ],
  "related_pages": [],
  "pages_considered": 6,
  "cost": { "currency": "USD", "total": 0.0038 },
  "created_at": "2026-09-15T14:12:00+08:00",
  "saved_page": null
}
```

- `sufficient: false` 表示知识不足（ERROR-005 / STATE-011）：此时 `answer` 为明确说明，`related_pages` 给出相关度最高的页面列表（最多 5 个），`citations` 可为空。**注意：这是 200 成功响应**，不是错误响应。
- `citations` 由后端从答案正文中解析出的 `[[链接]]` 与实际参与综合的页面求交集生成，保证「引用可点击且真实存在」（SC-1a）。
- `pages_considered` 供前端显示「正在综合 N 个页面」的 N（CONTENT-002）。

**API-029 响应**：`{ "page": { "name": "…", "title": "…", "zone": "…" }, "job_id": "…" }`。新页面 `source_type` 为 `query-generated`，`type` 为 `analysis`，落在 `wiki/analyses/`（需求边界规则 5）。

**API-030 响应**：

```json
{
  "items": [
    {
      "id": "q-20260915-1412",
      "question": "……",
      "answer_preview": "……前 80 字……",
      "sufficient": true,
      "citation_count": 2,
      "saved_page": null,
      "created_at": "2026-09-15T14:12:00+08:00"
    }
  ],
  "total": 7
}
```

`saved_page` 非空表示该问答已回填，前端显示已归档标记（TASK-TBD-005）。

### 2.6 体检（PAGE-011）

| 接口编号 | 名称 | 形态 | 对应模块 | 用途 | 状态 |
|---|---|---|---|---|---|
| API-033 | 体检报告 | HTTP GET `/api/lint/report` | MODULE-006 | 五类分组 + 已忽略项 | 已可用 |
| API-034 | 手动体检 | HTTP POST `/api/lint/run` | MODULE-006 | 手动触发一次扫描（TASK-TBD-001） | 已可用 |
| API-035 | 修复体检项 | HTTP POST `/api/lint/fix` | MODULE-006 | 勾选后逐条修复（INTERACTION-013） | 已可用 |
| API-036 | 忽略体检项 | HTTP POST `/api/lint/ignore` | MODULE-006 | 忽略并填写原因（INTERACTION-023） | 已可用 |

**API-033 响应**：

```json
{
  "generated_at": "2026-09-15T09:30:00+08:00",
  "trigger": "startup",
  "counts": { "contradictions": 2, "orphans": 3, "broken_links": 1, "missing_index": 1, "mixed_zones": 1, "total": 8 },
  "groups": {
    "contradictions": [
      {
        "id": "L-20260915-0001",
        "kind": "contradiction",
        "pages": ["LLM Wiki", "向量数据库"],
        "summary": "两页对「是否需要向量检索」的结论冲突",
        "suggestion": "确认后合并结论并标注来源",
        "repairable": false
      }
    ],
    "orphans": [
      { "id": "L-20260915-0002", "kind": "orphan", "pages": ["临时笔记"], "summary": "没有任何页面链接到它", "suggestion": "补充交叉引用或归入现有概念页", "repairable": true }
    ],
    "broken_links": [
      { "id": "L-20260915-0003", "kind": "broken_link", "pages": ["知识编译"], "summary": "链接目标「旧概念页」不存在或已失效", "suggestion": "移除链接或重建目标页", "repairable": true }
    ],
    "missing_index": [
      { "id": "L-20260915-0004", "kind": "missing_index", "pages": ["Agent 记忆"], "summary": "页面未出现在 index.md", "suggestion": "重建索引条目", "repairable": true }
    ],
    "mixed_zones": [
      { "id": "L-20260915-0005", "kind": "mixed_zone", "pages": ["RAG"], "summary": "该分区成员主题混杂", "suggestion": "拆分或调整成员归属", "repairable": false }
    ]
  },
  "ignored": [
    { "id": "L-20260910-0007", "kind": "orphan", "pages": ["草稿"], "reason": "刻意保留的草稿", "ignored_at": "2026-09-11T10:00:00+08:00" }
  ],
  "report_exists": true
}
```

- `repairable` 由后端判定：结构性修复（补索引、去失效链接、补交叉引用）为 `true`；需要语义判断的（矛盾、分区混杂）为 `false`，前端对这类只允许「忽略」，不允许勾选修复。
- `report_exists: false`（无报告文件）时前端显示 STATE-008 变体「还没跑过体检」。
- 无待处理项且无忽略项时 `counts.total = 0` → STATE-008「当前没有需要处理的问题」。
- 报告**不落盘为 wiki 页面**；状态存 `.llmwiki/lint-report.json`（ADR-006）。

**API-034 响应**：`{ "job_id": "…" }`（走写入队列，完成后 SSE 推 `lint.ready`）。

**API-035 请求**：`{ "items": [ { "id": "L-20260915-0002", "kind": "orphan" } ] }`。响应 `{ "job_id": "…", "accepted": 1, "rejected": [] }`。`rejected` 用于回传 `repairable = false` 的条目（前端本不该提交，后端仍兜底）。修复只做建议性修改，遇到 `human_edited` 页面**不覆盖**，改为在结果中标注需人工处理（U-07 / MODULE-006 边界）。

**API-036 请求**：`{ "id": "L-20260915-0002", "reason": "刻意保留" }`。`reason` 必填（1~200 字），缺失返回 `E_VALIDATION`。响应 `{ "id": "…", "ignored": true }`。

### 2.7 设置与成本（PAGE-012）

| 接口编号 | 名称 | 形态 | 对应模块 | 用途 | 状态 |
|---|---|---|---|---|---|
| API-037 | 读取设置 | HTTP GET `/api/settings` | MODULE-009 | 模型、vault、限额、主题 | 已可用 |
| API-038 | 保存设置 | HTTP PUT `/api/settings` | MODULE-009 | 不含 API key | 已可用 |
| API-039 | 保存 API key | HTTP PUT `/api/settings/api-key` | MODULE-009 | 单独写入仓库外密钥文件 | 已可用 |
| API-040 | 测试连接 | HTTP POST `/api/settings/test-connection` | MODULE-009 | 验证 key 与模型可用（ERROR-008 的预防） | 已可用 |
| API-041 | git 手动同步 | HTTP POST `/api/settings/git/sync` | MODULE-008 | 推送到远端（ADR-009） | 已可用 |
| API-042 | 成本看板 | HTTP GET `/api/costs` | MODULE-009 | 累计、按日、按操作（PAGE-012） | 已可用 |

**API-037 响应**

```json
{
  "llm": { "provider": "openai-compatible", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "temperature": 0.2, "max_tokens": 4096, "api_key_set": true, "api_key_hint": "sk-…f3a2" },
  "vault": { "path": "D:\\kb", "remote": "git@github.com:me/kb.git", "branch": "main", "auto_push": false, "ssh_key_path": "C:\\Users\\me\\.ssh\\id_ed25519" },
  "limits": { "max_source_chars": 40000, "segment_threshold_chars": 24000, "max_cost_per_job": 0.5, "llm_timeout_seconds": 120 },
  "ui": { "theme": "system" },
  "git": { "available": true, "initialized": true, "last_commit": "9f3c2b1", "last_sync_at": "2026-09-15T12:00:00+08:00", "dirty": false }
}
```

- `api_key_hint` 只回显末 4 位，**永不返回完整 key**。
- `limits.max_cost_per_job` 与 `segment_threshold_chars` 对应 ADR-012。
- `ssh_key_path` 对应「可设置 SSH key」。

**API-038 请求**：`{ "llm": { "base_url": "…", "model": "…", "temperature": 0.2, "max_tokens": 4096 }, "vault": { "path": "…", "remote": "…", "auto_push": false, "ssh_key_path": "…" }, "limits": { … }, "ui": { "theme": "dark" } }`，全部字段可选，仅更新提供的字段。修改 `vault.path` 时后端校验目录可访问，否则返回 `E_VALIDATION`。

**API-039 请求**：`{ "api_key": "sk-…" }`。响应 `{ "api_key_set": true, "api_key_hint": "sk-…f3a2" }`。写入 `%APPDATA%\llmwiki\settings.json`（ADR-010）。

**API-040 请求**：`{}`（用当前配置）。响应 `{ "ok": true, "model": "gpt-4o-mini", "latency_ms": 812 }`；失败返回 `E_LLM_AUTH` 或 `E_LLM_TIMEOUT`。

**API-041 响应**：`{ "pushed": true, "remote": "…", "branch": "main", "commit": "9f3c2b1" }`；失败返回 `E_GIT_FAILED` 并在 `details.stderr` 给出 git 输出。

**API-042 查询参数**：`range`（`7d` / `30d` / `all`，默认 `30d`）。响应：

```json
{
  "currency": "USD",
  "range": "30d",
  "total": 1.2841,
  "by_day": [ { "date": "2026-09-15", "cost": 0.2043, "calls": 12 } ],
  "by_operation": [
    { "operation": "compile", "cost": 1.1020, "calls": 38 },
    { "operation": "ask", "cost": 0.1440, "calls": 9 },
    { "operation": "lint", "cost": 0.0381, "calls": 3 }
  ],
  "recent": [
    { "at": "2026-09-15T14:03:11+08:00", "operation": "compile", "model": "gpt-4o-mini", "cost": 0.0421, "job_id": "job-20260915-1403" }
  ],
  "pricing_source": "builtin"
}
```

`pricing_source` 取值 `builtin`（内置定价表）或 `custom`（用户在设置里填了单价）——对应 TASK-TBD-002。

### 2.8 事件（SSE）

| 接口编号 | 名称 | 形态 | 对应模块 | 用途 | 状态 |
|---|---|---|---|---|---|
| API-043 | 事件流 | HTTP GET `/api/events` (SSE) | 公共 | 编译进度、素材状态、体检完成、待处理数变化 | 已可用 |

详见第 5 节。

---

## 3. 数据结构

以下为后端 Pydantic 模型与前端 TypeScript 类型的**共同权威定义**。前端类型文件由后端模型人工对齐生成，字段名一律 `snake_case`，不做驼峰转换。

### 3.1 枚举

| 枚举 | 取值 | 说明 |
|---|---|---|
| `PageType` | `source` / `concept` / `entity` / `analysis` | 页面类型（ADR-011，按类型分目录） |
| `SourceType` | `compiled` / `query-generated` / `human` | 页面来源（需求边界规则 5） |
| `PageStatus` | `active` / `invalid` | 页面有效状态 |
| `SourceKind` | `web` / `pdf` / `note` | 素材类型（需求 U-03 三类） |
| `SourceStatus` | `normal` / `failed` / `deleted` / `stale` | 素材状态（PAGE-013 四态筛选、INTERACTION-020） |
| `JobStatus` | `queued` / `running` / `done` / `failed` | 任务状态 |
| `JobKind` | `compile` / `fix` / `save_page` / `lint` | 任务类型 |
| `StepState` | `pending` / `running` / `done` / `failed` | 围观页步骤状态（COMPONENT-013） |
| `ChangeType` | `created` / `updated` / `zone_changed` | 变更类型 |
| `LintKind` | `contradiction` / `orphan` / `broken_link` / `missing_index` / `mixed_zone` | 体检项类型（PAGE-011 五类） |
| `ErrorCode` | 见第 4 节 | 错误码 |
| `Theme` | `light` / `dark` / `system` | 主题（UI-TBD-003：浅色为默认） |

### 3.2 核心对象

| 对象 | 关键字段 | 出现于 |
|---|---|---|
| `PageSummary` | `name` `title` `type` `zone` `source_type` `human_edited` `status` `link_count` `backlink_count` `updated_at` | API-004 / 008 / 012 / 013 |
| `PageDetail` | `PageSummary` 全部 + `content` `links` `backlinks` `sources` `created_at` `origin_source` | API-005 / 006 |
| `SourceSummary` | `id` `title` `kind` `source_url` `status` `tags` `author` `published_at` `created_at` `updated_at` `derived_page_count` `failure_reason` | API-014 |
| `SourceDetail` | `SourceSummary` 全部 + `note` `content` `content_editable` `asset_path` `raw_meta` `derived_pages` | API-015 / 016 / 017 / 018 / 019 |
| `GraphNode` | `id` `title` `type` `zone` `degree` `status` | API-010 |
| `GraphEdge` | `source` `target` | API-010 |
| `JobSnapshot` | `job_id` `status` `kind` `total_sources` `done_sources` `current_source` `current_page` `steps[]` `cost` `started_at` `finished_at` `failure_reason` `can_leave` | API-025 / 026 |
| `ChangeItem` | `name` `title` `change_type` `zone` `zone_before` `has_diff` | API-027 |
| `Answer` | `id` `question` `answer` `sufficient` `citations[]` `related_pages[]` `pages_considered` `cost` `created_at` `saved_page` | API-028 |
| `Citation` | `page` `title` `anchor_text` | API-028 |
| `LintItem` | `id` `kind` `pages[]` `summary` `suggestion` `repairable` | API-033 / 035 |
| `LintReport` | `generated_at` `trigger` `counts` `groups` `ignored` `report_exists` | API-033 |
| `CostSummary` | `currency` `range` `total` `by_day[]` `by_operation[]` `recent[]` `pricing_source` | API-042 |
| `ErrorBody` | `code` `message` `details` | 全部错误响应 |

### 3.3 前端消费约定

- 引用渲染：`answer` 与 `content` 中的 `[[页面名]]` 由前端统一渲染为 `COMPONENT-010`（主色文字 + 下划线），点击跳 PAGE-005。**只有真实存在的页面名才渲染为链接**；不存在的（失效链接）渲染为带失效标记的文本，点击走 ERROR-006 提示路径。页面存在性由页面详情响应的 `links` 字段与全局页面名集合校验。
- 图谱：`GraphNode.id` 即页面名，`GraphEdge.source/target` 即页面名，与路由参数一致，点节点直接跳转（INTERACTION-014）。
- 状态与颜色：所有状态必须同时给出文字标签，颜色仅作辅助（UI-AC-002）。状态到徽标变体的映射：`normal`/`done`/`active` → 成功，`stale`/`queued` → 警告，`failed`/`invalid` → 危险，`running` → 主色，`deleted` → 中性。

---

## 4. 错误与异常约定

### 4.1 错误码表

| 错误码 | HTTP | 含义 | 触发场景 | 前端行为 |
|---|---|---|---|---|
| `E_VALIDATION` | 422 | 参数校验失败 | 字段缺失、类型错误、超长、非法枚举 | 定位到对应表单字段（`details.fields`） |
| `E_NOT_FOUND` | 404 | 资源不存在 | 页面名不存在、素材 id 不存在、任务号不存在 | 显示失效提示页 + 相邻页面出口（ERROR-006） |
| `E_DUPLICATE_SOURCE` | 409 | 素材重复导入 | 同 `source_url` 或同内容哈希 | 提示已存在，提供重新编译/取消（ERROR-003） |
| `E_PARSE_FAILED` | 422 | 素材解析失败 | PDF 损坏、网页无正文 | 素材标失败并给出原因（ERROR-002 / STATE-010） |
| `E_SOURCE_BUSY` | 409 | 素材正在编译中 | 编辑/删除编译中的素材 | 编辑入口置灰并说明原因（ERROR-009） |
| `E_SOURCE_NOT_EDITABLE` | 422 | 该素材正文不可编辑 | 对 web/pdf 传 `content` | 输入区不可编辑，按钮为「编辑元数据」 |
| `E_LLM_NOT_CONFIGURED` | 503 | 未配置 API key | 触发编译/问答时无 key | 指向设置页（ERROR-008） |
| `E_LLM_AUTH` | 502 | key 无效或余额不足 | 上游返回 401/402/403 | 指向设置页更换 key（ERROR-008） |
| `E_LLM_TIMEOUT` | 504 | 模型调用超时 | 上游超时 | 保留已产出内容，提供重试（ERROR-001） |
| `E_LLM_RATE_LIMIT` | 502 | 上游限流 | 上游返回 429 | 提示稍后重试，不自动重试超过上限 |
| `E_JOB_CONFLICT` | 409 | 已有写入任务在跑 | 重复触发编译 | 跳转到围观页看当前任务 |
| `E_PATH_OUT_OF_VAULT` | 400 | 路径越界 | 路径遍历、绝对路径、盘符 | 直接报错，不允许继续 |
| `E_GIT_FAILED` | 502 | git 操作失败 | 提交/推送失败、无远端、鉴权失败 | 设置页展示 git stderr，提示检查远端与 SSH key |
| `E_VAULT_NOT_INITIALIZED` | 503 | vault 未初始化 | 未配置 vault 路径或目录不可写 | 引导到设置页配置 vault |
| `E_INTERNAL` | 500 | 未预期错误 | 兜底 | 显示通用错误 + 可复制的追踪标识 |

### 4.2 非错误但需要在响应体中表达的语义

| 语义 | 表达方式 | 对应 UX |
|---|---|---|
| 知识不足以回答 | `Answer.sufficient = false` + `related_pages` | ERROR-005 / STATE-011 / CONTENT-003 |
| 编译部分失败 | `ChangeSet.failed_sources[]` 非空，任务 `status = failed` | ERROR-001 / ERROR-002 |
| 素材重复 | 仍用 `E_DUPLICATE_SOURCE` 409（需用户决策，故为错误） | ERROR-003 |
| 无待处理体检项 | `counts.total = 0`（200） | STATE-008 |
| 还没跑过体检 | `report_exists = false`（200） | STATE-008 变体 |
| 空库 | `bootstrap.is_empty = true`（200） | STATE-006 / BRANCH-001 |
| 素材已改待重编译 | `SourceDetail.status = "stale"` + `needs_recompile` | STATE-013 / CONTENT-007 |

### 4.3 异常处理原则

1. **错误响应不得泄露路径细节**：`E_PATH_OUT_OF_VAULT` 不回显被拒绝的原始路径，只说明越界。
2. **部分成功要保留**：编译过程中单素材失败不影响其他素材（ERROR-001），已写入页面不删除，任务状态置 `failed` 并在 `failed_sources` 说明。
3. **写操作失败必须可追溯**：所有写入任务失败时保留 git 侧的可用回退点；失败信息写 `.llmwiki/jobs.json` 与 `wiki/log.md`。
4. **幂等提示优先于报错**：素材重复、任务冲突这类用户可理解的状态，一律给出明确文案与可选动作，不显示裸错误码。
5. **错误码与 HTTP 状态一一对应**，前端据此决定是页面级错误还是字段级错误。

---

## 5. SSE 事件约定

### 5.1 通道

```text
GET /api/events
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

`EventSource` 订阅，服务端单向推送。**不做**鉴权（本机），**不做**多客户端隔离（本机单人，但允许多标签页同时订阅，事件广播给所有连接）。

### 5.2 事件类型

| 事件名 | 载荷 | 触发时机 | 前端消费 |
|---|---|---|---|
| `job.progress` | `JobSnapshot` 的精简版（`job_id` `status` `total_sources` `done_sources` `current_source` `current_page` `steps` `cost`） | 步骤推进时 | PAGE-003 实时更新；顶部进度胶囊（BRANCH-002） |
| `job.done` | `{ job_id, kind, status, cost }` | 任务成功完成 | 弹出完成通知（FLOW-002-04），提示查看变更清单 |
| `job.failed` | `{ job_id, kind, failure_reason, failed_sources[] }` | 任务失败 | 显示失败原因与重试入口（ERROR-001 / ERROR-002） |
| `source.status` | `{ id, title, status, failure_reason }` | 素材状态变更（导入完成、失败、标记 stale、软删除、恢复） | PAGE-013 列表状态即时更新（STATE-010 / 012 / 013） |
| `lint.ready` | `{ generated_at, pending_count, trigger }` | 体检完成（启动/闲置/手动） | 导航栏「N 个待处理」更新（INTERACTION-006 语义 / CONTENT-006） |
| `lint.pending_changed` | `{ pending_count }` | 修复或忽略后待处理数变化 | 导航栏数字更新，无需拉全量报告 |
| `vault.changed` | `{ page_count, source_count }` | vault 结构变化（新页面、删除） | 首页空库判定与导航计数刷新 |

### 5.3 事件格式

```text
event: job.progress
data: {"job_id":"job-20260915-1403","status":"running","done_sources":1,"total_sources":3,"current_page":"知识编译","cost":{"currency":"USD","total":0.0421}}

: heartbeat
```

- 每条事件以空行结束；`data` 为单行 JSON（不换行）。
- 心跳每 15 秒发送注释行 `: heartbeat`，避免连接被中间层回收。
- 服务端在连接建立时**先推送一次当前快照**（等价于 `job.progress` 或 `vault.changed`），避免前端等待第一次变化。

### 5.4 断线重连

1. `EventSource` 自动重连（浏览器默认 3 秒）。
2. 重连成功后，前端**必须**重新拉取 `GET /api/compile/current`、`GET /api/lint/report`（或 `bootstrap`）以校正状态，不依赖事件补齐。
3. 后端不实现事件重放（不引入事件日志）；状态快照接口是唯一权威。
4. 编译中断（ERROR-007）时，重启后 `jobs.json` 中未完成任务的步骤状态决定续跑起点；前端从快照读到的 `steps` 即真实进度。

---

## 6. 待确认事项处理结果

| 编号 | 待确认事项 | 影响范围 | 处理方式 | 最终结论 |
|---|---|---|---|---|
| TASK-TBD-001 | 是否提供手动触发体检的接口 | API-034、PAGE-011 | 确认 | 提供。需求只定义了自动触发，但无手动入口时用户改完内容无法重新体检，功能上不完整；按钮放在 PAGE-011 页头，不改变页面职责 |
| TASK-TBD-002 | 成本看板的币种与定价来源 | API-042、PAGE-012 | 确认 | 币种 USD；内置 OpenAI 系定价表并允许在设置中填自定义单价，`pricing_source` 标明来源 |
| TASK-TBD-003 | 「打开数据文件夹」的实现方式 | API-003 | 确认 | 后端调用系统文件管理器（Windows `explorer.exe`，其他平台回退 `xdg-open` / `open`）；仅在接口被显式调用时执行 |
| TASK-TBD-004 | 搜索高亮由前端还是后端计算 | API-013 | 确认 | 后端生成带 `<mark>` 的 `snippet`，前端只渲染；避免前后端两套匹配逻辑不一致 |
| TASK-TBD-005 | 问答回填后原记录是否标记 | API-030 | 确认 | 标记。`saved_page` 非空即显示「已归档为页面」，避免重复回填同一答案 |
| TASK-TBD-006 | 图谱深度 2 的规模保护 | API-010 | 确认 | `depth=2` 时若邻域节点超过 300 个则截断并置 `truncated = true`，前端提示切换筛选；防止大库下页面卡死 |
| TASK-TBD-007 | 素材重编译时旧派生页面如何处理 | API-022、MODULE-002 | 确认 | 更新同一批派生页面而非新建；素材已删除但页面仍在的情况由体检列出，不级联删除 |
| TASK-TBD-008 | vault 默认路径 | API-037、ADR-004 | 确认 | 默认 `%USERPROFILE%\llmwiki-vault`，首次启动未检测到时引导到设置页配置，不自动创建目录 |

无未处理事项。实现过程中新增的待确认点将追加到本表，并使用同一 `TASK-TBD-###` 编号继续递增。
