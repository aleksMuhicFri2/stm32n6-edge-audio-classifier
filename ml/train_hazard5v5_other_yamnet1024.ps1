param([switch]$SmokeTest)

$ErrorActionPreference = 'Stop'
$longRepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$projectRoot = (Resolve-Path (Join-Path $longRepoRoot '..')).Path
$reviewSummaryPath = Join-Path $longRepoRoot 'experiments\hazard5v5_other_review_v9\summary.json'
$preflightPath = Join-Path $longRepoRoot 'experiments\results\hazard5v5_other_preflight\training_patch_balance.json'
$signalQualityPath = Join-Path $longRepoRoot 'experiments\results\hazard5v5_other_signal_quality_final_v6\summary.json'

if (-not (Test-Path -LiteralPath $reviewSummaryPath -PathType Leaf)) {
    throw 'Other-class listening-review summary is missing. Training is blocked.'
}
$review = Get-Content -LiteralPath $reviewSummaryPath -Raw | ConvertFrom-Json
if (-not $review.gate_passed) {
    throw 'Other-class listening-review gate did not pass. Training is blocked.'
}
if (-not (Test-Path -LiteralPath $signalQualityPath -PathType Leaf)) {
    throw 'Final other-class signal-quality audit is missing. Training is blocked.'
}
$signalQuality = Get-Content -LiteralPath $signalQualityPath -Raw | ConvertFrom-Json
if ($signalQuality.status -ne 'passed' -or [int]$signalQuality.severe_clipping_files -ne 0) {
    throw 'Final other-class signal-quality audit did not pass. Training is blocked.'
}
if (-not (Test-Path -LiteralPath $preflightPath -PathType Leaf)) {
    throw 'Other-class patch-balance audit is missing. Training is blocked.'
}
$preflight = Get-Content -LiteralPath $preflightPath -Raw | ConvertFrom-Json
if ([double]$preflight.maximum_to_minimum_patch_count_ratio -gt 1.5) {
    throw 'Other-class patch balance exceeds the predefined 1.5 ratio.'
}
$other = @($preflight.per_class | Where-Object { $_.class_name -eq 'other' })
if ($other.Count -ne 1 -or [int]$other[0].patches -lt 1550) {
    throw 'The explicit other class is missing or underrepresented.'
}

$shortDrive = 'T:'
if (Test-Path "$shortDrive\") {
    throw "Temporary training drive $shortDrive is already in use."
}

subst $shortDrive $projectRoot
try {
    $repoRoot = "$shortDrive\stm32n6-edge-audio-classifier"
    $workspaceRoot = "$shortDrive\ml-workspace"
    $serviceRoot = Join-Path $workspaceRoot 'stm32ai-modelzoo-services\audio_event_detection'
    $python = Join-Path $workspaceRoot '.venv\Scripts\python.exe'
    $configRoot = Join-Path $repoRoot 'ml\configs'
    $cacheRoot = Join-Path $workspaceRoot 'cache\matplotlib'
    $runRoot = Join-Path $workspaceRoot 'training-runs\hazard5v5_other_yamnet1024'
    $mlflowRoot = Join-Path $workspaceRoot 'training-runs\mlruns-hazard5v5-other-yamnet1024-short'
    $pretrainedModel = Join-Path $serviceRoot 'tf\src\models\yamnet\yamnet_1024_f32.h5'
    $datasetRoot = Join-Path $workspaceRoot 'datasets\hazard5v5_other'

    foreach ($requiredPath in @(
        $python,
        (Join-Path $serviceRoot 'stm32ai_main.py'),
        $pretrainedModel,
        (Join-Path $datasetRoot 'audio'),
        (Join-Path $datasetRoot 'meta\hazard7_train.csv'),
        (Join-Path $datasetRoot 'meta\hazard7_validation.csv'),
        (Join-Path $datasetRoot 'meta\hazard7_development_test.csv'),
        (Join-Path $datasetRoot 'meta\hazard7_quantization.csv')
    )) {
        if (-not (Test-Path -LiteralPath $requiredPath)) {
            throw "Missing training prerequisite: $requiredPath"
        }
    }

    New-Item -ItemType Directory -Force $cacheRoot, $runRoot, $mlflowRoot | Out-Null
    $env:MPLCONFIGDIR = $cacheRoot
    $env:MPLBACKEND = 'Agg'
    $env:TF_CPP_MIN_LOG_LEVEL = '2'
    $env:TF_ENABLE_ONEDNN_OPTS = '0'
    $mlflowUri = [System.Uri]::new(
        $mlflowRoot + [System.IO.Path]::DirectorySeparatorChar
    ).AbsoluteUri
    $hydraRunDir = ($runRoot -replace '\\', '/') + '/${now:%Y_%m_%d_%H_%M_%S}'
    $arguments = @(
        'stm32ai_main.py',
        '--config-path', $configRoot,
        '--config-name', 'hazard5v5_other_yamnet1024_tqe',
        'general.project_name=stm32n6_hazard5v5_other_yamnet1024',
        "mlflow.uri=$mlflowUri",
        "hydra.run.dir=$hydraRunDir"
    )
    if ($SmokeTest) {
        $arguments += 'training.epochs=1'
        $arguments += '+training.dryrun=1'
    }

    Push-Location $serviceRoot
    try {
        & $python @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "ST model-zoo training failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    subst $shortDrive /D
}
