param([switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$previous = Get-Location
try {
  Set-Location $projectRoot
  if ($env:ATMOTRUST_PYTHON) {
    $pythonCommand = $env:ATMOTRUST_PYTHON
    $pythonArgs = @()
  } elseif (Test-Path (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')) {
    $pythonCommand = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    $pythonArgs = @()
  } elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCommand = 'python'
    $pythonArgs = @()
  } elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCommand = 'py'
    $pythonArgs = @('-3')
  } else {
    throw 'Python 3.11+ is required. Install Python or set ATMOTRUST_PYTHON to its executable.'
  }
  if (-not $SkipInstall) {
    & $pythonCommand @pythonArgs -m pip install -r backend/requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    if (-not (Test-Path frontend/node_modules)) {
      Push-Location frontend
      try { npm ci; if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' } } finally { Pop-Location }
    }
    if (-not (Test-Path frontend/dist/index.html)) {
      Push-Location frontend
      try { npm run build; if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' } } finally { Pop-Location }
    }
  }
  & $pythonCommand @pythonArgs scripts/seed_accounts.py
  if ($LASTEXITCODE -ne 0) { throw 'Account setup failed.' }
  Write-Host 'AtmoTrust running at http://127.0.0.1:8000'
  & $pythonCommand @pythonArgs -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
} finally {
  Set-Location $previous
}
