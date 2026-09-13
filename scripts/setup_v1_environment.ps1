# Uses the user's existing named Conda environment; never invokes conda create.
[CmdletBinding()]
param([switch]$IncludeFrontend)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'enter_environment.ps1')
if (-not (Test-Path -LiteralPath (Join-Path $icsV1Prefix 'conda-meta/history'))) {
    throw 'Existing intelligent-commerce-support-v1 Conda environment not found; no new environment created'
}
if ((& $icsPython --version) -ne 'Python 3.12.14') { throw 'V1 Python patch does not match reviewed baseline' }
Push-Location $icsProjectRoot
try {
    & $icsPython -m uv pip install --python $icsPython --require-hashes --find-links _local_artifacts/environment --index https://download.pytorch.org/whl/cpu --default-index https://pypi.org/simple --index-strategy unsafe-best-match -r deploy/dev-environment/v1-requirements.lock
    if ($LASTEXITCODE) { throw 'V1 locked dependency installation failed' }
    & $icsPython -m pip check
    if ($LASTEXITCODE) { throw 'V1 installed dependencies conflict' }
    if ($IncludeFrontend) { & (Join-Path $PSScriptRoot 'setup_frontend_environment.ps1') -Frozen }
} finally { Pop-Location }
