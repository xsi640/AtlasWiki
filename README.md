# LLM Wiki

个人知识库，按 Andrej Karpathy 的 **LLM Wiki** 范式实现 —— 用「知识编译」替代 RAG。

不是切块 + 向量嵌入 + 相似度检索。而是让模型**增量维护一个持久化的 Markdown wiki**：
新素材进来时读原文、抽取概念、更新实体页与概念页、标注新旧说法的矛盾、重建索引。
文件是唯一真相来源，每条陈述都能追溯到具体的 `.md`。

```
RAG        上传 → 切块 → 向量 → 查询时召回 → 生成        （每次都在从头重新发现知识）
LLM Wiki   raw/ → LLM 编译 → wiki/ → 查询时读索引+读页面  （知识一次编译、持续复利）
```

## 快速开始

```bash
./run.sh --setup     # 首次运行：创建 .venv 并安装依赖
./run.sh             # 启动，默认 http://127.0.0.1:8765
```

打开浏览器 → 左上角「收录素材」→ 粘贴链接 → 自动落盘到 `raw/` → 自动编译进 `wiki/`。

## 支持的输入

| 类型 | 说明 |
|---|---|
| 抖音分享链接 | `v.douyin.com/xxx` 短链、`douyin.com/video/xxx`，也支持整段分享文案 |
| B 站分享链接 | `bilibili.com/video/BVxxx`、`b23.tv/xxx`，抓标题/简介/UP主/标签/热评 |
| 网页 URL | 任意文章页，trafilatura + 自研正文提取双通道 |
| 文档 | `.docx` `.doc` `.rtf` `.pdf` `.md` `.txt` `.html` |
| 纯文本 | 直接粘贴 Markdown 或笔记 |

> B 站视频的**逐字稿**需要登录态。在「设置 → 抓取」里填上 `bilibili_cookie`（浏览器 Cookie 里的 `SESSDATA`）即可抓到 CC / AI 字幕。

## 目录结构

```
data/kb/                    ← 知识库（可以直接用 Obsidian / 编辑器打开）
├── raw/                    原始素材，不可变。你和采集器写，LLM 只读
│   └── assets/
└── wiki/                   LLM 维护的知识层，你只读
    ├── index.md            内容索引：所有页面 + 一句话摘要
    ├── log.md              append-only 操作日志
    ├── overview.md         跨素材的综述与主线
    ├── conventions.md      你写给 LLM 的偏好
    ├── sources/            素材页（一篇素材一页）
    ├── entities/           实体页（人物、组织、产品）
    ├── concepts/           概念页（理论、方法、术语）
    └── analyses/           分析页（对比、问答归档、体检报告）
```

整个 `data/kb/` 就是一个 git 仓库友好的 Markdown 文件夹，随时可以搬走或版本管理。

## 三个核心操作

| 操作 | 做什么 |
|---|---|
| **收录 ingest** | 素材落 `raw/` → LLM 读原文 → 写素材页 → 更新相关的实体页/概念页 → 重建索引 → 记日志 |
| **提问 query** | LLM 先读 `index.md` 定位相关页面 → 逐个读取 → 综合作答并标注来源页面；好答案可以一键归档回 `wiki/analyses/` |
| **体检 lint** | 结构检查（孤儿页、失效链接、陈旧页面、缺失概念页）+ LLM 语义检查（矛盾、陈旧说法、数据缺口） |

## 配置大模型

编辑 `config.yaml`：

```yaml
llm:
  enabled: true                         # 硬开关；设 false 则强制用确定性编译器（即使填了 Key）
  base_url: https://api.openai.com/v1   # 任何 OpenAI 兼容接口
  api_key: sk-xxxxxxxx                  # 填上即启用
  model: gpt-4o-mini
```

DeepSeek、通义千问、Kimi、Ollama、vLLM 都可用，只要兼容 `/chat/completions` 且支持 function calling。

想临时对比「LLM 编译」和「确定性编译」的差别时，把 `enabled` 设成 `false` 再重建一次即可，
不用把 API Key 删掉。

**没有 API Key 也能用**：系统会启用内置的「确定性编译器」，
它仍然按同样的目录约定生成素材页、概念页、双链、索引与日志，
只是正文由关键词聚合的原文摘录构成，而不是 LLM 撰写的百科条目。
填上 Key 之后重新编译一次，页面就会被重写成真正的百科条目。

## 工作原理

`app/` 模块划分：

| 文件 | 职责 |
|---|---|
| `vault.py` | 文件层。raw/wiki 读写、YAML frontmatter、`[[双链]]` 解析、反向链接、index/log 维护 |
| `schema.py` | **SCHEMA 提示词**，等价于 Karpathy 方案里的 `CLAUDE.md`，定义结构约定与三个工作流 |
| `agent.py` | LLM Agent 工具循环。给模型 10 个文件系统工具：`list_wiki` / `read_wiki` / `write_wiki` / `edit_wiki` / `append_wiki` / `search_wiki` / `list_raw` / `read_raw` / `rebuild_index` / `append_log` |
| `compiler.py` | 无 API Key 时的确定性编译兜底 |
| `lint.py` | 结构体检 + 报告生成 |
| `ingest/` | 各来源的采集器（抖音 / B站 / 网页 / 文档），统一归一化为 Markdown |
| `main.py` | FastAPI 接口层 |

关键点：**模型拿到的是文件系统工具，不是检索器**。
查询时它自己读 `index.md` 找相关页面、自己决定读哪几页、自己写页面。
这就是 LLM Wiki 与 RAG 的分界线。

## 规模

Karpathy 的经验是：约 100 篇素材、数百个页面时，`index.md` + 摘要已经足够让模型高效定位信息，
不需要 embedding 基础设施。超过这个量级可以接 [qmd](https://github.com/tobi/qmd) 之类的本地
Markdown 搜索引擎给模型当工具用 —— 注意是**给模型用的工具**，不是答案引擎本身。

## 常用快捷键

- `⌘K` / `Ctrl+K` 聚焦搜索框
- `⌘Enter` / `Ctrl+Enter` 发送提问
