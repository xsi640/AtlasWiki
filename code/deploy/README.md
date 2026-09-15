# LLM Wiki 部署说明

## 环境要求

| 工具 | 最低版本 | 说明 |
|---|---|---|
| Python | 3.12.x | 锁定 3.12，不用 3.13+ |
| uv | 0.11+ | 依赖管理 |
| Node.js | 24.x | 仅构建前端需要 |
| npm | 11.x | 同上 |
| git | 2.30+ | vault 自动 commit |

## 首次准备

```bash
# 1. 后端依赖
cd code/backend
uv sync --extra dev

# 2. 前端构建
cd ../frontend
npm install
npm run build
```

## 日常启动

### macOS / Linux
```bash
bash code/scripts/start.sh
```

### Windows PowerShell
```powershell
pwsh -File code/scripts/start.ps1
```

脚本会：
1. 检查 `code/frontend/dist/index.html` 是否存在（缺失则提示先构建）
2. 以 `127.0.0.1:8765` 启动 uvicorn
3. 端口被占用时自动顺延并打印实际地址
4. 浏览器打开打印的地址即可使用

## 故障排查

| 症状 | 原因 | 解决 |
|---|---|---|
| `uv: command not found` | uv 未安装 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `npm run build` 失败 | Node 版本过低 | 升级到 Node 24.x |
| 端口 8765 被占用 | 其他进程 | 脚本自动顺延，查看控制台输出的实际端口 |
| vault 目录不存在 | 未配置 | 启动后进入设置页配置 vault 路径 |
| LLM 调用返回 503 | 未配置 API key | 设置页填入 OpenAI 兼容端点 + key |
| PDF 导入失败 | 扫描版无文本层 | 属正常行为，原件已保留，可人工补录 |

## 配置文件

| 文件 | 位置 | 说明 |
|---|---|---|
| 应用设置 | `%APPDATA%/llmwiki/settings.json`（Win）或 `~/Library/Application Support/llmwiki/`（macOS） | vault 路径 / LLM / git |
| 知识库 | `vault_path` 指定的目录 | 独立 git 仓库，markdown 文件 |

设置环境变量 `LLMWIKI_CONFIG_DIR` 可把应用配置指到任意目录（测试与端到端脚本使用，
普通部署不需要）。

## 端到端验证

```bash
bash code/scripts/e2e.sh
```

脚本在临时目录建 vault 与隔离配置，用内置的 mock LLM（`e2e_mock_llm.py`，无外部
网络依赖）跑通「导入笔记 → 编译 → 变更清单 → 问答 → 体检」全链路；失败时打印
服务端日志尾部并以非 0 退出；可重复执行，不残留状态。

## 数据安全

- API key 不进版本库（存放在仓库外）
- vault 是独立 git 仓库，自动 commit
- 升级不需要数据迁移，状态文件缺失时自动重建
