# V projekt vključi datoteke končnega modela, ki jih ustvari ST Edge AI.
# Pred kopiranjem preveri izvor modela in kontrolno vsoto uteži; ploščice ne programira.
param(
    [Parameter(Mandatory = $true)]
    [string]$GeneratedOutput,

    [string]$Objcopy
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$modelDirectory = Join-Path $repoRoot 'Projects\X-CUBE-AI\models'
$expectedOrigin = 'hazard5v5_other_yamnet1024_int8_nchw_qdq'
$expectedWeightsSha256 = '0979d852a24f3f2180e10f32f920eddeee166fabc5148841af5678731c33352e'
$generatedOutput = (Resolve-Path -LiteralPath $GeneratedOutput).Path
$required = @(
    'network.c',
    'network.h',
    'stai_network.c',
    'stai_network.h',
    'network_c_info.json',
    'network_generate_report.txt',
    'network_atonbuf.xSPI2.raw'
)

foreach ($name in $required) {
    $path = Join-Path $generatedOutput $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing generated model artifact: $path"
    }
}

$networkHeader = Get-Content -LiteralPath (Join-Path $generatedOutput 'network.h') -Raw
if (-not $networkHeader.Contains($expectedOrigin)) {
    throw 'The generated network is not the selected Hazard5 V5 other-class model.'
}

$weightsSource = Join-Path $generatedOutput 'network_atonbuf.xSPI2.raw'
$weightsHash = (Get-FileHash -LiteralPath $weightsSource -Algorithm SHA256).Hash.ToLowerInvariant()
if ($weightsHash -ne $expectedWeightsSha256) {
    throw "Unexpected Hazard5 V5 weight hash: $weightsHash"
}

foreach ($name in @(
    'network.c',
    'network.h',
    'stai_network.c',
    'stai_network.h',
    'network_c_info.json',
    'network_generate_report.txt'
)) {
    Copy-Item -LiteralPath (Join-Path $generatedOutput $name) `
        -Destination (Join-Path $modelDirectory $name) -Force
}
Copy-Item -LiteralPath $weightsSource `
    -Destination (Join-Path $modelDirectory 'aed_weights.bin') -Force

if (-not $Objcopy) {
    $command = Get-Command 'arm-none-eabi-objcopy.exe' -ErrorAction SilentlyContinue
    if ($command) {
        $Objcopy = $command.Source
    } else {
        $command = Get-ChildItem -LiteralPath 'C:\ST\STM32CubeIDE_2.2.0\STM32CubeIDE\plugins' `
            -Filter 'arm-none-eabi-objcopy.exe' -File -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($command) {
            $Objcopy = $command.FullName
        }
    }
}

if (-not $Objcopy -or -not (Test-Path -LiteralPath $Objcopy -PathType Leaf)) {
    throw 'arm-none-eabi-objcopy.exe was not found; pass its path with -Objcopy.'
}

Push-Location $modelDirectory
try {
    & $Objcopy -I binary 'aed_weights.bin' --change-addresses 0x70180000 `
        -O ihex 'aed_weights.hex'
    if ($LASTEXITCODE -ne 0) {
        throw "Weight HEX generation failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

Write-Host 'Installed the seven-class Hazard5 V5 Neural-ART model.'
Write-Host "Weights: $((Get-Item -LiteralPath (Join-Path $modelDirectory 'aed_weights.bin')).Length) bytes"
Write-Host "SHA-256: $weightsHash"
