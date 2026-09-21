$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repositoryRoot

$verificationEnvironment = Join-Path $repositoryRoot ".venv-windows-check"
if (Test-Path $verificationEnvironment) {
    throw "Verification environment already exists: $verificationEnvironment"
}

py -3.12 -m venv $verificationEnvironment
$python = Join-Path $verificationEnvironment "Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -r requirements.txt
& $python -m pytest -q
& $python -m compileall database services finsight_app scripts

$verificationDatabase = Join-Path $env:TEMP "finsight-windows-verification-$PID.db"
if (Test-Path $verificationDatabase) {
    throw "Temporary verification database already exists: $verificationDatabase"
}
$env:FINSIGHT_DATABASE_PATH = $verificationDatabase
& $python scripts\seed_demo.py --database $verificationDatabase

$streamlit = Start-Process -FilePath $python -ArgumentList @(
    "-m", "streamlit", "run", "finsight_app\app.py",
    "--server.headless=true", "--server.port=8765"
) -PassThru
try {
    $healthy = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        try {
            $response = Invoke-WebRequest -UseBasicParsing `
                -Uri "http://127.0.0.1:8765/_stcore/health" -TimeoutSec 2
            if ($response.StatusCode -eq 200 -and $response.Content -match "ok") {
                $healthy = $true
                break
            }
        } catch {
            # The server may still be starting; retry within the bounded loop.
        }
    }
    if (-not $healthy) {
        throw "Streamlit health check did not become ready."
    }
    Write-Host "Windows verification passed. Complete the README click-through manually."
} finally {
    Stop-Process -Id $streamlit.Id -ErrorAction SilentlyContinue
}
