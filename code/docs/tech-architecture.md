# 技术架构

> 状态：**已定稿**，可作为阶段 3B 的唯一架构输入
> 方法：SoloForge 阶段 3A v0.3
> 日期：2026-09-15
> 输入：`code/docs/requirement-analysis.md`（含两次修订）、`code/docs/ux-design.md`、`code/docs/ui-design.md`
> 版本约束来源：本机 `uv pip compile` 与 `npm install --package-lock-only` 实测解析结果

---

## 1. 架构目标与约束

### 1.1 目标逐条对应（来自需求文档第 4 节）

| 需求目标 | 架构上的兑现方式 |
|---|---|
| G-1 素材进得来、改得了、删得掉 | MODULE-001 三类解析器 + 元数据写回；`raw/` 对用户开放写、对程序只读 |
| G-2 知识自动生长 | MODULE-002 编译编排：摘要页 / 概念页 / 实体页 / 索引 / 互链 / 增量分区 |
| G-3 看得见网络 | MODULE-004：13 个页面 + 反链面板 + 图谱页（d3-force 自绘） |
| G-4 能问出新东西 | MODULE-005 跨页综合问答，答案带可跳转引用 |
| G-5 能自愈 | MODULE-006 五类体检项，只出清单不自动改 |
| G-6 过程可信 | MODULE-008 变更记录 + 逐页 diff + git 自动 commit |
| G-7 不被锁定 | 纯 Markdown + frontmatter，独立 git 仓库，设置页一键打开文件夹 |
| G-8 自动归档 | MODULE-002 增量分区判定，结果写入 frontmatter |

### 1.2 成功标准对应

| 标准 | 架构保障 |
|---|---|
| SC-1 跨素材综合问答 | MODULE-005 强制读取多个页面后综合；引用为页面级 `[[链接]]`，可点击跳转；知识不足时明确拒答并列出相关页 |
| SC-2 导入到可见编译结果 ≤ 10 分钟且无需手工干预 | 投放 → 单写锁排队 → 编译 → 变更清单为一条自动链路；SSE 实时反馈，不阻塞界面 |
| SC-3 平均出链 ≥ 3、孤儿页 ≤ 20% | MODULE-003 提供度数/孤儿计算，MODULE-006 将孤儿页列为体检项 |

### 1.3 非功能性约束

| 类型 | 约束 | 落实方式 |
|---|---|---|
| 交付 | 本机单人、浏览器访问、无账号无权限 | 服务只绑 `127.0.0.1`，不实现认证；不做多用户隔离 |
| 存储 | 文件优先，无数据库、无向量库 | 全部状态落 Markdown / JSON 文件；不引入 SQLAlchemy、chroma、faiss 等 |
| 写入安全 | 单写入进程、写前读最新版、写操作串行化 | 全局 `asyncio.Lock` + 任务队列 `jobs.py`；同一时刻只有一个写入任务 |
| 原子性 | 文件不得半写 | 临时文件 + `os.replace` 原子替换 |
| 成本 | LLM 成本可观，需可见 | MODULE-009 按调用记账，设置页成本看板 + 围观页累计花费 |
| 密钥 | API key 不进版本库 | 存放于仓库外 `%APPDATA%\llmwiki\settings.json`（ADR-010） |
| 规模 | V1 依赖 `index.md`，约 200 页以内 | 搜索与图谱均为 O(页数) 内存计算，不引入索引中间件 |
| 性能 | 图谱与列表在 200 页内可交互 | 图谱默认 1 层深度，2 层可选；分区筛选减小渲染规模 |
| 可访问性 | 对比度 ≥ 7:1、点击目标 ≥ 28/34px、色不单独表意 | 前端严格复用 `tokens.css`，不新增颜色与尺寸来源 |
| 自适应 | XL/L/M/S 四档无横向滚动，正文 ≤ 820px | 复用 `tokens.css` 的 `--container/--rail-w/--gutter` 断点机制 |
| 主题 | 浅色默认，深色跟随系统并可切换 | `data-theme` 属性切换，token 驱动 |

### 1.4 明确不做

需求第 7 节「暂不做」的全部条目一律不进入架构：向量数据库、代码仓库素材源、视频源、多人协作与鉴权、移动端适配、浏览器扩展、独立定时调度器、PDF/PPT 导出、Obsidian 插件、回滚 UI。

**特别说明：不引入 cron 式调度器。** 体检只由两个事件触发：应用启动时一次、闲置 30 分钟后一次。实现方式为应用内计时器，随进程存亡，不落任何调度配置。

---

## 2. 交付形态与运行环境

- **形态**：单个本机 Web 应用。一个 Python 进程同时提供 REST 接口、SSE 事件流与 React 构建产物。
- **启动方式**：手动命令行启动一条命令（`code/scripts/` 提供脚本），进程打印访问地址。
- **访问方式**：浏览器打开 `http://127.0.0.1:8765`。不做桌面壳、不做系统托盘、不做安装包。
- **运行环境**：Windows 10/11 本机（开发与使用同一台机器），Python 3.12，Node 仅构建期需要。
- **网络**：可直连 LLM API（OpenAI 兼容协议）。素材抓取需公网访问。两者都不经过代理。
- **离线降级**：无 LLM key 时后端仍可启动，素材可正常导入与浏览，编译类操作返回明确错误（`E_LLM_NOT_CONFIGURED`）。
- **知识库位置**：独立 git 仓库，路径由设置项 `vault.path` 指定，可在仓库外（默认 `%USERPROFILE%\llmwiki-vault`）。

---

## 3. 技术栈与分层

### 3.1 版本约束（实测解析，非记忆值）

| 层 | 组件 | 版本 | 理由 |
|---|---|---|---|
| 运行时 | Python | **3.12.x**（锁定 3.12，不用 3.14） | 3.14 过新，PDF/HTML 解析与 HTTP 客户端轮子不全，Windows 上易退回源码编译 |
| 依赖管理 | uv | **0.11.28** | 本机已装；可锁 Python 版本与生成锁文件，安装快 |
| 后端框架 | FastAPI | **0.141.1** | 原生 async、Pydantic 校验与 OpenAPI 文档，配合 SSE 无需额外组件 |
| 后端框架 | Starlette | **1.6.0** | FastAPI 依赖，静态托管与流式响应由其提供 |
| ASGI 服务器 | Uvicorn | **0.53.0** | 单进程 `--host 127.0.0.1`，Windows 上无需 gunicorn |
| 数据校验 | Pydantic | **2.13.5** | 请求/响应与设置模型 |
| 配置 | pydantic-settings | **2.15.0** | 环境变量与 JSON 设置文件合并 |
| HTTP 客户端 | httpx | **0.28.1** | 素材抓取 + LLM 调用，同一客户端栈，支持流式 |
| 网页正文抽取 | trafilatura | **2.2.0** | 纯 Python、无浏览器依赖，长文抽取质量稳定 |
| HTML 解析 | lxml | **6.1.3** | trafilatura 依赖，同时用于元信息抽取 |
| PDF 解析 | pypdf | **6.18.1** | 纯 Python，免外部二进制 |
| frontmatter | python-frontmatter | **1.3.0** | Markdown 元数据读写 |
| YAML | PyYAML | **6.0.3** | frontmatter 序列化 |
| 上传 | python-multipart | **0.0.32** | 文件上传表单解析 |
| 编码探测 | charset-normalizer | **3.5.1** | 非 UTF-8 素材解码不报错 |
| 测试 | pytest / pytest-asyncio | **9.1.1** / **1.4.0** | 阶段 4 的测试基座 |
| 静态检查 | ruff | **0.16.7** | 仅 lint，不引入额外格式化器 |
| 构建期 | Node / npm | **24.14.0** / **11.9.0** | 仅用于 `npm run build`，不常驻 |
| 前端框架 | React / ReactDOM | **19.3.0** | 用户选定 |
| 路由 | react-router-dom | **7.18.3** | 13 页路由与深层返回路径 |
| Markdown 渲染 | react-markdown / remark-gfm | **10.1.0** / **4.0.1** | 页面正文与表格渲染；`[[链接]]` 通过自定义节点渲染为可跳转链接 |
| 构建 | Vite | **8.3.0** | 构建产物交后端托管，运行期无 node 进程 |
| React 插件 | @vitejs/plugin-react | **6.1.1** | 与 Vite 8 配套 |
| 类型 | TypeScript | **7.0.2** | 接口类型与后端 Pydantic 模型人工对齐，生成共享类型定义 |
| 单测 | vitest / jsdom | **5.0.1** / **29.1.1** | jsdom 必须锁 29.1.1：`jsdom@30` 要求 Node ≥ 24.15.0，本机为 24.14.0 |
| 组件测试 | @testing-library/react | **16.3.3** | 页面级测试 |
| 图谱 | d3-force / d3-zoom / d3-selection | **3.0.0** | 自绘 SVG，样式与 `tokens.css` 同源（ADR-007） |

### 3.2 分层与职责

| 层 | 位置 | 职责 | 禁止 |
|---|---|---|---|
| 表现层 | `frontend/src/` | 13 个页面、组件、路由、状态管理、SSE 订阅 | 不直接拼写文件路径语义；不自行推导权限与业务规则 |
| 接口层 | `backend/src/llmwiki/api/` | HTTP 路由、请求校验、响应封装、SSE 端点 | 不写文件、不调用 LLM |
| 服务层 | `compile/` `ask/` `lint/` `ingest/` | 业务编排：编译、问答、体检、素材解析 | 不直接读写文件（经 MODULE-003）、不处理 HTTP |
| 领域/存储层 | `workspace/` | 文件读写、frontmatter、链接解析、反链、索引、原子写、写锁 | 不做内容理解、不调用 LLM |
| 规范层 | `schema/` | 页面类型定义、字段规范、三种操作的提示词 | 不承载运行时数据 |
| 审计层 | `audit/` | 变更记录、diff、git 提交与同步 | 不修改知识内容 |
| 接入层 | `llm/` | OpenAI 兼容客户端、流式、重试、成本核算 | 不感知 wiki 结构 |
| 横切 | `jobs.py` `config.py` `main.py` | 单写入任务队列与事件发布、配置与密钥、应用装配与生命周期 | 不含业务规则 |

### 3.3 工程结构

```text
code/
├── backend/
│   ├── pyproject.toml            # uv 管理，requires-python = ">=3.12,<3.13"
│   ├── uv.lock
│   ├── src/llmwiki/
│   │   ├── main.py               # 应用装配、静态托管、启动/闲置体检
│   │   ├── config.py             # 设置读写（含 %APPDATA% 密钥文件）
│   │   ├── jobs.py               # 单写入任务队列 + 事件总线（SSE 数据源）
│   │   ├── watcher.py            # 闲置计时与体检触发
│   │   ├── errors.py             # 错误码与异常类型
│   │   ├── api/
│   │   │   ├── pages.py          # 页面、反链、图谱、分区、搜索
│   │   │   ├── sources.py        # 素材投放、素材库、原文、编辑、删除
│   │   │   ├── compile.py        # 触发编译、变更清单、diff、改分区
│   │   │   ├── ask.py            # 提问、问答历史、回填
│   │   │   ├── lint.py           # 体检报告、修复、忽略
│   │   │   ├── settings.py       # 模型配置、成本看板、打开文件夹、git 同步
│   │   │   └── events.py         # SSE 事件流
│   │   ├── workspace/            # MODULE-003
│   │   ├── ingest/               # MODULE-001
│   │   ├── compile/              # MODULE-002
│   │   ├── ask/                  # MODULE-005
│   │   ├── lint/                 # MODULE-006
│   │   ├── schema/               # MODULE-007
│   │   ├── audit/                # MODULE-008
│   │   └── llm/                  # MODULE-009
│   └── tests/
├── frontend/
│   ├── package.json / package-lock.json
│   ├── vite.config.ts            # base '/'，build.outDir 指向后端可托管的 dist
│   ├── index.html
│   └── src/
│       ├── main.tsx / App.tsx / router.tsx
│       ├── api/                  # 后端接口封装 + 共享类型
│       ├── pages/                # PAGE-001 ~ PAGE-013
│       ├── components/           # 复用组件（徽标、卡片、步骤项、日志块…）
│       ├── hooks/                # useEventStream 等
│       └── styles/tokens.css     # 从 code/design/tokens.css 复制，保持唯一来源
├── design/                       # 阶段 2B 设计稿（只读参考，不作为交付产物）
├── deploy/                       # 启动脚本、环境说明、故障排查
└── scripts/                      # 端到端验证脚本
```

---

## 4. 模块划分与需求模块映射

需求文档第 5 节的模块名称**原样复用**，仅补正式编号。

| 模块编号 | 模块名称（原样） | 代码位置 | 主要职责 | 对应需求模块 |
|---|---|---|---|---|
| MODULE-001 | 素材接入 | `backend/src/llmwiki/ingest/` | 网页 / PDF / 手写笔记三类素材的解析、去重、元数据落盘、编辑与软删除 | MOD-01 |
| MODULE-002 | 编译引擎 | `backend/src/llmwiki/compile/` | ingest 编排：摘要页 / 概念页 / 实体页 / 互链 / 增量分区 / 索引 / 日志 / 矛盾标记 | MOD-02 |
| MODULE-003 | Wiki 存储与链接 | `backend/src/llmwiki/workspace/` | md 读写、frontmatter、`[[链接]]` 解析、反链、索引、原子写、写锁 | MOD-03 |
| MODULE-004 | 浏览与图谱 | `backend/src/llmwiki/api/`（读接口）+ `frontend/src/`（13 页） | 页面渲染、跳转、反链面板、全局图谱、人工编辑入口 | MOD-04 |
| MODULE-005 | 问答 | `backend/src/llmwiki/ask/` | 候选页选取、跨页综合、带引用作答、答案回填 | MOD-05 |
| MODULE-006 | 体检与维护 | `backend/src/llmwiki/lint/` | 矛盾 / 孤儿页 / 失效链接 / 缺失索引 / 分区混杂的扫描与建议清单 | MOD-06 |
| MODULE-007 | 知识规范（Schema） | `backend/src/llmwiki/schema/` | 页面类型、命名规范、frontmatter 字段、三种操作提示词 | MOD-07 |
| MODULE-008 | 变更记录与审计 | `backend/src/llmwiki/audit/` | 操作日志、页面级 diff、变更原因、git 自动 commit 与手动同步 | MOD-08 |
| MODULE-009 | 设置与模型接入 | `backend/src/llmwiki/llm/` + `api/settings.py` | provider / 模型 / API key 配置、成本看板 | MOD-09 |

**关于 MODULE-004 的说明**：该模块横跨前端 13 个页面与后端的读接口，这是需求本身的形态决定的——「浏览与图谱」的呈现端就是浏览器。架构上不把它拆成两个模块，避免与需求模块编号脱节；其接口部分与页面部分的边界写进 3B 的任务拆解。

**映射自检**：需求 9 个模块（MOD-01 ~ MOD-09）全部有对应代码模块，编号一一对应，无遗漏、无新增模块。

---

## 5. 数据与存储

### 5.1 知识库目录布局（独立 git 仓库）

```text
<vault>/
├── raw/                      素材层：对用户开放，对程序只读（除用户显式编辑）
│   ├── <素材>.md              一素材一文件：frontmatter 元数据 + 笔记正文
│   └── assets/                PDF 等原件
├── wiki/                     知识层：LLM 写，人可读可改
│   ├── index.md              内容索引：全部页面 + 一句话摘要
│   ├── log.md                append-only 操作日志
│   ├── overview.md           跨素材综述
│   ├── conventions.md        用户写给 LLM 的偏好
│   ├── sources/              素材页
│   ├── concepts/             概念页
│   ├── entities/             实体页
│   └── analyses/             分析页（对比、问答归档、体检报告）
└── .llmwiki/                 运行时状态（ADR-006）
    ├── jobs.json             编译任务与进度（供围观页恢复）
    ├── lint-report.json      最近一次体检结果与已忽略项
    ├── queries.json          问答历史
    ├── costs.json            成本流水
    └── sources-index.json    素材状态索引（正常/失败/已删除/待重编译）
```

### 5.2 页面 frontmatter 字段

`wiki/` 下页面统一字段（MODULE-007 定义，MODULE-003 读写）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `title` | string | 页面标题 |
| `type` | enum | `source` / `concept` / `entity` / `analysis` |
| `source_type` | enum | `compiled` / `query-generated` / `human` |
| `zone` | string | 所属分区，由 MODULE-002 增量判定 |
| `links` | string[] | 出链页面名（由解析结果回写，便于快速计算） |
| `human_edited` | bool | 人工编辑标记，体检只建议不覆盖 |
| `status` | enum | `active` / `invalid`（软删除或来源失效） |
| `created_at` / `updated_at` | ISO8601 | 时间戳 |
| `origin_source` | string | 派生自哪个素材（可空） |

`raw/` 下素材字段：`title` / `kind`（`web` / `pdf` / `note`）/ `source_url` / `author` / `published_at` / `tags` / `status`（`normal` / `failed` / `deleted` / `stale`）/ `raw_meta`。

### 5.3 写入规则

1. **单写入者**：所有写操作进入 `jobs.py` 的单一队列，由一个持锁的 worker 串行执行。
2. **原子写**：写临时文件后 `os.replace` 覆盖目标；跨设备时降级为同目录临时文件。
3. **写前读最新版**：每次写入前重新读取磁盘内容作为基线，避免使用陈旧内存副本。
4. **`raw/` 保护**：MODULE-001 之外的模块对 `raw/` 只读；程序写入仅发生在用户显式编辑/删除素材与导入落盘时。
5. **软删除**：素材或页面删除只改 `status`，不物理删除、不级联；失效入链由 MODULE-006 列出。
6. **git**：每次写入任务完成后自动 `git add <vault> && git commit`；远端推送为设置页手动触发（ADR-009）。

---

## 6. 接口约定

### 6.1 风格

- 协议：HTTP/1.1，JSON 请求与响应；进度推送为 SSE（`text/event-stream`）。
- 前缀：全部业务接口位于 `/api`；前端静态资源挂在 `/`。
- 命名：资源用复数名词（`/api/pages`、`/api/sources`），动作型操作用子路径（`/api/sources/{id}/recompile`）。
- 鉴权：**无**。服务只绑定 `127.0.0.1`，本机单人使用，不实现 token、会话或权限。
- 路径安全：所有涉及文件路径的参数必须是 vault 内相对路径，服务端做归一化与白名单校验，越界返回 `E_PATH_OUT_OF_VAULT`。

### 6.2 统一响应与错误

成功响应直接返回资源对象或列表；错误统一为：

```json
{ "error": { "code": "E_LLM_TIMEOUT", "message": "模型调用超时", "details": {} } }
```

| 错误码 | HTTP | 含义 | 触发场景（对应 UX 异常） |
|---|---|---|---|
| `E_VALIDATION` | 422 | 参数校验失败 | 表单字段非法，附字段级 `details` |
| `E_NOT_FOUND` | 404 | 资源不存在 | 页面 / 素材 / 任务不存在（ERROR-006） |
| `E_DUPLICATE_SOURCE` | 409 | 素材重复导入 | ERROR-003 |
| `E_PARSE_FAILED` | 422 | 素材解析失败 | ERROR-002 |
| `E_SOURCE_BUSY` | 409 | 素材正在编译中不可编辑 | ERROR-009 |
| `E_LLM_NOT_CONFIGURED` | 503 | 未配置 API key | ERROR-008 前置 |
| `E_LLM_AUTH` | 502 | key 无效或余额不足 | ERROR-008 |
| `E_LLM_TIMEOUT` | 504 | 模型超时 | ERROR-001 |
| `E_JOB_CONFLICT` | 409 | 已有写入任务在跑 | 并发触发编译 |
| `E_PATH_OUT_OF_VAULT` | 400 | 路径越界 | 路径遍历尝试 |
| `E_GIT_FAILED` | 502 | git 操作失败 | 提交或同步失败 |
| `E_INSUFFICIENT_KNOWLEDGE` | 200 | 知识不足以回答（非错误，走正常响应体字段） | ERROR-005 |

`E_INSUFFICIENT_KNOWLEDGE` 是回答的一种结果而非传输错误，放在问答响应体的 `sufficient: false` 字段中表达，避免前端把「答不上来」当成系统故障。

### 6.3 接口分组概览

| 分组 | 前缀 | 覆盖页面 |
|---|---|---|
| 页面与图谱 | `/api/pages`、`/api/graph`、`/api/zones`、`/api/search` | PAGE-005 / 006 / 007 / 008 |
| 素材 | `/api/sources` | PAGE-002 / 010 / 013 |
| 编译 | `/api/compile`、`/api/changes` | PAGE-003 / 004 |
| 问答 | `/api/ask`、`/api/queries` | PAGE-001 / 009 |
| 体检 | `/api/lint` | PAGE-011 |
| 设置 | `/api/settings`、`/api/costs`、`/api/system` | PAGE-012 |
| 事件 | `/api/events`（SSE） | PAGE-003 + 全局进度胶囊 |

具体路径、请求体、响应体与字段定义由阶段 3B 产出 `code/docs/api-design.md`，本文件只约定风格、错误语义与分组边界。

### 6.4 SSE 事件约定

- 通道：`GET /api/events`，单向服务端推送，`EventSource` 订阅。
- 事件类型：`job.progress`（编译进度，含当前素材、当前页面、已完成数、累计花费）、`job.done`、`job.failed`、`lint.ready`、`source.status`（素材状态变更）。
- 断线重连：前端自动重连；重连后先调 `GET /api/compile/current` 取当前任务快照，避免只依赖事件导致状态丢失（ERROR-007）。
- 心跳：每 15 秒发送注释行，避免中间层超时断开。

---

## 7. 构建、运行与部署

### 7.1 首次准备

```powershell
# 后端依赖
cd code/backend
uv sync

# 前端构建产物（仅构建期需要 Node）
cd ../frontend
npm install
npm run build
```

### 7.2 日常启动

```powershell
# 仓库根目录
pwsh -File code/scripts/start.ps1
```

脚本行为：检查 `frontend/dist` 是否存在（缺失则提示先构建）→ 以 `--host 127.0.0.1 --port 8765` 启动 uvicorn → 打印实际访问地址 → 端口被占用时自动顺延到下一个可用端口并打印（ADR-013）。

### 7.3 开发态（可选）

前端需要热更新时，单独跑 `npm run dev`，Vite 把 `/api` 代理到后端。**这是可选路径**，日常使用始终是单进程（ADR-001）。

### 7.4 部署与回滚

本机应用，无正式部署环节：

- 代码回滚：`git revert` 或切回上一个提交，重启进程。
- 知识库回滚：vault 是独立仓库，用 `git -C <vault> checkout <commit> -- <path>` 回到任意历史版本；V1 不做回滚 UI（需求第 7 节）。
- 数据迁移：升级不需要迁移脚本，`.llmwiki/` 状态文件缺失时自动重建，`wiki/` 缺失时按空库处理（触发 BRANCH-001）。

---

## 8. 架构决策记录

| 编号 | 决策点 | 背景 | 最终选择 | 被放弃的方案 | 放弃原因 |
|---|---|---|---|---|---|
| ADR-001 | 交付形态 | 需求：本机浏览器访问、手动命令行启动、单人维护 | 单进程同时提供 REST + SSE + React 构建产物 | 前后端双常驻进程；Tauri 桌面壳 | 双进程需常驻两个服务、配置 CORS 与 SSE 代理，与「一条命令启动」冲突；桌面壳与已确认的交付形态不符，且引入 Rust 与 sidecar 生命周期管理 |
| ADR-002 | 后端语言与框架 | 需求：文件优先、单人维护，且本机已具备 Python 与 Java 工具链 | Python 3.12 + FastAPI + Uvicorn | Java 17 + Spring Boot；Node + NestJS | Spring Boot 对单机小工具属重量级（JVM 启动、构建链、ORM 心智负担）；Node 生态中 PDF/正文抽取类库弱于 Python |
| ADR-003 | 前端形态 | 13 个页面已有成品级静态原型，用户选定 React | React 19 + TypeScript + Vite，产物由后端托管 | 原生 ES Module 零构建；Vue 3 | 用户明确要求 React；零构建在 13 页规模下会重复手写状态与路由逻辑 |
| ADR-004 | 知识库仓库 | 需求：自动 commit + 可带走 + 不被锁定 | vault 为**独立 git 仓库**，路径可配，可设远端与 SSH key | 与代码同仓；数据库托管 | 用户选择独立仓库，避免知识提交污染代码历史；数据库违背文件优先 |
| ADR-005 | 进度推送 | UX：围观页实时进度 + 离开后后台继续 | SSE（`EventSource`） | 轮询；WebSocket | SSE 单向、实现简单、自动重连；轮询延迟与请求量差；WebSocket 对本场景是过度设计 |
| ADR-006 | 运行时状态存放 | 需求只定义 `raw/` 与 `wiki/` 两套 md，但任务/体检/历史/成本需要落盘 | vault 内 `.llmwiki/` 存 JSON 状态 | SQLite；把状态塞进 `wiki/` 的 md | 引入数据库违背文件优先且不便随仓库带走；把运行时状态写成 wiki 页面会污染知识层并干扰孤儿页与图谱统计 |
| ADR-007 | 图谱渲染 | UI：设计 token 唯一来源，图谱需分区筛选与 1/2 层深度 | d3-force + d3-zoom 自绘 SVG | cytoscape | cytoscape 自带样式体系，与 `tokens.css` 双份样式来源，UI-AC-009 与 UI-AC-004 难保证 |
| ADR-008 | Python 依赖管理 | 本机已装 uv，需锁定 3.12 | uv（pyproject + uv.lock） | pip + requirements.txt | 无法锁 Python 版本、无解析锁文件、Windows 上复现性差 |
| ADR-009 | git 同步策略 | 需求 U-09 只要求自动 commit | 自动 commit + 设置页手动「立即同步」推送（`auto_push` 默认关闭） | 每次提交自动 push | 自动推送会在误操作时把错误内容推到远端，风险高于收益 |
| ADR-010 | API key 存放 | 需求：key 不进版本库，本机安全存储 | 仓库外 `%APPDATA%\llmwiki\settings.json` | vault 内配置文件 + gitignore | 放在 vault 内即使 gitignore 也有被误提交与随仓库外传的风险 |
| ADR-011 | wiki 页面组织 | 需求模块含页面类型定义，图谱与体检需按类型统计 | 按页面类型分目录（sources / concepts / entities / analyses），`type` 字段为权威 | 全部平铺在 `wiki/` 根目录 | 平铺后人工浏览与类型统计都变差，且与设计稿的来源区、类型徽标语义脱节 |
| ADR-012 | 长文与超大 PDF | 需求约束：长文分段处理以控成本；单次编译成本可观 | 超阈值先分段摘要再合成，围观页显示分段进度 | 直接截断超长正文；一次性全文投喂 | 截断会丢结论造成幻觉；全文投喂在长 PDF 上成本与超时风险都不可控 |
| ADR-013 | 服务端口 | 本机可能被其他工具占用 8765 | 固定 8765，占用时自动顺延并打印实际地址 | 强制固定端口直接报错退出；随机端口 | 报错退出对非技术流程不友好；随机端口无法写死书签 |

---

## 9. 技术风险

| 风险 | 影响 | 应对 |
|---|---|---|
| TypeScript 7.0.2 是全新原生版编译器，生态兼容性未知 | 前端可能无法构建或类型检查异常 | 若 `npm run build` 失败，降级到 TypeScript 5.x（仅版本号改动，不影响架构） |
| LLM 输出结构不稳定，编译期写坏页面或链接 | 知识层出现脏数据 | 所有落盘经 `schema/` 校验与归一化；页面名冲突时改名而非覆盖；单次任务完成后仍可用 git 回退 |
| 长 PDF 编译成本与超时叠加 | 任务失败、成本失控 | ADR-012 分段处理；单任务成本上限与超时上限可配；成本看板可见 |
| 抓取站点反爬或结构变更 | 部分网页素材解析质量下降 | 解析失败不阻塞其他素材（ERROR-002）；保留原文快照供人工补录 |
| `raw/` 与 `wiki/` 被外部编辑器（Obsidian）同时改动 | 写前读最新版仍有竞态窗口 | 写前重新读取 + 原子替换；变更清单展示实际落盘结果；冲突交由 git 可见 |
| 图谱在页数增长后渲染变慢 | 交互卡顿 | 默认 1 层深度、分区筛选；超过 200 页按需求 U-10 评估引入检索引擎 |
| Windows 上文件占用导致 `os.replace` 失败 | 写入任务失败 | 重试 + 明确错误码；提示关闭占用文件的外部程序 |
| 自动体检与用户操作争抢写锁 | 交互变慢或任务排队 | 体检任务优先级低于用户任务；体检只读扫描，仅在写报告时短暂持锁 |

---

## 10. 待确认事项处理结果

| 编号 | 待确认事项 | 处理方式 | 最终结论 |
|---|---|---|---|
| ARCH-TBD-001 | 运行时状态目录放在哪 | 确认 | vault 内 `.llmwiki/` 存 JSON，随 git 提交（ADR-006） |
| ARCH-TBD-002 | 是否实现 git 远端推送 | 确认 | 实现，但默认关闭自动推送，设置页手动「立即同步」（ADR-009） |
| ARCH-TBD-003 | API key 存放位置 | 确认 | 仓库外 `%APPDATA%\llmwiki\settings.json`（ADR-010） |
| ARCH-TBD-004 | 图谱渲染技术 | 确认 | d3-force + d3-zoom 自绘 SVG（ADR-007） |
| ARCH-TBD-005 | wiki 目录组织方式 | 确认 | 按页面类型分目录，`type` frontmatter 为权威（ADR-011） |
| ARCH-TBD-006 | 服务端口策略 | 确认 | 固定 8765，占用自动顺延并打印（ADR-013） |
| ARCH-TBD-007 | 长文与超大 PDF 处理 | 确认 | 分段摘要再合成，围观页显示分段进度（ADR-012） |
| ARCH-TBD-008 | 是否保留 Vite dev server | 确认 | 保留为可选开发路径，日常始终单进程（ADR-001） |

无未处理事项，无新增待确认点。

---

## 11. 人工确认结论

**用户已确认的架构决策：**

- 交付形态：单进程单体，`127.0.0.1` 浏览器访问，无账号鉴权
- 技术栈：Python 3.12 + uv + FastAPI；React 19 + TypeScript + Vite；SSE 推流
- 知识库：独立 git 仓库，可配远端与 SSH key
- 运行时状态：vault 内 `.llmwiki/` JSON
- 图谱：d3-force 自绘
- 长文处理：分段摘要再合成
- 全部 13 条 ADR 与 8 项 `ARCH-TBD-###` 处理结论

**同步修订的方法文档：**

`docs/stages/03-implementation/README.md` 原预写 `code/backend` 为 Maven + Spring Boot、`code/frontend` 为 Vite + Vue，与本次选型不符，已改为 Python + FastAPI 后端、React + Vite 前端。该修订只涉及方法文档的目录说明，不改动任何需求、UX 或 UI 内容。

**阶段完成判断：✅ 阶段 3A 完成。** 架构与需求、UX、UI 无冲突，无过度设计，所有选型均有理由与被放弃方案，版本约束均为实测值。本文档固化为 `code/docs/tech-architecture.md`，阶段 3B 可开始。
