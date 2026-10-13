$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$venv = Join-Path $root '.venv'
$python = Join-Path $venv 'Scripts\python.exe'
$model = Join-Path $root 'models\qwen2.5-coder-7b-instruct-q4_k_m.gguf'
$llama = Join-Path $root 'runtime\windows\llama-server.exe'
$web = Join-Path $root 'source\scripts\serve_forgemind_chat_web.py'
New-Item -ItemType Directory -Force -Path (Join-Path $root 'logs'),(Join-Path $root 'tmp'),(Join-Path $root 'workspace'),(Join-Path $root 'runstate') | Out-Null
if (Get-NetTCPConnection -LocalPort 8091,8094 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 8091 or 8094 is already in use.' }
if (-not (Test-Path -LiteralPath $python)) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Install Python 3.12 and enable Python Launcher (py).' }
    & py -3.12 -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python 3.12 environment.' }
    & $python -m pip install --upgrade pip
    & $python -m pip install -r (Join-Path $root 'requirements-web.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed; check network and requirements-web.txt.' }
}
foreach ($path in @($model,$llama,$web)) { if (-not (Test-Path -LiteralPath $path)) { throw "Package file missing: $path" } }
$env:TEMP = Join-Path $root 'tmp'; $env:TMP = $env:TEMP
$env:PYTHONDONTWRITEBYTECODE = '1'; $env:PYTHONPYCACHEPREFIX = Join-Path $root 'tmp\pycache'
$env:CODE_WORKSPACE = Join-Path $root 'workspace'; $env:FORGEMIND_ALLOW_ANY_DRIVE = '1'
$env:ENABLE_CODE_WRITE = '1'; $env:ENABLE_CODE_EXECUTION = '0'
$modelArgs = '-m "'+$model+'" --alias forgemind-qwen25-coder-7b --host 127.0.0.1 --port 8091 --ctx-size 4096 --threads 8 --n-gpu-layers 0 --jinja'
$modelProc = Start-Process -FilePath $llama -ArgumentList $modelArgs -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'logs\model.log') -RedirectStandardError (Join-Path $root 'logs\model-error.log') -PassThru
Set-Content -LiteralPath (Join-Path $root 'runstate\model.pid') -Value $modelProc.Id
$ready = $false
for ($i=0; $i -lt 240; $i++) {
    try { Invoke-RestMethod 'http://127.0.0.1:8091/v1/models' -TimeoutSec 2 | Out-Null; $ready=$true; break } catch { Start-Sleep 1 }
}
if (-not $ready) { throw 'Model server did not become ready within 240 seconds. Read logs/model-error.log.' }
$webArgs = '"'+$web+'" --backend-url http://127.0.0.1:8091/v1 --model forgemind-qwen25-coder-7b --host 127.0.0.1 --port 8094'
$webProc = Start-Process -FilePath $python -ArgumentList $webArgs -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'logs\website.log') -RedirectStandardError (Join-Path $root 'logs\website-error.log') -PassThru
Set-Content -LiteralPath (Join-Path $root 'runstate\website.pid') -Value $webProc.Id
$ready = $false
for ($i=0; $i -lt 30; $i++) {
    try { $health=Invoke-RestMethod 'http://127.0.0.1:8094/healthz' -TimeoutSec 2; if($health.status -eq 'ok'){$ready=$true;break} } catch { Start-Sleep 1 }
}
if (-not $ready) { throw 'Website did not become ready. Read logs/website-error.log.' }
if (-not $env:FORGEMIND_LAUNCHER) { Start-Process 'http://127.0.0.1:8094/' }
'ForgeMind is ready: http://127.0.0.1:8094/'
'OpenAI-compatible API: http://127.0.0.1:8091/v1'
