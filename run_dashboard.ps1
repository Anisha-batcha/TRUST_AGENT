$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

. "$repoRoot\\scripts\\load-env.ps1" -EnvFile ".env"

$depsDir = Join-Path $repoRoot ".deps-ui"
if (-not (Test-Path $depsDir)) {
  New-Item -ItemType Directory -Force $depsDir | Out-Null
}

python -m pip install --upgrade --target $depsDir -r requirements-ui.txt

if (-not $env:TRUSTAGENT_API_BASE_URL) {
  $env:TRUSTAGENT_API_BASE_URL = "http://127.0.0.1:8001"
}
$env:PYTHONPATH = "$depsDir;$repoRoot"

python -m streamlit run frontend/dashboard.py
