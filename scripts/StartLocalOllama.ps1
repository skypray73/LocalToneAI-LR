$ErrorActionPreference = 'Stop'
$env:OLLAMA_MODELS = 'C:\AI\Models\Ollama'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_CONTEXT_LENGTH = '8192'
$env:OLLAMA_NUM_PARALLEL = '1'
try {
    $version = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2
    Write-Output "Ollama already running: $($version.version). No service changes made."
    exit 0
} catch {}
$ollamaExe = 'C:\AI\Ollama\ollama.exe'
if (-not (Test-Path -LiteralPath $ollamaExe)) { throw 'Portable Ollama not installed at C:\AI\Ollama' }
Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden
Write-Output 'Started local Ollama in background, model folder C:\AI\Models\Ollama.'
