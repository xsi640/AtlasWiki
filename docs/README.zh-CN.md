# AtlasWiki

[English](../README.md)

AtlasWiki 是一个本地优先的知识库编译器。它将网页、PDF 和手写笔记转化为结构化 Markdown Wiki，并提供问答、知识图谱、变更审阅、来源管理和知识质量体检能力。

数据与 API Key 默认保留在本机：知识库是一个独立的 Markdown + Git 仓库，适合个人研究、团队知识沉淀与可追溯的 AI 辅助写作。

## 核心能力

- 导入网页、PDF 和 Markdown/纯文本笔记
- 将素材编译为带来源信息、链接和分区的 Wiki 页面
- 基于已有知识库进行跨页面问答，并显示引用来源
- 浏览知识图谱、搜索页面、查看编译变更与历史记录
- 管理原始素材，编辑笔记并触发重新编译
- 扫描死链、孤儿页等知识库质量问题并提供修复入口
- 使用 OpenAI 兼容接口；支持费用记录、任务进度和可选 Git 同步

## 技术架构

| 层级 | 技术 |
| --- | --- |
| 前端 | React 19、TypeScript、Vite、React Router、D3 |
| 后端 | Python 3.12、FastAPI、Uvicorn、Pydantic |
| 存储 | 本地 Markdown Vault、YAML Front Matter、Git |
| 模型接入 | OpenAI-compatible API |

## 快速开始

### 环境要求

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js 24+ 与 npm
- Git（推荐，用于 Vault 的版本记录）

### 1. 安装并构建

```bash
# 后端依赖
cd backend
uv sync --extra dev

# 前端构建
cd ../frontend
npm install
npm run build
```

### 2. 启动应用

```bash
# macOS / Linux
bash scripts/start.sh

# Windows PowerShell
pwsh -File scripts/start.ps1
```

默认访问地址为 `http://127.0.0.1:8765`。若端口已被占用，应用会自动选择下一个可用端口并输出实际地址。

## 首次使用

1. 打开 **设置**，填写一个本机空目录作为 **Vault 路径**。
2. 配置 OpenAI 兼容的 Base URL、模型名称和 API Key。
3. 在 **投放** 页面导入网页、PDF 或笔记。
4. 导入后运行编译，生成 Wiki 页面。
5. 回到首页提问，或使用图谱、搜索、体检和素材库继续探索。

> Vault 路径中的内容由应用管理，并会创建 `wiki/`、`raw/` 与 `.llmwiki/` 等目录。请为其选择专用目录，不要指向本项目目录。

## 配置与数据

- 应用设置：Windows 为 `%APPDATA%/atlaswiki/settings.json`；macOS 为 `~/Library/Application Support/atlaswiki/`。
- 使用 `ATLASWIKI_CONFIG_DIR` 可覆盖配置目录，适合测试或隔离环境；旧版 LLM Wiki 配置会被自动识别，保证升级兼容。
- API Key 不写入项目文件，也不应提交到版本控制。
- Vault 是独立 Git 仓库；可在设置中启用自动提交和配置远端同步。

## 开发与验证

```bash
# 前端类型检查与生产构建
cd frontend && npm run build

# 后端测试
cd backend && uv run pytest

# 端到端验证（macOS / Linux）
bash scripts/e2e.sh
```

端到端脚本使用内置 mock LLM，在临时目录中验证「导入笔记 → 编译 → 变更 → 问答 → 体检」完整流程，无需外部模型服务。

## 项目结构

```text
backend/     FastAPI 服务、领域逻辑与测试
frontend/    React Web 应用
scripts/     启动、端到端验证与 mock LLM 脚本
design/      设计 token、页面原型与出图脚本
docs/        中文产品文档
```
