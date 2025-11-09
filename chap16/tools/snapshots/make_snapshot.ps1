# tools/snapshots/make_snapshot.ps1
param(
  [string]$Tag = "v2025-11-01-Stable",
  [string]$Topic = "venfobel-market-gm",
  [string]$Chap = ".",
  [switch]$RetagIfExists,
  [switch]$ZipToResources,
  [switch]$Push
)

# switch 값은 .IsPresent로 확인
$doRetag = $RetagIfExists.IsPresent
$zipToRes = $ZipToResources.IsPresent
$doPush  = $Push.IsPresent
$ErrorActionPreference = "Stop"

# 0) resolve working dir
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot   = (Resolve-Path (Join-Path $ScriptRoot "..\..\")).Path

if ([string]::IsNullOrWhiteSpace($Chap)) { throw "Please provide -Chap (e.g., '.' or 'chap14_8')." }

if (Test-Path $Chap) {
  $chapDir = (Resolve-Path $Chap).Path
} else {
  $chapDir = Join-Path $RepoRoot $Chap
}
if (!(Test-Path $chapDir)) { throw "Not found: $chapDir" }

Set-Location $chapDir
Write-Host "== Snapshot working dir == $chapDir"

# 1) keep list (code/config)
$keep = @(
  "app.py",
  "core", "agent", "agents", "tools", "utils", "content", "prompts",
  "requirements.txt", "pyproject.toml", ".env", ".env.example",
  "README.md", "report_builder.py"
)

# 2) artifacts to include
$artifacts = @(
  "sections\$Topic",
  "chapters\$Topic",
  "outlines\$Topic",
  "research\$Topic",
  "resources\$Topic",
  "state\last_state.pkl",
  "state\last_state.json",
  "logs"
) | ForEach-Object { Join-Path $chapDir $_ }

# 3) freeze requirements
Write-Host "== Freeze requirements =="
python -m pip freeze | Out-File (Join-Path $chapDir "requirements.lock.txt") -Encoding UTF8

# 4) create .env.example (strip secrets)
Write-Host "== Create .env.example =="
$envPath    = Join-Path $chapDir ".env"
$envExample = Join-Path $chapDir ".env.example"
if (Test-Path $envPath) {
  (Get-Content $envPath) |
    ForEach-Object {
      if ($_ -match "KEY|SECRET|TOKEN|PASSWORD") {
        ($_ -split "=",2)[0] + "="
      } else { $_ }
    } | Set-Content -Encoding UTF8 $envExample
}

# 5) git commit & tag
Write-Host "== Git commit & tag =="
git add -A | Out-Null
try {
  git commit -m "chore(snapshot): $Tag - stable research->write; dual-retrieve; findings saved; Executive Summary drafted" | Out-Null
} catch {
  Write-Host "(info) Nothing to commit; continuing..."
}

# check existing tag
$tagExists = ((git tag -l $Tag) | Where-Object { $_ -eq $Tag }).Count -gt 0

if ($tagExists -and $doRetag) {
  Write-Host "Tag '$Tag' already exists - delete and re-tag"
  git tag -d $Tag | Out-Null
  $tagExists = $false
}

if (-not $tagExists) {
  git tag -a $Tag -m "$Tag"
} else {
  Write-Host "(info) Tag '$Tag' kept (use -RetagIfExists to overwrite)."
}

if ($doPush) {
  git push
  git push origin $Tag
} else {
  Write-Host "== Skip git push (Push switch not present) =="
}

# 6) create snapshot zip (robust: temp → move with retries)
$stamp   = Get-Date -Format "yyyyMMdd_HHmmss"
$zipName = "snapshot_${Tag}_${stamp}.zip"

if ($zipToRes) {
  $snapDir = Join-Path $chapDir ("resources\" + $Topic + "\snapshots")
} else {
  $snapDir = $chapDir
}
if (!(Test-Path $snapDir)) { New-Item -ItemType Directory -Path $snapDir -Force | Out-Null }
$zipPath = Join-Path $snapDir $zipName

function Test-FileLocked([string]$path) {
  if (-not (Test-Path $path)) { return $false }
  try {
    $fs = [System.IO.File]::Open($path, 'Open', 'ReadWrite', 'None'); $fs.Close(); return $false
  } catch { return $true }
}
function Remove-IfPossible([string]$path) {
  if (Test-Path $path) {
    if (Test-FileLocked $path) { Start-Sleep -Milliseconds 500 }
    try { Remove-Item $path -Force -ErrorAction SilentlyContinue } catch {}
  }
}

# gather include paths
$include = @()
$include += $keep      | ForEach-Object { Join-Path $chapDir $_ } | Where-Object { Test-Path $_ }
$include += $artifacts | Where-Object { Test-Path $_ }

Write-Host "== Create archive (temp) =="
$tmpZip = Join-Path $env:TEMP ("snap_" + [guid]::NewGuid().ToString() + ".zip")
Remove-IfPossible $tmpZip

Compress-Archive -Path $include -DestinationPath $tmpZip -CompressionLevel Optimal -ErrorAction Stop

# move to destination with retries (handle locks)
$moved = $false
for ($i=0; $i -lt 6; $i++) {
  if (-not (Test-FileLocked $zipPath)) {
    Remove-IfPossible $zipPath
    try { Move-Item -Path $tmpZip -Destination $zipPath -Force; $moved=$true; break }
    catch { Start-Sleep -Milliseconds 700 }
  } else {
    Start-Sleep -Milliseconds 700
  }
}
if (-not $moved) {
  Write-Error "Failed to place zip at: $zipPath (locked). Temp zip left at: $tmpZip"
} else {
  Write-Host "Zip created: $zipPath"
}

# 7) preview
Write-Host "== Snapshot content preview =="
Get-ChildItem -Recurse (Join-Path $chapDir "research\$Topic")  -ErrorAction SilentlyContinue | Select-Object FullName | Out-String | Write-Host
Get-ChildItem -Recurse (Join-Path $chapDir "sections\$Topic")  -ErrorAction SilentlyContinue | Select-Object FullName | Out-String | Write-Host
Get-ChildItem -Recurse (Join-Path $chapDir "resources\$Topic") -ErrorAction SilentlyContinue | Select-Object FullName | Out-String | Write-Host

Write-Host ""
Write-Host "== DONE =="
Write-Host ("Tag: {0}" -f $Tag)
Write-Host ("Zip: {0}" -f $zipPath)
