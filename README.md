# AtlasWiki

[简体中文](docs/README.zh-CN.md)

AtlasWiki is a local-first knowledge compiler. It turns web pages, PDFs, and notes into a structured Markdown wiki, then lets you explore that knowledge through cited Q&A, graph navigation, change review, source management, and quality checks.

Your data and API keys stay local by default. Each knowledge base is an independent Markdown and Git repository, making AtlasWiki well suited to research, durable team knowledge, and traceable AI-assisted writing.

## Key capabilities

- Import web pages, PDFs, and Markdown or plain-text notes
- Compile source material into linked, attributed, and organized wiki pages
- Ask questions across pages and receive source citations
- Explore the knowledge graph, search content, and review compilation changes/history
- Manage source material, edit notes, and recompile stale content
- Detect dead links, orphan pages, and other knowledge-base quality issues
- Connect to OpenAI-compatible APIs with cost tracking, job progress, and optional Git sync

## Architecture

| Layer | Technology |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, React Router, D3 |
| Backend | Python 3.12, FastAPI, Uvicorn, Pydantic |
| Storage | Local Markdown vault, YAML front matter, Git |
| Model provider | OpenAI-compatible API |

## Quick start

### Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js 24+ and npm
- Git (recommended for vault version history)

### 1. Install dependencies and build the frontend

```bash
# Backend dependencies
cd backend
uv sync --extra dev

# Frontend build
cd ../frontend
npm install
npm run build
```

### 2. Start the app

```bash
# macOS / Linux
bash scripts/start.sh

# Windows PowerShell
pwsh -File scripts/start.ps1
```

Open `http://127.0.0.1:8765`. If that port is occupied, the app selects the next available port and prints it to the console.

## First-run workflow

1. Open **Settings** and choose an empty local directory as the **Vault path**.
2. Configure an OpenAI-compatible Base URL, model, and API key.
3. Import a web page, PDF, or note from **Ingest**.
4. Compile the material into wiki pages.
5. Ask questions from Home, or continue with Graph, Search, Lint, and Sources.

> The selected vault is managed by the app and will contain directories such as `wiki/`, `raw/`, and `.llmwiki/`. Use a dedicated directory; do not point it at this repository.

## Configuration and data

- App settings live in `.atlaswiki/settings.json` at the repository root and are excluded from Git.
- Set `ATLASWIKI_CONFIG_DIR` to override the configuration location for containers, CI, testing, or isolated runs. Existing system-level LLM Wiki settings are read only when no project-local settings exist; the next save writes to `.atlaswiki/`.
- API keys are kept outside the repository and should never be committed.
- A vault is an independent Git repository. Automatic commits and a remote can be configured in Settings.

## Development and verification

```bash
# Type-check and production-build the frontend
cd frontend && npm run build

# Run backend tests
cd backend && uv run pytest

# End-to-end check (macOS / Linux)
bash scripts/e2e.sh
```

The end-to-end script uses the built-in mock LLM in a temporary directory to validate the full flow: note ingestion, compilation, changes, Q&A, and linting—without an external model service.

## Repository layout

```text
backend/     FastAPI service, domain logic, and tests
frontend/    React web application
scripts/     Startup, E2E, and mock-LLM scripts
design/      Design tokens, page prototypes, and rendering scripts
docs/        Chinese product documentation
```
