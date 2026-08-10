param(
    [switch]$SmokeTest
)

$ErrorActionPreference = 'Stop'

$longRepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$projectRoot = (Resolve-Path (Join-Path $longRepoRoot '..')).Path
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
    $runRoot = Join-Path $workspaceRoot 'training-runs\hazard5v3s_yamnet1024_event_b1'
    $mlflowRoot = Join-Path $workspaceRoot 'training-runs\mlruns-hazard5v3s-yamnet1024-event-b1-short'
    $pretrainedModel = Join-Path $serviceRoot 'tf\src\models\yamnet\yamnet_1024_f32.h5'
    $reviewSummary = Join-Path $longRepoRoot 'experiments\transient_event_review\transient_event_review_summary.json'

    foreach ($requiredPath in @(
        $python,
        (Join-Path $serviceRoot 'stm32ai_main.py'),
        $pretrainedModel,
        (Join-Path $workspaceRoot 'datasets\hazard5v3s_event_b1\audio'),
        (Join-Path $workspaceRoot 'datasets\hazard5v3s_event_b1\meta\hazard6_train.csv'),
        (Join-Path $workspaceRoot 'datasets\hazard5v3s_event_b1\meta\hazard6_validation.csv'),
        (Join-Path $workspaceRoot 'datasets\hazard5v3s_event_b1\meta\hazard6_development_test.csv'),
        (Join-Path $workspaceRoot 'datasets\hazard5v3s_event_b1\meta\hazard6_quantization.csv'),
        $reviewSummary
    )) {
        if (-not (Test-Path $requiredPath)) {
            throw "Missing B1 training prerequisite: $requiredPath"
        }
    }

    $review = Get-Content -LiteralPath $reviewSummary -Raw | ConvertFrom-Json
    if (-not $review.gate_passed) {
        throw "The predefined event-window listening-review gate did not pass. B1 training is blocked."
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
        '--config-name', 'hazard5v3s_yamnet1024_event_b1_tqe',
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
            throw "ST model-zoo B1 training failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    subst $shortDrive /D
}
