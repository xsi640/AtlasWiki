# 重新渲染设计图
# 用法：在 code/design 目录下执行  pwsh -File render.ps1
# 依赖：本机安装 Chrome 或 Edge
# 说明：tokens.css 是唯一的设计 token 来源；每个页面一个 HTML，通过 ?theme=light|dark 切主题。

$ErrorActionPreference = "Stop"
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$img  = Join-Path $base "images"
New-Item -ItemType Directory -Force -Path $img | Out-Null

$candidates = @(
  "C:\Program Files\Google\Chrome\Application\chrome.exe",
  "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
  "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
)
$browser = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $browser) { throw "未找到 Chrome 或 Edge，无法渲染。" }

# 页面 -> 输出编号 / 主题。出图视口统一取笔记本基准 1440 × 900（≈1440×900 屏除浏览器边框）
$baseW = 1440
$baseH = 900

# UI-000~006：关键页面；UI-007/008：断点验证；UI-009~015：补齐 UX 定义的其余 7 页
$jobs = @(
  # p000 是长参考表（色彩/字体/组件/断点），单独加高画布以完整呈现
  @{ f="p000-design-system.html"; out="UI-000-design-system"; h=1560; themes=@("light","dark") },
  @{ f="p001-home.html";          out="UI-001-home";          themes=@("light","dark") },
  @{ f="p003-compile.html";       out="UI-002-compile";       themes=@("light") },
  @{ f="p004-changes.html";       out="UI-003-changes";       themes=@("light") },
  @{ f="p005-page.html";          out="UI-004-page";          themes=@("light","dark") },
  @{ f="p006-graph.html";         out="UI-005-graph";         themes=@("light") },
  @{ f="p013-sources.html";       out="UI-006-sources";       themes=@("light") },
  # —— 补齐的 7 页 ——
  @{ f="p002-ingest.html";        out="UI-009-ingest";        themes=@("light") },
  @{ f="p007-zones.html";         out="UI-010-zones";         themes=@("light") },
  @{ f="p008-search.html";        out="UI-011-search";        themes=@("light") },
  @{ f="p009-history.html";       out="UI-012-history";       themes=@("light") },
  @{ f="p010-source.html";        out="UI-013-source";        themes=@("light","dark") },
  @{ f="p011-lint.html";          out="UI-014-lint";          themes=@("light") },
  @{ f="p012-settings.html";      out="UI-015-settings";      themes=@("light","dark") }
)

# 自适应验证：同一页面在小笔记本 / 外接大屏两档各出一版，用于确认 breakpoint 切换正常
$adaptive = @(
  @{ f="p005-page.html"; w=1120; h=860; out="UI-007-adaptive-1120"; themes=@("light") },
  @{ f="p005-page.html"; w=1680; h=960; out="UI-008-adaptive-1680"; themes=@("light") }
)

function Render($f, $w, $h, $out, $t) {
  $src = "file:///" + ((Join-Path $base $f) -replace '\\','/') + "?theme=" + $t
  $dst = Join-Path $img ($out + "-" + $t + ".png")
  & $browser --headless=new --disable-gpu --hide-scrollbars `
    --force-device-scale-factor=1 --virtual-time-budget=3000 `
    --window-size="$w,$h" --screenshot="$dst" "$src" | Out-Null
  if (Test-Path $dst) { Write-Host "OK   $out-$t.png  ($w x $h)" } else { Write-Host "FAIL $out-$t.png" }
}

foreach ($j in $jobs) {
  $h = if ($j.ContainsKey("h")) { $j.h } else { $baseH }
  foreach ($t in $j.themes) { Render $j.f $baseW $h $j.out $t }
}
foreach ($j in $adaptive) { foreach ($t in $j.themes) { Render $j.f $j.w $j.h $j.out $t } }
Write-Host "完成，输出目录：$img"
