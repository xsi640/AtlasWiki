# LLM Wiki 启动脚本（Windows PowerShell）
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "../..")
$BackendDir = Join-Path $RepoRoot "code/backend"
$FrontendDist = Join-Path $RepoRoot "code/frontend/dist"

if (-not (Test-Path (Join-Path $FrontendDist "index.html"))) {
    Write-Host "⚠️  未找到前端构建产物，请先执行:" -ForegroundColor Yellow
    Write-Host "    cd code/frontend && npm install && npm run build"
    Write-Host "然后重新运行本脚本。"
    exit 1
}

Write-Host "🚀 启动 LLM Wiki..."
Set-Location $BackendDir
uv run python -m llmwiki
