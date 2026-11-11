# orangevideo 安装脚本（Windows PowerShell 5.1+）
#   irm https://raw.githubusercontent.com/lyc4614/orangevideo/main/install.ps1 | iex
#
# 选项：
#   -Dir <path>   装到指定技能根目录（默认 $env:USERPROFILE\.workbuddy\skills）
#   -Project      装到当前目录的 .workbuddy\skills
#   -Claude       装到 $env:USERPROFILE\.claude\skills
#   -Force        目标已存在时覆盖
[CmdletBinding()]
param(
  [string]$Dir,
  [switch]$Project,
  [switch]$Claude,
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
# 不静默的话 Invoke-WebRequest / Expand-Archive 会刷屏几十行进度条
$ProgressPreference = 'SilentlyContinue'

$Repo    = 'lyc4614/orangevideo'
$Name    = 'orangevideo'
$Branch  = 'main'
# github.com/<repo>/archive 在部分网络下会被拦，codeload 更容易通
$ZipUrl  = "https://codeload.github.com/$Repo/zip/refs/heads/$Branch"

if ($Project) { $Root = Join-Path (Get-Location) '.workbuddy\skills' }
elseif ($Claude) { $Root = Join-Path $env:USERPROFILE '.claude\skills' }
elseif ($Dir) { $Root = $Dir }
else { $Root = Join-Path $env:USERPROFILE '.workbuddy\skills' }

$Dest = Join-Path $Root $Name

if ((Test-Path $Dest) -and -not $Force) {
  Write-Host "已经装过：$Dest"
  Write-Host "要覆盖请加 -Force"
  exit 1
}

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("ov-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp -Force | Out-Null

try {
  Write-Host "→ 下载 $Repo@$Branch"
  $zip = Join-Path $tmp 'pkg.zip'
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $ZipUrl -OutFile $zip -UseBasicParsing
  } catch {
    throw "下载失败，检查网络，或改用 git clone 方式安装：$($_.Exception.Message)"
  }

  Write-Host "→ 解压"
  $un = Join-Path $tmp 'x'
  # 不用 Expand-Archive：它在 PS 5.1 里无视 $ProgressPreference，会刷几十行进度条
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  [System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $un)

  # codeload 的 zip 解出来是 orangevideo-main
  $src = Get-ChildItem -Path $un -Directory | Where-Object { $_.Name -like "$Name-*" } | Select-Object -First 1
  if (-not $src) { throw "压缩包里没找到 $Name-* 目录" }
  if (-not (Test-Path (Join-Path $src.FullName 'SKILL.md'))) { throw "压缩包里没有 SKILL.md，仓库结构不对" }

  Write-Host "→ 安装到 $Dest"
  New-Item -ItemType Directory -Path $Root -Force | Out-Null
  if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }
  Move-Item -Path $src.FullName -Destination $Dest

  if (-not (Test-Path (Join-Path $Dest 'SKILL.md'))) { throw "安装后找不到 SKILL.md" }

  $skillName = (Select-String -Path (Join-Path $Dest 'SKILL.md') -Pattern '^name:\s*(.+)$' |
                Select-Object -First 1).Matches.Groups[1].Value.Trim()
  if ($skillName -ne $Name) {
    Write-Host "⚠ SKILL.md 里的 name 是「$skillName」，与目录名 $Name 不一致"
  }

  $n = (Get-ChildItem -Path $Dest -Recurse -File).Count
  Write-Host ""
  Write-Host "✓ 装好了：$Dest" -ForegroundColor Green
  Write-Host "  文件：$n 个（SKILL.md / references 5 篇 / scripts 7 个）"
  Write-Host ""
  Write-Host "下一步："
  Write-Host "  1) 在对话里说「做一条口播视频」即可自动加载"
  Write-Host "  2) 只想跑脚本的话：python `"$Dest\scripts\check_spec.py`" --help"
  Write-Host ""
  Write-Host "可选依赖（只跑部分脚本才需要）："
  Write-Host "  pip install python-docx     # build_cues.py 读 docx"
  Write-Host "  npm i puppeteer-core        # 渲染 / 字幕渲染层体检"
  Write-Host "  ffmpeg                      # 编码、抠图、响度、体检"
}
finally {
  if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
}
