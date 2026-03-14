$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

. "$repoRoot\\scripts\\load-env.ps1" -EnvFile ".env"

$depsDir = Join-Path $repoRoot ".deps-backend-v2"
if (-not (Test-Path $depsDir)) {
  New-Item -ItemType Directory -Force $depsDir | Out-Null
}

if (-not (Test-Path (Join-Path $depsDir "fastapi"))) {
  python -m pip install --upgrade --target $depsDir -r requirements.txt
}

$aiDepsDir = Join-Path $repoRoot ".deps-ai"
if (-not (Test-Path $aiDepsDir)) {
  New-Item -ItemType Directory -Force $aiDepsDir | Out-Null
}

$scrapeDepsDir = Join-Path $repoRoot ".deps-scrape"
if (-not (Test-Path $scrapeDepsDir)) {
  New-Item -ItemType Directory -Force $scrapeDepsDir | Out-Null
}

$scrapeMode = ($env:TRUSTAGENT_SCRAPE_MODE)
if (-not $scrapeMode) { $scrapeMode = "auto" }
$scrapeMode = $scrapeMode.ToLowerInvariant().Trim()
if ($scrapeMode -eq "selenium") {
  if (-not (Test-Path (Join-Path $scrapeDepsDir "selenium"))) {
    $allowInstall = ($env:TRUSTAGENT_SELENIUM_INSTALL)
    if (-not $allowInstall) { $allowInstall = "0" }
    $allowInstall = $allowInstall.ToLowerInvariant().Trim()

    if ($allowInstall -in @("1", "true", "yes", "on")) {
      try {
        python -m pip install --upgrade --target $scrapeDepsDir -r requirements-scrape.txt
      } catch {
        Write-Warning "Selenium dependency install failed. Falling back to TRUSTAGENT_SCRAPE_MODE=auto."
        $env:TRUSTAGENT_SCRAPE_MODE = "auto"
      }
    } else {
      Write-Warning "Selenium mode requested but selenium deps are not installed in $scrapeDepsDir. Set TRUSTAGENT_SELENIUM_INSTALL=1 once to auto-install, or install via 'python -m pip install --target $scrapeDepsDir -r requirements-scrape.txt'. Falling back to TRUSTAGENT_SCRAPE_MODE=auto."
      $env:TRUSTAGENT_SCRAPE_MODE = "auto"
    }
  }
}

# Groq is optional; keep it in a separate deps folder to avoid dependency conflicts.
if (-not (Test-Path (Join-Path $aiDepsDir "groq"))) {
  try {
    python -m pip install --target $aiDepsDir -r requirements-ai.txt
  } catch {
    Write-Warning "Groq dependency install failed. Backend will still run using fallback summaries."
  }
}

$env:PYTHONPATH = "$depsDir;$aiDepsDir;$repoRoot"
$env:PYTHONPATH = "$scrapeDepsDir;$env:PYTHONPATH"

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
