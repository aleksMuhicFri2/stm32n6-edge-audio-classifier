param(
    [switch]$SmokeTest,
    [switch]$FineTune
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
    $runName = if ($FineTune) { 'hazard_gate_yamnet256_finetuned' } else { 'hazard_gate_yamnet256' }
    $mlflowName = if ($FineTune) { 'mlruns-hazard-gate-finetuned-short' } else { 'mlruns-hazard-gate-short' }
    $runRoot = Join-Path $workspaceRoot "training-runs\$runName"
    $mlflowRoot = Join-Path $workspaceRoot "training-runs\$mlflowName"
    foreach ($requiredPath in @(
        $python,
        (Join-Path $serviceRoot 'stm32ai_main.py'),
        (Join-Path $workspaceRoot 'datasets\hazard_gate\audio'),
        (Join-Path $workspaceRoot 'datasets\hazard_gate\meta\hazard_gate_train.csv')
    )) {
        if (-not (Test-Path $requiredPath)) {
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
        '--config-name', 'hazard_gate_yamnet256_tqe',
        "mlflow.uri=$mlflowUri",
        "hydra.run.dir=$hydraRunDir"
    )
    if ($FineTune) {
        $arguments += 'training.fine_tune=true'
        $arguments += 'training.optimizer.Adam.learning_rate=0.0001'
        $arguments += 'general.project_name=stm32n6_hazard_gate_yamnet256_finetuned_development'
    }
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
