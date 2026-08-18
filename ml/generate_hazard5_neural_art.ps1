param(
    [string]$STEdgeAI = 'C:\ST\STEdgeAI\4.0\Utilities\windows\stedgeai.exe',
    [string]$Model = 'ml\models\hazard5v5_other_yamnet1024_int8_nchw_qdq.onnx',
    [string]$RunName = 'hazard5v5_other',
    [ValidateSet('', 'float32', 'int8', 'uint8')]
    [string]$InputDataType = '',
    [string]$CutInputTensor = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$projectRoot = (Resolve-Path (Join-Path $repoRoot '..')).Path
$workspaceRoot = Join-Path $projectRoot 'ml-workspace'
$model = if ([System.IO.Path]::IsPathRooted($Model)) {
    $Model
} else {
    Join-Path $repoRoot $Model
}
$configRoot = Join-Path $repoRoot 'ml\configs\stedgeai'
$modelHash = (Get-FileHash $model -Algorithm SHA256).Hash.ToLowerInvariant()
$runRoot = Join-Path $workspaceRoot ("stedgeai\{0}\{1}" -f $RunName, $modelHash.Substring(0, 12))

foreach ($required in @(
    $STEdgeAI,
    $model,
    (Join-Path $configRoot 'stm32n6.mpool'),
    (Join-Path $configRoot 'user_neural_art.json')
)) {
    if (-not (Test-Path $required)) {
        throw "Missing Neural-ART generation prerequisite: $required"
    }
}

New-Item -ItemType Directory -Force $runRoot | Out-Null
Copy-Item (Join-Path $configRoot 'stm32n6.mpool') $runRoot -Force
Copy-Item (Join-Path $configRoot 'user_neural_art.json') $runRoot -Force
$generationWorkspace = Join-Path $runRoot 'gen-workspace'
$generationOutput = Join-Path $runRoot 'gen-output'

Push-Location $runRoot
try {
    $arguments = @(
        'generate',
        '-m', $model,
        '--target', 'stm32n6',
        '--st-neural-art', 'default@user_neural_art.json',
        '--workspace', $generationWorkspace,
        '--output', $generationOutput,
        '--with-report',
        '--verbosity', '1'
    )
    if ($InputDataType) {
        $arguments += @('--input-data-type', $InputDataType)
    }
    if ($CutInputTensor) {
        $arguments += @('--cut-input-tensors', $CutInputTensor)
    }
    & $STEdgeAI @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "STEdgeAI Neural-ART generation failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

$cInfo = Get-ChildItem $generationOutput -Filter 'network_c_info.json' -File | Select-Object -First 1
$weights = Get-ChildItem $generationOutput -Filter 'network_atonbuf.*.raw' -File | Select-Object -First 1
if (-not $cInfo -or -not $weights) {
    throw 'Generation completed without the expected C-info or weight artifact.'
}

[pscustomobject]@{
    model_sha256 = $modelHash
    run_root = $runRoot
    generation_output = $generationOutput
    c_info = $cInfo.FullName
    weights = $weights.FullName
    weights_bytes = $weights.Length
    weights_sha256 = (Get-FileHash $weights.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
} | ConvertTo-Json
