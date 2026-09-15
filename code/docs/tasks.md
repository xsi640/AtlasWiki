# 任务文档

> 状态：**已定稿**，作为阶段 4 测试阶段的输入
> 方法：SoloForge 阶段 3B v0.3
> 日期：2026-09-15
> 输入：`code/docs/tech-architecture.md`、`code/docs/api-design.md`
> 并行编码方式：`docs/stages/03-implementation/coding/SKILL.md`

---

## 1. 实现范围与顺序

### 1.1 实现顺序

需求第 7 节要求四个动作**串行推进、逐动作独立验收**。任务按此顺序编排为 6 个波次：

| 波次 | 内容 | 交付后可日用 |
|---|---|---|
| Wave 0 | 公共地基：工程骨架、存储层、任务队列与 SSE、审计、LLM 客户端、Schema | 进程能启动、能打开界面、能读写 vault |
| Wave 1 | Ingest 动作（MODULE-001 / 002 + 前端 PAGE-002 / 003 / 004 / 010 / 013） | **是** —— 最小可运行闭环达成 |
| Wave 2 | 浏览与图谱（MODULE-004 读侧 + PAGE-005 / 006 / 007 / 008） | 是 —— 浏览与图谱动作可日用 |
| Wave 3 | Query（MODULE-005 + PAGE-001 / 009） | 是 —— 问答动作可日用 |
| Wave 4 | Lint（MODULE-006 + PAGE-011 + 待处理提醒） | 是 —— 体检动作可日用，四个动作齐备 |
| Wave 5 | 设置与收尾（PAGE-012、部署脚本、端到端验证、忽略规则、文档回填） | 交付 |

### 1.2 最小可运行闭环

Wave 0 完成后，以 Wave 1 的最小切片构成闭环：

```text
配置 vault 路径
→ 打开应用（空库 → 首页落到素材投放页，BRANCH-001）
→ 粘贴 URL / 上传 PDF / 手写笔记任选一种导入（MODULE-001）
→ 触发编译（MODULE-002）
→ 围观页通过 SSE 实时看到正在读哪份素材、正在写哪个页面（PAGE-003 / STATE-007）
→ 编译完成落到变更清单（PAGE-004），看到新页面、改动与自动分区
→ 点击新页面入口，页面能正常渲染
```

达成闭环即 Wave 1 完成，此后可日常使用并进入 Wave 2。

### 1.3 不在本次实现范围

需求第 7 节「暂不做」的全部条目；架构第 1.4 节复述的同一清单。特别地：不做独立定时调度器（体检只由启动 + 闲置触发）、不做回滚 UI、不做向量检索、不做多人鉴权。

---

## 2. 任务清单

任务粒度按「一次能做完并验证」确定。状态取值：待处理 / 进行中 / 待验证 / 已完成 / 已阻塞。

### Wave 0 · 公共地基

| 任务编号 | 任务名称 | 模块 | 依赖项 | 验收标准 | 状态 |
|---|---|---|---|---|---|
| TASK-001 | 后端工程骨架与配置 | 公共 | 无 | `uv sync` 成功；`uv run python -m llmwiki` 启动后 `GET /api/system/health` 返回 200 且 `llm.configured` 正确反映当前 key 状态；密钥文件写入 `%APPDATA%\llmwiki\settings.json` 且仓库内无任何 key 痕迹；ruff 检查通过 | 已完成 |
| TASK-002 | 前端工程骨架与设计系统移植 | 公共 | 无 | `npm run build` 成功产出 `frontend/dist`；`tokens.css` 与 `code/design/tokens.css` 内容一致；路由壳与顶栏渲染出 13 页占位；浅色/深色切换生效且 `<html data-theme>` 正确；无横向滚动（S 档顶栏不重叠） | 已完成 |
| TASK-003 | Wiki 存储与链接层 | MODULE-003 | TASK-001 | 能创建 vault 骨架目录；frontmatter 读写往返一致（含中文与数组字段）；`[[链接]]` 解析正确（含 `[[名|显示文本]]`）；反向链接与出链计算正确（构造 5 页 8 边的样本断言结果）；原子写在写入过程中断时不产生半截文件；非法路径（`..`、绝对路径、盘符）被拒绝 | 已完成 |
| TASK-004 | 写入队列与 SSE 事件总线 | 公共 | TASK-001 | 并发提交 10 个写任务时严格串行执行（断言执行区间不重叠）；任务进度可查询且与 `jobs.json` 一致；`GET /api/events` 能收到 `job.progress` 与心跳；多标签页同时订阅都能收到事件；进程重启后未完成任务的状态可从 `jobs.json` 恢复 | 已完成 |
| TASK-005 | 审计与 git 底座 | MODULE-008 | TASK-003 | 每次写入任务完成后自动 commit，提交信息含任务类型与影响文件数；`wiki/log.md` 为 append-only 且记录操作类型、影响页面、原因；页面级 diff 可生成；`POST /api/settings/git/sync` 在无远端时返回 `E_GIT_FAILED` 且 `details.stderr` 非空；仓库无远端时不阻塞本地 commit | 已完成 |
| TASK-006 | LLM 客户端与成本记账 | MODULE-009 | TASK-001 | 能调用 OpenAI 兼容端点并拿到响应；流式与非流式均可用；超时映射为 `E_LLM_TIMEOUT`、401/402 映射为 `E_LLM_AUTH`、429 映射为 `E_LLM_RATE_LIMIT`；每次调用按模型单价记账写入 `costs.json`；无 key 时返回 `E_LLM_NOT_CONFIGURED` 而非崩溃 | 已完成 |
| TASK-007 | 知识规范 Schema 与提示词 | MODULE-007 | TASK-003 | 页面类型、frontmatter 字段、命名规范以代码常量与校验函数形式定义；`type`/`source_type` 非法值被校验拒绝；ingest / query / lint 三种操作的提示词模板可加载；页面名规范化函数对中文、空格、特殊字符、重名都能产出合法且唯一的文件名 | 已完成 |

### Wave 1 · Ingest 动作

| 任务编号 | 任务名称 | 模块 | 依赖项 | 验收标准 | 状态 |
|---|---|---|---|---|---|
| TASK-008 | 网页素材解析与导入 | MODULE-001 | TASK-003, TASK-007 | 粘贴 URL 能抓取并抽出正文（含标题、作者、发布时间）；正文抽取失败的站点返回 `E_PARSE_FAILED` 且不产生半成品文件；抓取超时可控；非 2xx 响应有明确错误；同一 URL 重复导入返回 `E_DUPLICATE_SOURCE` 且 `details.existing` 正确 | 待处理 |
| TASK-009 | PDF 素材解析与导入 | MODULE-001 | TASK-003, TASK-007 | 上传 PDF 能抽出文本并落 `raw/assets/`；文本可抽取的 PDF 正文完整；加密或损坏 PDF 返回 `E_PARSE_FAILED` 且原件保留；扫描版（无文本层）给出明确失败原因而非空正文 | 待处理 |
| TASK-010 | 手写笔记与素材元数据 | MODULE-001 | TASK-003, TASK-007 | 新建笔记能落盘并成为独立素材；编辑标题/标签/备注/metadata 后状态置 `stale` 且响应 `needs_recompile: true`；`web`/`pdf` 传 `content` 返回 `E_SOURCE_NOT_EDITABLE`；`note` 类正文可改且 `content_editable = true`；素材索引 `sources-index.json` 与磁盘一致（新增、改名、删除后均一致） | 待处理 |
| TASK-011 | 素材生命周期：软删除、恢复、重编译 | MODULE-001 | TASK-010, TASK-004 | 软删除只改状态、文件保留、返回受影响页面数与列表；删除后 `GET /api/sources?status=deleted` 能查到、`normal` 查不到；恢复后状态回 `normal`；重编译走同一队列并复用既有派生页面（不新建重复页）；编译中的素材被编辑或删除返回 `E_SOURCE_BUSY` | 待处理 |
| TASK-012 | 素材 API 接口层 | MODULE-001 | TASK-008, TASK-009, TASK-010, TASK-011 | API-014 ~ API-023 全部可用；`status` 多值筛选与 `counts` 统计正确；分页参数生效且 `size` 上限 200；错误码与 api-design 第 4 节逐条一致；上传大小超限有明确错误 | 待处理 |
| TASK-013 | 编译引擎：读取与生成 | MODULE-002 | TASK-003, TASK-006, TASK-007 | 编译一份素材能产出摘要页，并新建或更新受影响的概念页/实体页；页面互链形成且 `links` 字段与正文中的 `[[链接]]` 一致；`index.md` 随编译更新；LLM 返回非法结构时不写坏文件（校验后再落盘）；编译过程每一步都通过队列发进度事件 | 待处理 |
| TASK-014 | 编译引擎：增量分区与矛盾标记 | MODULE-002 | TASK-013 | 分区判定只作用于本次受影响页面（断言未受影响页面的 `zone` 未被改写）；`zone` 写入 frontmatter 并记入 log；分区变更在变更清单中为 `zone_changed` 且保留 `zone_before`；发现的新旧矛盾被记录供体检消费；`human_edited` 页面的 `zone` 不由编译过程擅自改写 | 待处理 |
| TASK-015 | 长文分段与成本上限 | MODULE-002 | TASK-013 | 超过 `segment_threshold_chars` 的素材走分段摘要再合成，围观页 `steps` 显示分段进度；单任务成本超过 `max_cost_per_job` 时停止并置任务 `failed` 且原因明确；未超阈值的长文不走分段（断言调用次数不增加） | 待处理 |
| TASK-016 | 编译与变更清单 API | MODULE-002, MODULE-008 | TASK-012, TASK-013, TASK-015 | API-024 ~ API-027 可用；`GET /api/compile/current` 在无任务时返回 `status: idle`；断线重连后快照与实际进度一致（ERROR-007）；变更清单区分 `created`/`updated`/`zone_changed` 且 `has_diff` 正确；部分素材失败时 `failed_sources` 有内容且已产出页面保留 | 待处理 |
| TASK-017 | 前端 PAGE-002 素材投放页 | MODULE-004 | TASK-002, TASK-012 | 三种入口同屏并列并都能成功提交；空库时首页落到本页（BRANCH-001 / STATE-006）；导入失败就地显示 STATE-010 与重试/移除；重复素材提示 ERROR-003 并给「重新编译」；主操作行在任意滚动位置可见；1440×900 下与 UI-009 布局一致 | 待处理 |
| TASK-018 | 前端 PAGE-003 编译围观页 | MODULE-004 | TASK-002, TASK-004, TASK-016 | 通过 SSE 实时更新当前素材、当前页面、已完成数与步骤状态；显示累计花费（不显示 token）；显示「可离开」并在离开后顶部保留进度胶囊（BRANCH-002）；完成后跳转变更清单；断线后重连能恢复到正确进度 | 待处理 |
| TASK-019 | 前端 PAGE-004 变更清单页 | MODULE-004 | TASK-002, TASK-016 | 展示本次改动页面、新页面入口、自动分区结果；可逐页展开 diff（INTERACTION-012）；可一键改分区并立即反映到结果（INTERACTION-011 / BRANCH-004）；失败素材单独分区展示并可重试 | 待处理 |
| TASK-020 | 前端 PAGE-010 / PAGE-013 素材管理页 | MODULE-004 | TASK-002, TASK-012 | 素材库支持四态筛选且各态数量正确（INTERACTION-020）；`web`/`pdf` 的编辑按钮为「编辑元数据」且正文区不可编辑；`note` 可改正文；保存后提示「需重编译」并给立即重编译入口（CONTENT-007）；软删除二次确认展示受影响页面数（ERROR-010）；已删除可恢复；原文页展示派生页面并可跳转 | 待处理 |

### Wave 2 · 浏览与图谱

| 任务编号 | 任务名称 | 模块 | 依赖项 | 验收标准 | 状态 |
|---|---|---|---|---|---|
| TASK-021 | 页面、反链与搜索读接口 | MODULE-004 | TASK-003, TASK-013 | API-004 ~ API-009、API-013 可用；反链与出链双向一致（对同一批页面互查结果吻合）；`human_edited` 页面保存后标记为 `true`；搜索返回带 `<mark>` 的片段且命中位置正确；空查询与超长查询返回 `E_VALIDATION`；分页与类型筛选正确 | 已完成 |
| TASK-022 | 图谱与分区读接口 | MODULE-004 | TASK-021 | API-010 ~ API-012 可用；`depth=1` 与 `depth=2` 的节点数符合邻域定义；孤儿页仍出现在节点集合中；`depth=2` 超过 300 节点时 `truncated = true`（TASK-TBD-006）；分区筛选后边不产生悬空引用（边的两端都在节点集合内）；分区列表的页面数之和等于总页面数 | 已完成 |
| TASK-023 | 前端 PAGE-005 页面详情页 | MODULE-004 | TASK-002, TASK-021 | 正文渲染正确（含表格、代码块、`[[链接]]`）；内联链接、反链面板、来源区三方向可进出且都跳同一页面详情（UX-AC-004）；失效链接走 ERROR-006 提示路径；`human_edited` 页面显示 STATE-009 提示；人工编辑保存后标记出现（INTERACTION-016）；分区可改并记入变更记录；正文行宽 ≤ 820px | 已完成 |
| TASK-024 | 前端 PAGE-006 全局图谱页 | MODULE-004 | TASK-002, TASK-022 | d3-force 渲染节点与边，样式取自 `tokens.css`（无硬编码颜色）；分区筛选与 1/2 层深度切换生效；点节点跳页面详情；孤点可见；200 节点规模下交互不阻塞；`truncated` 时有明确提示；画布高度随视口弹性且不产生横向滚动 | 已完成 |
| TASK-025 | 前端 PAGE-007 分区浏览与 PAGE-008 搜索页 | MODULE-004 | TASK-002, TASK-021, TASK-022 | 分区页为「分区列表 → 分区内页面」，S 档分区导航转横向滚动而非隐藏；搜索页展示命中片段与 `<mark>` 高亮，无结果走 ERROR-004 空态并给出投放/浏览出口；V1 不出现高级筛选控件；两页在 1440×900 与 1120 宽下均无横向滚动 | 已完成 |

### Wave 3 · Query

| 任务编号 | 任务名称 | 模块 | 依赖项 | 验收标准 | 状态 |
|---|---|---|---|---|---|
| TASK-026 | 问答引擎 | MODULE-005 | TASK-013, TASK-021 | 提问能选取候选页并跨页综合作答；答案中引用为真实存在的页面名，`citations` 与实际参与页面一致；`pages_considered` 为实际读取页数；知识不足时 `sufficient = false` 并给出最多 5 个相关页（不编造答案）；答案落 `queries.json` 并可回放 | 待处理 |
| TASK-027 | 问答 API 与答案回填 | MODULE-005 | TASK-026 | API-028 ~ API-032 可用；回填生成的新页面 `source_type = query-generated`、`type = analysis`、落在 `wiki/analyses/`；回填后原记录 `saved_page` 非空（TASK-TBD-005）；重复回填同一答案不被允许或幂等；删除问答后历史列表与详情一致 | 待处理 |
| TASK-028 | 前端 PAGE-001 首页问答台与 PAGE-009 历史页 | MODULE-004 | TASK-002, TASK-027 | 输入为空时不可提交；提交后显示「正在综合 N 个页面」（N 来自 `pages_considered`）；引用可点击跳转（SC-1a）；「存为页面」为次要入口且不打断主流程；`sufficient = false` 时显示 STATE-011 并列出相关页；历史页列表 + 单条展开 + 单条删除（幽灵按钮 + 危险色）；已归档条目显示标记；空库时整页替换为 PAGE-002 内容 | 待处理 |

### Wave 4 · Lint

| 任务编号 | 任务名称 | 模块 | 依赖项 | 验收标准 | 状态 |
|---|---|---|---|---|---|
| TASK-029 | 体检扫描五类检查 | MODULE-006 | TASK-021, TASK-022 | 矛盾、孤儿页、失效链接、缺失索引、分区混杂五类都能检出（构造含全部五类的样本 vault 断言命中）；`repairable` 判定正确（结构性为 true，语义类为 false）；扫描为只读，不修改任何页面；孤儿页占比与平均出链可计算（对应 SC-3） | 待处理 |
| TASK-030 | 体检 API、触发与修复 | MODULE-006 | TASK-004, TASK-029 | API-033 ~ API-036 可用；启动时触发一次、闲置 30 分钟后触发一次（不得引入定时调度器）；报告落 `.llmwiki/lint-report.json` 而非 wiki 页面；修复只改结构性条目且**不覆盖** `human_edited` 页面（改为标注需人工处理）；忽略必须带原因，缺原因返回 `E_VALIDATION`；`counts.total` 与 `groups` 实际条目数一致 | 待处理 |
| TASK-031 | 前端 PAGE-011 体检报告页与待处理提醒 | MODULE-004 | TASK-002, TASK-030 | 五类分组展示且逐条可勾选；`repairable = false` 的条目只允许忽略；忽略时强制填写原因（INTERACTION-023 / UX-TBD-003）；页头常驻「自动生成但不会自动修复」（UX-AC-005）；右栏列出已忽略项与原因可回查；导航栏常驻「N 个待处理」并在修复/忽略后即时更新（CONTENT-006）；无待处理项时显示 STATE-008 | 待处理 |

### Wave 5 · 设置与收尾

| 任务编号 | 任务名称 | 模块 | 依赖项 | 验收标准 | 状态 |
|---|---|---|---|---|---|
| TASK-032 | 设置、成本与系统 API | MODULE-009, MODULE-008 | TASK-005, TASK-006 | API-001 ~ API-003、API-037 ~ API-042 可用；API key 只回显末 4 位、永不返回完整值；`test-connection` 能区分鉴权失败与超时；成本看板按日/按操作统计与 `costs.json` 一致；`pricing_source` 正确反映内置或自定义；打开数据文件夹能实际唤起系统文件管理器 | 待处理 |
| TASK-033 | 前端 PAGE-012 设置页 | MODULE-004 | TASK-002, TASK-032 | provider / base_url / 模型 / key / 限额可配置并保存生效；成本看板展示累计、按日、按操作；「打开数据文件夹」为页内主按钮（G-7 / UX-AC-008）；git 远端、分支、SSH key 可配置并可手动同步；同步失败展示 git 输出；深浅主题可切换且浅色为默认（UI-TBD-003） | 待处理 |
| TASK-034 | 启动脚本与部署说明 | 公共 | TASK-001, TASK-002 | `code/scripts/start.ps1` 能检查 `dist` 缺失并给出提示、启动服务、打印实际地址；端口占用时自动顺延并打印新端口；`code/deploy/` 含环境要求、启动方式、故障排查；在干净环境下按文档操作能成功启动 | 待处理 |
| TASK-035 | 端到端验证脚本 | 公共 | TASK-016, TASK-023, TASK-028, TASK-031, TASK-033 | 脚本可独立完成：建临时 vault → 启动服务 → 导入三类素材之一 → 编译 → 断言 wiki 出现页面与索引 → 提问并断言引用页真实存在 → 跑体检并断言五类检查可执行 → 关闭服务 → 清理；失败时打印服务端日志尾部；退出码非 0 表示失败；重复执行不残留状态（幂等） | 待处理 |
| TASK-036 | 忽略规则、文档回填与收尾 | 公共 | TASK-035 | `.gitignore` 覆盖 `.venv`/`node_modules`/`dist`/`.llmwiki` 的运行期垃圾但不忽略知识内容；仓库内无 API key；`implementation-record.md` 记录实现过程与集成阶段缺陷；`tasks.md` 状态全部回填；无临时文件残留 | 待处理 |

**任务统计**：36 个任务，覆盖 9 个模块 + 公共基础设施。

---

## 3. 任务依赖与并行分组

### 3.1 并行分组

按 `coding/SKILL.md` 的「先冻结契约再并行」原则分组。同一组内的任务写入范围互斥，可并行交给子代理；跨组按依赖顺序推进。

| 分组 | 任务 | 写入范围 | 可并行 | 前提 |
|---|---|---|---|---|
| G0 契约层（**协调者自己做**） | TASK-001 的公共层部分、TASK-003 的接口签名、TASK-007 的常量与校验函数、共享 TS 类型 | `backend/src/llmwiki/{config,errors,models}.py`、`frontend/src/api/types.ts`、`tokens.css` | 否（必须一次冻结） | 无 |
| G1 公共设施 | TASK-004、TASK-005、TASK-006 | 各自独立文件 | 是（3 路） | G0 |
| G2 素材接入 | TASK-008、TASK-009、TASK-010、TASK-011 | `ingest/` 下各自模块 | 是（4 路） | G0 |
| G3 编译引擎 | TASK-013、TASK-014、TASK-015 | `compile/` 下各自模块 | 部分（013 → 014/015 有先后） | G0、G1 |
| G4 前端 Wave 1 | TASK-017、TASK-018、TASK-019、TASK-020 | `frontend/src/pages/` 各自页面 | 是（4 路） | G0、TASK-002 |
| G5 前端 Wave 2 | TASK-023、TASK-024、TASK-025 | 各自页面 | 是（3 路） | TASK-021、TASK-022 |
| G6 问答 | TASK-026、TASK-027 | `ask/` | 串行（026 → 027） | G3 |
| G7 体检 | TASK-029、TASK-030 | `lint/` | 串行（029 → 030） | G3 |
| G8 收尾 | TASK-032、TASK-033、TASK-034、TASK-035、TASK-036 | 各自独立 | 部分并行 | 各波次完成 |

**共享文件由协调者独占**：`main.py`（应用装配与路由注册）、`pyproject.toml`、`vite.config.ts`、`package.json`、`router.tsx`、`App.tsx`、`tokens.css`、`jobs.py`、`errors.py`。子代理发现契约问题只能上报，不得自行修改。

### 3.2 关键路径

```text
TASK-001 → TASK-003 → TASK-007 → TASK-013 → TASK-016 → TASK-018 → TASK-021 → TASK-026 → TASK-029 → TASK-031 → TASK-035
```

关键路径上的任务延期会整体推迟交付。其中 TASK-003（存储层）与 TASK-013（编译引擎）是两个最大风险点：前者是所有模块的地基，后者依赖 LLM 输出的稳定性。

**非关键路径上可提前并行**的：TASK-002（前端骨架）、TASK-006（LLM 客户端）、TASK-034（启动脚本）。

### 3.3 阻塞说明

当前无阻塞任务。

---

## 4. 任务进度状态汇总

| 状态 | 数量 | 任务 |
|---|---|---|
| 已完成 | 7 | TASK-001 ~ TASK-007（Wave 0 公共地基） |
| 进行中 | 9 | TASK-008 ~ TASK-011、TASK-013（G2/G3 并行中） |
| 待处理 | 20 | TASK-012、TASK-014 ~ TASK-036 |

| 待验证 | 0 | — |
| 已完成 | 0 | — |
| 已阻塞 | 0 | — |

**按模块统计**

| 模块 | 任务数 |
|---|---|
| MODULE-001 素材接入 | TASK-008 ~ TASK-012（5） |
| MODULE-002 编译引擎 | TASK-013 ~ TASK-016（4） |
| MODULE-003 Wiki 存储与链接 | TASK-003（1） |
| MODULE-004 浏览与图谱 | TASK-017 ~ TASK-025、TASK-028、TASK-031、TASK-033（13） |
| MODULE-005 问答 | TASK-026、TASK-027（2） |
| MODULE-006 体检与维护 | TASK-029、TASK-030（2） |
| MODULE-007 知识规范 | TASK-007（1） |
| MODULE-008 变更记录与审计 | TASK-005（并入 TASK-016 / TASK-032） |
| MODULE-009 设置与模型接入 | TASK-006（并入 TASK-032） |
| 公共 | TASK-001、TASK-002、TASK-004、TASK-034 ~ TASK-036（6） |

架构中 9 个 `MODULE-###` 全部有对应任务，无遗漏模块。MODULE-008 与 MODULE-009 的接口部分分别并入 TASK-016 / TASK-032，单独任务见对应行，不重复计数。

---

## 5. 待确认事项处理结果

| 编号 | 待确认事项 | 处理方式 | 最终结论 |
|---|---|---|---|
| TASK-TBD-001 | 是否提供手动触发体检的接口 | 确认 | 提供，见 API-034，按钮置于 PAGE-011 页头 |
| TASK-TBD-002 | 成本看板币种与定价来源 | 确认 | USD；内置定价表 + 允许自定义单价，`pricing_source` 标明来源 |
| TASK-TBD-003 | 打开数据文件夹的实现方式 | 确认 | 后端起子进程调用系统文件管理器，仅显式调用时执行 |
| TASK-TBD-004 | 搜索高亮由谁计算 | 确认 | 后端生成带 `<mark>` 的 `snippet` |
| TASK-TBD-005 | 问答回填后原记录是否标记 | 确认 | 标记 `saved_page`，显示「已归档为页面」 |
| TASK-TBD-006 | 图谱 depth=2 的规模保护 | 确认 | 邻域超 300 节点截断并置 `truncated = true` |
| TASK-TBD-007 | 素材重编译时旧派生页面如何处理 | 确认 | 更新既有派生页面，不新建重复页；不级联删除 |
| TASK-TBD-008 | vault 默认路径 | 确认 | 默认 `%USERPROFILE%\llmwiki-vault`，未配置时引导到设置页，不自动创建 |

实现过程中新发现的待确认点将追加本表，沿用同一编号序列。当前无未处理事项。

---

## 6. 人工确认结论

**用户已确认的内容：**

- 实现顺序：Wave 0 → Ingest → 浏览与图谱 → Query → Lint → 收尾，四个动作逐动作独立验收
- 最小可运行闭环：导入一类素材 → 编译 → 围观进度 → 变更清单 → 打开新页面
- 并行方式：协调者冻结契约后按模块切分给并行子代理，协调者负责集成与端到端验证
- 全部 8 项 `TASK-TBD-###` 处理结论

**约束确认：**

- 未新增需求之外的功能或接口
- 未修改已确认的 UX/UI 流程与页面职责
- 未改动已确认的架构（`tech-architecture.md` 无未处理的 `ARCH-TBD-###`）

**阶段完成判断：⏳ 阶段 3B 文档部分完成。** `tasks.md` 与 `api-design.md` 已生成，任务将按波次推进并持续回填状态；全部任务完成后本文件作为阶段 4 的输入定稿。
