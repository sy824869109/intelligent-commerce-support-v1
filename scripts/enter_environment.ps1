# Dot-source this file in the PyCharm PowerShell terminal. Changes affect this shell only.
$icsProjectRoot = Split-Path $PSScriptRoot -Parent
$icsArtifactRoot = Join-Path $icsProjectRoot '_local_artifacts'
$icsCondaRoot = 'F:\heima\ai\python\day01\Anaconda'
$icsV1Prefix = Join-Path $icsCondaRoot 'envs/intelligent-commerce-support-v1'
$icsPython = Join-Path $icsV1Prefix 'python.exe'
if (-not (Test-Path -LiteralPath (Join-Path $icsV1Prefix 'conda-meta/history'))) {
    throw 'Existing V1 Conda environment missing; no environment will be created'
}
# Apply Conda's official activation output directly. Conda 24.5's optional shell wrapper
# passes empty _CE_* arguments incorrectly in PowerShell 7.6; no global profile is edited.
if ($env:CONDA_PREFIX -ne $icsV1Prefix) {
    $icsCondaActivation = (& (Join-Path $icsCondaRoot 'Scripts/conda.exe') 'shell.powershell' 'activate' $icsV1Prefix) -join "`n"
    if ($LASTEXITCODE -or -not $icsCondaActivation) { throw 'Existing V1 Conda activation failed' }
    . ([scriptblock]::Create($icsCondaActivation))
}
foreach ($icsFolder in @('environment/tmp', 'caches/npm', 'caches/pnpm', 'caches/uv', 'models', 'caches/huggingface', 'caches/torch', 'caches/playwright')) {
    New-Item -ItemType Directory -Force -Path (Join-Path $icsArtifactRoot $icsFolder) | Out-Null
}
$env:TEMP = $env:TMP = $env:TMPDIR = Join-Path $icsArtifactRoot 'environment/tmp'
$env:PIP_CACHE_DIR = Join-Path $icsArtifactRoot 'caches/pip'
$env:UV_CACHE_DIR = Join-Path $icsArtifactRoot 'caches/uv'
$env:npm_config_cache = Join-Path $icsArtifactRoot 'caches/npm'
$env:PNPM_HOME = Join-Path $icsArtifactRoot 'dependencies/pnpm'
$env:HF_HOME = Join-Path $icsArtifactRoot 'caches/huggingface'
$env:TORCH_HOME = Join-Path $icsArtifactRoot 'caches/torch'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $icsArtifactRoot 'caches/playwright'
$env:PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT = '120000'
$env:RUFF_CACHE_DIR = Join-Path $icsArtifactRoot 'caches/ruff'
$env:CONDA_PKGS_DIRS = Join-Path $icsArtifactRoot 'caches/conda'
# Do not create another Conda environment. The user's existing named V1 is authoritative.
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
$env:LANGSMITH_TRACING = 'false'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:DO_NOT_TRACK = '1'
$env:PATH = "$icsV1Prefix;$(Join-Path $icsV1Prefix 'Scripts');$(Join-Path $icsV1Prefix 'Library/bin');$(Join-Path $icsArtifactRoot 'dependencies/node/node-v24.20.0-win-x64');$(Join-Path $icsArtifactRoot 'dependencies/pnpm');$env:PATH"
