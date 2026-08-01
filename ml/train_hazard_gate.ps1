param(
    [switch]$SmokeTest,
    [switch]$FineTune,
    [switch]$SpeechHeavy
)

$ErrorActionPreference = 'Stop'
$longRepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$projectRoot = (Resolve-Path (Join-Path $longRepoRoot '..')).Path
$shortDrive = 'T:'
if ($FineTune -and $SpeechHeavy) {
    throw 'FineTune and SpeechHeavy are separate controlled experiments.'
}
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
    $runName = if ($FineTune) {
        'hazard_gate_yamnet256_finetuned'
    } elseif ($SpeechHeavy) {
        'hazard_gate_speechheavy_yamnet256'
    } else {
        'hazard_gate_yamnet256'
    }
    $mlflowName = if ($FineTune) {
        'mlruns-hazard-gate-finetuned-short'
    } elseif ($SpeechHeavy) {
        'mlruns-hazard-gate-speechheavy-short'
    } else {
        'mlruns-hazard-gate-short'
    }
    $datasetName = if ($SpeechHeavy) { 'hazard_gate_speechheavy' } else { 'hazard_gate' }
    $runRoot = Join-Path $workspaceRoot "training-runs\$runName"
    $mlflowRoot = Join-Path $workspaceRoot "training-runs\$mlflowName"
    foreach ($requiredPath in @(
        $python,
        (Join-Path $serviceRoot 'stm32ai_main.py'),
        (Join-Path $workspaceRoot "datasets\$datasetName\audio"),
        (Join-Path $workspaceRoot "datasets\$datasetName\meta\hazard_gate_train.csv")
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
    if ($SpeechHeavy) {
        $datasetRel = "../../datasets/$datasetName"
        $arguments += "dataset.training_audio_path=$datasetRel/audio"
        $arguments += "dataset.training_csv_path=$datasetRel/meta/hazard_gate_train.csv"
        $arguments += "dataset.validation_audio_path=$datasetRel/audio"
        $arguments += "dataset.validation_csv_path=$datasetRel/meta/hazard_gate_validation.csv"
        $arguments += "dataset.test_audio_path=$datasetRel/audio"
        $arguments += "dataset.test_csv_path=$datasetRel/meta/hazard_gate_development_test.csv"
        $arguments += "dataset.quantization_audio_path=$datasetRel/audio"
        $arguments += "dataset.quantization_csv_path=$datasetRel/meta/hazard_gate_quantization.csv"
        $arguments += 'general.project_name=stm32n6_hazard_gate_speechheavy_yamnet256_development'
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
