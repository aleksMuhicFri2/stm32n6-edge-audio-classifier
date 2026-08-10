param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Refined', 'Event', 'PatchBalanced', 'PatchBalancedV2', 'PatchBalancedV3')]
    [string]$Variant,
    [switch]$SmokeTest
)

$ErrorActionPreference = 'Stop'
$longRepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$projectRoot = (Resolve-Path (Join-Path $longRepoRoot '..')).Path
$shortDrive = 'T:'
if (Test-Path "$shortDrive\") {
    throw "Temporary training drive $shortDrive is already in use."
}

$datasetName = switch ($Variant) {
    'Event' { 'hazard5v4_shatter_event' }
    'PatchBalanced' { 'hazard5v4_patch_balanced' }
    'PatchBalancedV2' { 'hazard5v4_patch_balanced_v2' }
    'PatchBalancedV3' { 'hazard5v4_patch_balanced_v3' }
    default { 'hazard5v4_shatter' }
}
$runName = switch ($Variant) {
    'Event' { 'hazard5v4_shatter_event_yamnet1024' }
    'PatchBalanced' { 'hazard5v4_patch_balanced_yamnet1024' }
    'PatchBalancedV2' { 'hazard5v4_patch_balanced_v2_yamnet1024' }
    'PatchBalancedV3' { 'hazard5v4_patch_balanced_v3_yamnet1024' }
    default { 'hazard5v4_shatter_yamnet1024' }
}
$reviewSummary = if ($Variant -eq 'PatchBalanced') {
    Join-Path $longRepoRoot 'experiments\patch_balanced_augmentation_review\transient_event_review_summary.json'
}
elseif ($Variant -eq 'PatchBalancedV2') {
    Join-Path $longRepoRoot 'experiments\patch_balanced_augmentation_review_v2\combined_transient_review_summary.json'
}
elseif ($Variant -eq 'PatchBalancedV3') {
    Join-Path $longRepoRoot 'experiments\patch_balanced_augmentation_review_v3\combined_transient_review_summary.json'
}
else {
    Join-Path $longRepoRoot 'experiments\shatter_event_review\combined_transient_review_summary.json'
}
if (-not (Test-Path -LiteralPath $reviewSummary -PathType Leaf)) {
    throw "Combined transient listening-review summary is missing."
}
$review = Get-Content -LiteralPath $reviewSummary -Raw | ConvertFrom-Json
if (-not $review.gate_passed) {
    throw "The predefined combined listening-review gate did not pass. Training is blocked."
}

subst $shortDrive $projectRoot
try {
    $repoRoot = "$shortDrive\stm32n6-edge-audio-classifier"
    $workspaceRoot = "$shortDrive\ml-workspace"
    $serviceRoot = Join-Path $workspaceRoot 'stm32ai-modelzoo-services\audio_event_detection'
    $python = Join-Path $workspaceRoot '.venv\Scripts\python.exe'
    $configRoot = Join-Path $repoRoot 'ml\configs'
    $cacheRoot = Join-Path $workspaceRoot 'cache\matplotlib'
    $runRoot = Join-Path $workspaceRoot "training-runs\$runName"
    $mlflowRoot = Join-Path $workspaceRoot "training-runs\mlruns-$runName-short"
    $pretrainedModel = Join-Path $serviceRoot 'tf\src\models\yamnet\yamnet_1024_f32.h5'
    $datasetRoot = Join-Path $workspaceRoot "datasets\$datasetName"

    foreach ($requiredPath in @(
        $python,
        (Join-Path $serviceRoot 'stm32ai_main.py'),
        $pretrainedModel,
        (Join-Path $datasetRoot 'audio'),
        (Join-Path $datasetRoot 'meta\hazard6_train.csv'),
        (Join-Path $datasetRoot 'meta\hazard6_validation.csv'),
        (Join-Path $datasetRoot 'meta\hazard6_development_test.csv'),
        (Join-Path $datasetRoot 'meta\hazard6_quantization.csv')
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
        '--config-name', 'hazard5v4_shatter_yamnet1024_tqe',
        "general.project_name=stm32n6_$runName",
        "mlflow.uri=$mlflowUri",
        "hydra.run.dir=$hydraRunDir"
    )
    if ($Variant -in @('Event', 'PatchBalanced', 'PatchBalancedV2', 'PatchBalancedV3')) {
        $arguments += "dataset.training_audio_path=../../datasets/$datasetName/audio"
        $arguments += "dataset.training_csv_path=../../datasets/$datasetName/meta/hazard6_train.csv"
        $arguments += "dataset.validation_audio_path=../../datasets/$datasetName/audio"
        $arguments += "dataset.validation_csv_path=../../datasets/$datasetName/meta/hazard6_validation.csv"
        $arguments += "dataset.test_audio_path=../../datasets/$datasetName/audio"
        $arguments += "dataset.test_csv_path=../../datasets/$datasetName/meta/hazard6_development_test.csv"
        $arguments += "dataset.quantization_audio_path=../../datasets/$datasetName/audio"
        $arguments += "dataset.quantization_csv_path=../../datasets/$datasetName/meta/hazard6_quantization.csv"
    }
    if ($SmokeTest) {
        $arguments += 'training.epochs=1'
        $arguments += '+training.dryrun=1'
    }

    Push-Location $serviceRoot
    try {
        & $python @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "ST model-zoo $Variant training failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    subst $shortDrive /D
}
