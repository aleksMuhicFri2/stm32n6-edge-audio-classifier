param(
    [string]$Port = "COM3",
    [switch]$ValidateOnly,
    [switch]$AutoConfirm
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$calibrationDir = Join-Path $repoRoot "experiments\calibration\transient_delivery_002"
$manifestPath = Join-Path $calibrationDir "manifest.csv"
$manifestInfoPath = Join-Path $calibrationDir "manifest.json"
$responsesPath = Join-Path $calibrationDir "operator_responses.csv"
$captureScript = Join-Path $PSScriptRoot "capture_uart_experiment.ps1"
$runsPath = Join-Path $repoRoot "experiments\runs.csv"
$attemptId = "TD-A02"

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
    throw "TD-A02 manifest hash mismatch."
}
$trials = @(Import-Csv -LiteralPath $manifestPath | Sort-Object { [int]$_.trial_order })
if ($trials.Count -ne 5) {
    throw "Expected five focused TD-A02 trials; found $($trials.Count)."
}
foreach ($trial in $trials) {
    $audioPath = (Resolve-Path -LiteralPath (Join-Path $repoRoot ($trial.stimulus_path -replace "/", "\"))).Path
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $audioPath).Hash.ToLowerInvariant()
    if ($actualHash -ne $trial.sha256.ToLowerInvariant()) {
        throw "Stimulus hash mismatch for $($trial.trial_id)."
    }
}
if ($ValidateOnly) {
    Write-Host "Validated five frozen TD-A02 stimuli, hashes, manifest, and serial port $Port."
    Write-Host "No audio was played and no classification result was scored."
    return
}

$existingRuns = @(Import-Csv -LiteralPath $runsPath | Where-Object {
    $_.notes -like "*Focused delivery calibration*attempt $attemptId*"
})
$existingResponses = @(Import-Csv -LiteralPath $responsesPath)
if ($existingRuns.Count -gt 0 -or $existingResponses.Count -gt 0) {
    throw "Attempt $attemptId already contains data. Stop and tell Codex instead of mixing attempts."
}

Write-Host "STM32N6 focused non-scored delivery calibration: five clips."
Write-Host "Set Windows volume to 75 percent and keep the speaker 30 cm away."
Write-Host "Press NRST once, keep the room quiet, and rate only audibility."
if (-not $AutoConfirm) {
    $confirmation = Read-Host "Type START to begin"
    if ($confirmation -ne "START") {
        throw "TD-A02 cancelled before capture."
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
    Write-Host "[$order/5] $($trial.trial_id) | $($trial.true_category) | adjustment $($trial.adjustment_db) dB"
    & $captureScript `
        -Port $Port `
        -BaudRate 14400 `
        -DurationSeconds ([int]$trial.capture_duration_s) `
        -Stimulus "$($trial.trial_id) | $($trial.true_category) | $($trial.stimulus_file)" `
        -ExpectedClass $trial.expected_class `
        -QualityLevel controlled `
        -TestType $trial.test_type `
        -Source "Derived TD-A01 development sequence; focused non-scored delivery calibration" `
        -DistanceCm ([int]$trial.distance_cm) `
        -VolumePercent ([int]$trial.volume_percent) `
        -StimulusHash $trial.sha256 `
        -Notes "Focused delivery calibration $($trial.calibration_id) attempt $attemptId; order $order; source $($trial.source_td_a01_trial_id); level adjustment $($trial.adjustment_db) dB; target parent gain $($trial.target_parent_gain_db) dB; required active frames $($trial.required_active_frames); classification outcome is not scored." `
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
        response_id = "TD2-R-{0:D3}" -f $order
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
Write-Host "TD-A02 complete. Tell Codex it is done; predictions were not scored."
