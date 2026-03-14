$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

. "$repoRoot\\scripts\\load-env.ps1" -EnvFile ".env"

Set-Location "$repoRoot\\frontend-react"

$npmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue)
if (-not $npmCmd) {
  throw "npm.cmd not found. Install Node.js (LTS) and re-run."
}

if (-not (Test-Path "node_modules")) {
  $cacheDir = Join-Path $repoRoot ".npm-cache"
  New-Item -ItemType Directory -Force $cacheDir | Out-Null
  $env:npm_config_cache = $cacheDir
  & $npmCmd.Source install --no-fund --no-audit
}

if (-not $env:VITE_BACKEND_URL) {
  $env:VITE_BACKEND_URL = "http://127.0.0.1:8001"
}

& $npmCmd.Source run dev
