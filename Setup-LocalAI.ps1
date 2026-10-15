param([string]$PythonExe = 'python', [switch]$PlanOnly)
$ErrorActionPreference = 'Stop'
$installRoot = 'C:\AI\LightroomLocalDevelop'
$sourceRoot = $PSScriptRoot
if ($PlanOnly) {
    Write-Output "Install target: $installRoot"
    Write-Output 'Copies plugin, scripts, YuNet model, requirements and documents; creates .venv and installs requirements.'
    Write-Output 'Does not install/start Ollama, pull Qwen, operate Lightroom, or change photos/catalogs.'
    exit 0
}
$version = & $PythonExe -c 'import sys; print(sys.version_info.major,sys.version_info.minor,sep=chr(46)); print(64 if sys.maxsize > 2**32 else 32)'
if ($LASTEXITCODE -ne 0 -or $version[0] -ne '3.14' -or $version[1] -ne '64') {
    throw 'Use 64-bit Python 3.14. Pass -PythonExe with its full python.exe path if needed.'
}
New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
if ([IO.Path]::GetFullPath($sourceRoot).TrimEnd('\') -ne [IO.Path]::GetFullPath($installRoot).TrimEnd('\')) {
    foreach ($entry in @('LightroomLocalDevelop.lrplugin','scripts','models','docs','skills',
                          'requirements.txt','requirements-dev.txt','README.md','LICENSE','THIRD_PARTY_NOTICES.md')) {
        Copy-Item -LiteralPath (Join-Path $sourceRoot $entry) -Destination $installRoot -Recurse -Force
    }
    Copy-Item -LiteralPath $PSCommandPath -Destination $installRoot -Force
}
$runtimePython = Join-Path $installRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $runtimePython)) {
    & $PythonExe -m venv (Join-Path $installRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
$runtimeVersion = & $runtimePython -c 'import sys; print(sys.version_info.major,sys.version_info.minor,sep=chr(46))'
if ($runtimeVersion -ne '3.14') { throw 'Existing .venv uses a different Python. Keep it and inspect before updating.' }
& $runtimePython -m pip install --index-url https://pypi.org/simple -r (Join-Path $installRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency install failed. No Lightroom settings were changed.' }
& $runtimePython -c 'import PIL,cv2,numpy; print(PIL.__version__,cv2.__version__,numpy.__version__)'
if ($LASTEXITCODE -ne 0) { throw 'Dependency import check failed.' }
New-Item -ItemType Directory -Force -Path 'C:\AI\LightroomJobs','C:\AI\Models\Ollama' | Out-Null
Write-Output 'Ready: C:\AI\LightroomLocalDevelop\LightroomLocalDevelop.lrplugin'
Write-Output 'Next: install/pull Ollama + Qwen as documented, then add the plugin in Lightroom.'
