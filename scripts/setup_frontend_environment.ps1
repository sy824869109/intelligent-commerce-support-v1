# Downloads are verified before extraction. Does not install globally or modify system PATH.
[CmdletBinding()]
param([switch]$Frozen)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'enter_environment.ps1')
$icsNodeRoot = Join-Path $icsArtifactRoot 'dependencies/node'
$icsArchive = Join-Path $icsArtifactRoot 'environment/node-v24.20.0-win-x64.zip'
$icsNode = Join-Path $icsNodeRoot 'node-v24.20.0-win-x64/node.exe'
$icsChecksums = Invoke-RestMethod 'https://nodejs.org/dist/v24.20.0/SHASUMS256.txt'
$icsMatch = [regex]::Match($icsChecksums, '(?m)^([a-f0-9]{64})\s+node-v24\.20\.0-win-x64\.zip\s*$')
if (-not $icsMatch.Success) { throw 'Official Node archive checksum missing' }
if (-not (Test-Path -LiteralPath $icsArchive)) {
    Invoke-WebRequest 'https://nodejs.org/dist/v24.20.0/node-v24.20.0-win-x64.zip' -OutFile $icsArchive
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $icsArchive).Hash.ToLowerInvariant() -ne $icsMatch.Groups[1].Value) {
    throw 'Node archive checksum mismatch; preserve file for inspection'
}
if (-not (Test-Path -LiteralPath $icsNode)) { Expand-Archive -LiteralPath $icsArchive -DestinationPath $icsNodeRoot }
if ((& $icsNode --version) -ne 'v24.20.0') { throw 'Node version mismatch' }
$icsNpm = Join-Path $icsNodeRoot 'node-v24.20.0-win-x64/node_modules/npm/bin/npm-cli.js'
$icsPnpm = Join-Path $env:PNPM_HOME 'node_modules/pnpm/bin/pnpm.cjs'
if (-not (Test-Path -LiteralPath $icsPnpm)) {
    & $icsNode $icsNpm install --prefix $env:PNPM_HOME --ignore-scripts --no-audit --no-fund --registry https://registry.npmjs.org pnpm@10.34.5
    if ($LASTEXITCODE) { throw 'Project-local pnpm installation failed' }
}
if ((& $icsNode $icsPnpm --version) -ne '10.34.5') { throw 'pnpm version mismatch' }
$icsFrontend = Join-Path $icsProjectRoot 'deploy/dev-environment/frontend'
Push-Location $icsFrontend
try {
    $icsInstallArgs = @('install', '--ignore-scripts', '--store-dir', (Join-Path $icsArtifactRoot 'caches/pnpm'), '--registry', 'https://registry.npmjs.org')
    if ($Frozen) { $icsInstallArgs += '--frozen-lockfile' }
    & $icsNode $icsPnpm @icsInstallArgs
    if ($LASTEXITCODE) { throw 'Frontend dependency installation failed' }
    & $icsNode $icsPnpm exec playwright install chromium
    if ($LASTEXITCODE) { throw 'Project-local Chromium installation failed' }
    & $icsNode $icsPnpm run check
    if ($LASTEXITCODE) { throw 'Frontend environment smoke failed' }
} finally { Pop-Location }
Write-Output 'Frontend environment installed and checked; no business pages created.'
