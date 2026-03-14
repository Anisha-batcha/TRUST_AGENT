param(
  [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"

function Set-EnvVarFromLine {
  param([string]$Line)
  $trimmed = $Line.Trim()
  if (-not $trimmed) { return }
  if ($trimmed.StartsWith("#")) { return }
  $idx = $trimmed.IndexOf("=")
  if ($idx -lt 1) { return }

  $name = $trimmed.Substring(0, $idx).Trim()
  $value = $trimmed.Substring($idx + 1).Trim()

  $doubleQuote = '"'
  $singleQuote = "'"
  if (($value.StartsWith($doubleQuote) -and $value.EndsWith($doubleQuote)) -or ($value.StartsWith($singleQuote) -and $value.EndsWith($singleQuote))) {
    $value = $value.Substring(1, $value.Length - 2)
  }

  if ($name) {
    Set-Item -Path "Env:$name" -Value $value
  }
}

if (Test-Path $EnvFile) {
  Get-Content $EnvFile -ErrorAction Stop | ForEach-Object { Set-EnvVarFromLine -Line $_ }
}
