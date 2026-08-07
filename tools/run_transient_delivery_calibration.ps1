param(
    [string]$Port = "COM3",
    [switch]$ValidateOnly,
    [switch]$AutoConfirm
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$calibrationDir = Join-Path $repoRoot "experiments\calibration\transient_delivery_001"
$manifestPath = Join-Path $calibrationDir "manifest.csv"
$manifestInfoPath = Join-Path $calibrationDir "manifest.json"
$responsesPath = Join-Path $calibrationDir "operator_responses.csv"
$captureScript = Join-Path $PSScriptRoot "capture_uart_experiment.ps1"
$runsPath = Join-Path $repoRoot "experiments\runs.csv"
$attemptId = "TD-A01"

foreach ($requiredPath in @($manifestPath, $manifestInfoPath, $responsesPath, $captureScript)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Missing calibration file: $requiredPath"
    }
}
if ($Port -notin [System.IO.Ports.SerialPort]::GetPortNames()) {
    throw "Serial port $Port is not currently available."
}

$manifestInfo = Get-Content -Raw -LiteralPath $manifestInfoPath | ConvertFrom-Json
$manifestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath).Hash.ToLowerInvariant()
if ($manifestHash -ne $manifestInfo.manifest_sha256) {
    throw "Calibration manifest hash mismatch."
}
$trials = @(Import-Csv -LiteralPath $manifestPath | Sort-Object { [int]$_.trial_order })
if ($trials.Count -ne 11) {
    throw "Expected 11 transient-delivery calibration trials; found $($trials.Count)."
}
if (@($trials | Where-Object { [int]$_.volume_percent -ne 75 }).Count -ne 0) {
    throw "All delivery-calibration trials must use Windows volume 75 percent."
}

foreach ($trial in $trials) {
    $audioPath = (Resolve-Path -LiteralPath (Join-Path $repoRoot ($trial.stimulus_path -replace "/", "\"))).Path
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $audioPath).Hash.ToLowerInvariant()
    if ($actualHash -ne $trial.sha256.ToLowerInvariant()) {
        throw "Stimulus hash mismatch for $($trial.trial_id): $audioPath"
    }
}

if ($ValidateOnly) {
    Write-Host "Validated 11 frozen delivery-calibration stimuli, hashes, manifest, and serial port $Port."
    Write-Host "No audio was played and no result was scored."
    return
}

$existingRuns = @(Import-Csv -LiteralPath $runsPath | Where-Object {
    $_.notes -like "*Transient delivery calibration*attempt $attemptId*"
})
$existingResponses = @(Import-Csv -LiteralPath $responsesPath)
if ($existingRuns.Count -gt 0 -or $existingResponses.Count -gt 0) {
    throw "Calibration attempt $attemptId already contains data. Stop and tell Codex instead of mixing attempts."
}

Write-Host "STM32N6 non-scored transient-delivery calibration: 11 clips."
Write-Host "This checks audibility and activity coverage only; it is not an accuracy test."
Write-Host "Before continuing:"
Write-Host "  1. Put the speaker 30 cm from the board microphone."
Write-Host "  2. Set Windows playback volume to 75 percent."
Write-Host "  3. Keep the room quiet and press NRST once."
Write-Host "  4. After each clip, rate only how it sounded to you."
if (-not $AutoConfirm) {
    $confirmation = Read-Host "Type START to begin"
    if ($confirmation -ne "START") {
        throw "Delivery calibration cancelled before capture."
    }
}

$ratingMap = @{
    "Q" = "too_quiet"
    "C" = "comfortable"
    "L" = "too_loud_or_distorted"
}

foreach ($trial in $trials) {
    $order = [int]$trial.trial_order
    $audioPath = (Resolve-Path -LiteralPath (Join-Path $repoRoot ($trial.stimulus_path -replace "/", "\"))).Path
    Write-Host ""
    Write-Host "[$order/11] $($trial.trial_id) | $($trial.calibration_scope) | $($trial.true_category)"

    & $captureScript `
        -Port $Port `
        -BaudRate 14400 `
        -DurationSeconds ([int]$trial.capture_duration_s) `
        -Stimulus "$($trial.trial_id) | $($trial.true_category) | $($trial.stimulus_file)" `
        -ExpectedClass $trial.expected_class `
        -QualityLevel controlled `
        -TestType $trial.test_type `
        -Source "Derived Pilot 2 development stimulus; non-scored delivery calibration" `
        -DistanceCm ([int]$trial.distance_cm) `
        -VolumePercent ([int]$trial.volume_percent) `
        -StimulusHash $trial.sha256 `
        -Notes "Transient delivery calibration $($trial.calibration_id) attempt $attemptId; order $order; scope $($trial.calibration_scope); source trial $($trial.source_pilot2_trial_id); repetitions $($trial.repetitions); target parent gain $($trial.target_parent_gain_db) dB; required active frames $($trial.required_active_frames); classification outcome is not scored." `
        -PlaybackFile $audioPath `
        -PlaybackDelaySeconds 3 `
        -FirmwareCommit "9a614d2" `
        -ModelName "YAMNet-256 Hazard-5 + Speech int8" `
        -ModelClasses 6

    do {
        $ratingKey = (Read-Host "Audibility: Q=too quiet, C=comfortable, L=too loud/distorted").Trim().ToUpperInvariant()
    } while (-not $ratingMap.ContainsKey($ratingKey))
    $operatorNote = Read-Host "Optional short note (press Enter to skip)"
    $latestRun = Import-Csv -LiteralPath $runsPath | Select-Object -Last 1
    if ($latestRun.notes -notlike "*attempt $attemptId*" -or $latestRun.stimulus -notlike "$($trial.trial_id) |*") {
        throw "Could not match the latest capture to $($trial.trial_id)."
    }
    [pscustomobject][ordered]@{
        response_id = "TD-R-{0:D3}" -f $order
        recorded_at = (Get-Date).ToString("o")
        calibration_id = $trial.calibration_id
        attempt_id = $attemptId
        trial_id = $trial.trial_id
        run_id = $latestRun.run_id
        audibility_rating = $ratingMap[$ratingKey]
        operator_note = $operatorNote
        stimulus_sha256 = $trial.sha256
        manifest_sha256 = $manifestHash
    } | Export-Csv -LiteralPath $responsesPath -NoTypeInformation -Append -Encoding utf8
}

Write-Host ""
Write-Host "Delivery calibration complete. All responses were saved after each clip."
Write-Host "Tell Codex it is done; do not interpret the board predictions as accuracy."
