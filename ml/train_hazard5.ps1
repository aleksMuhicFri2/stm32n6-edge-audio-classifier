param(
    [switch]$SmokeTest,
    [switch]$V2,
    [switch]$V3,
    [ValidateSet('256', '512', '1024')]
    [string]$Embedding = '256'
)

$ErrorActionPreference = 'Stop'
if ($V2 -and $V3) {
    throw 'V2 and V3 are separate controlled taxonomies.'
}
if ((-not $V3) -and ($Embedding -ne '256')) {
    throw 'Embedding-width comparison is currently defined only for V3.'
}

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
    $datasetName = if ($V3) { 'hazard5v3' } elseif ($V2) { 'hazard5v2' } else { 'hazard5' }
    $configName = if ($V3) { 'hazard5v3_yamnet256_tqe' } elseif ($V2) { 'hazard5v2_yamnet256_tqe' } else { 'hazard5_yamnet256_tqe' }
    $runName = if ($V3) { "hazard5v3_yamnet$Embedding" } elseif ($V2) { 'hazard5v2_yamnet256' } else { 'hazard5_yamnet256' }
    $mlflowName = if ($V3) { "mlruns-hazard5v3-$Embedding-short" } elseif ($V2) { 'mlruns-hazard5v2-short' } else { 'mlruns-hazard5-short' }
    $runRoot = Join-Path $workspaceRoot "training-runs\$runName"
    $mlflowRoot = Join-Path $workspaceRoot "training-runs\$mlflowName"

    foreach ($requiredPath in @(
        $python,
        (Join-Path $serviceRoot 'stm32ai_main.py'),
        (Join-Path $workspaceRoot "datasets\$datasetName\audio"),
        (Join-Path $workspaceRoot "datasets\$datasetName\meta\hazard5_train.csv")
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
        '--config-name', $configName,
        "mlflow.uri=$mlflowUri",
        "hydra.run.dir=$hydraRunDir"
    )
    if ($V3 -and ($Embedding -ne '256')) {
        $arguments += "model.model_name=yamnet_e$Embedding"
        $arguments += "general.project_name=stm32n6_hazard5v3_yamnet${Embedding}_development"
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
