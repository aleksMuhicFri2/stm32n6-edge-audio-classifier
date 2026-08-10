param(
    [string]$Port = "COM3",
    [int]$BaudRate = 14400,
    [ValidateRange(1, 13)]
    [int]$StartOrder = 1,
    [ValidateRange(1, 13)]
    [int]$EndOrder = 13,
    [ValidateRange(0, 100)]
    [int]$VolumePercent = 70,
    [ValidateRange(1, 500)]
    [int]$DistanceCm = 30
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$manifestPath = Join-Path $repoRoot "experiments\v3_thunder_calibration\manifest.csv"
$runsPath = Join-Path $repoRoot "experiments\runs.csv"
$captureScript = Join-Path $PSScriptRoot "capture_uart_experiment.ps1"

if ($StartOrder -gt $EndOrder) {
    throw "StartOrder must be less than or equal to EndOrder."
}
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Calibration manifest is missing. Run ml\prepare_v3_thunder_calibration.py first."
}

$allTrials = @(Import-Csv -LiteralPath $manifestPath | Sort-Object { [int]$_.order })
$trials = @($allTrials | Where-Object {
    [int]$_.order -ge $StartOrder -and [int]$_.order -le $EndOrder
})
$captured = @{}
if (Test-Path -LiteralPath $runsPath) {
    foreach ($row in Import-Csv -LiteralPath $runsPath) {
        if ($row.stimulus -like "V3TC-*") {
            $captured[$row.stimulus] = $row.run_id
        }
    }
}

foreach ($trial in $trials) {
    if ($captured.ContainsKey($trial.calibration_id)) {
        Write-Host "Skipping $($trial.calibration_id); already captured as $($captured[$trial.calibration_id])."
        continue
    }

    $audioPath = [IO.Path]::GetFullPath((Join-Path $repoRoot $trial.stimulus_path))
    if (-not (Test-Path -LiteralPath $audioPath -PathType Leaf)) {
        throw "Missing calibration audio: $audioPath"
    }
    $actualHash = (Get-FileHash -LiteralPath $audioPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $trial.stimulus_sha256) {
        throw "Calibration audio hash mismatch: $audioPath"
    }

    Write-Host "[$($trial.order)/$($allTrials.Count)] $($trial.calibration_id) | $($trial.role) | $($trial.true_category)"
    $notes = "Thunder decision calibration; role=$($trial.role); category=$($trial.true_category); processing=$($trial.processing); gain_db=$($trial.gain_change_db); excluded from final evaluation"
    & $captureScript `
        -Port $Port `
        -BaudRate $BaudRate `
        -DurationSeconds ([int]$trial.capture_duration_seconds) `
        -Stimulus $trial.calibration_id `
        -ExpectedClass $trial.expected_board_class `
        -QualityLevel controlled `
        -TestType $trial.test_type `
        -Source "$($trial.source_dataset):$($trial.source_id)" `
        -DistanceCm $DistanceCm `
        -VolumePercent $VolumePercent `
        -StimulusHash $trial.stimulus_sha256 `
        -Notes $notes `
        -PlaybackFile $audioPath `
        -PlaybackDelaySeconds 3 `
        -FirmwareCommit "working-tree-v3" `
        -ModelName "YAMNet-1024 Hazard-5 + Speech V3" `
        -ModelClasses 6
    if ($LASTEXITCODE -ne 0) {
        throw "Capture failed for $($trial.calibration_id) with exit code $LASTEXITCODE."
    }
}

Write-Host "Selected calibration range is complete."
