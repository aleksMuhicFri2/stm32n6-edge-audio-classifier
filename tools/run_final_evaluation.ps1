param(
    [string]$Port = "COM3",
    [ValidateRange(1, 70)]
    [int]$StartOrder = 1,
    [ValidateRange(1, 70)]
    [int]$EndOrder = 70,
    [switch]$ValidateOnly,
    [switch]$AutoConfirm
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$evaluationDir = Join-Path $repoRoot "experiments\final_evaluation"
$manifestPath = Join-Path $evaluationDir "manifest.csv"
$manifestInfoPath = Join-Path $evaluationDir "manifest.json"
$attemptsPath = Join-Path $evaluationDir "attempts.csv"
$captureScript = Join-Path $PSScriptRoot "capture_uart_experiment.ps1"
$runsPath = Join-Path $repoRoot "experiments\runs.csv"
$evaluationId = "STM32N6-HAZARD6-FINAL-001"
$attemptId = "FE-A01"

if ($StartOrder -gt $EndOrder) {
    throw "StartOrder must be less than or equal to EndOrder."
}
foreach ($requiredPath in @($manifestPath, $manifestInfoPath, $attemptsPath, $captureScript, $runsPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Missing final-evaluation file: $requiredPath"
    }
}
if ($Port -notin [System.IO.Ports.SerialPort]::GetPortNames()) {
    throw "Serial port $Port is not currently available."
}

$manifestInfo = Get-Content -Raw -LiteralPath $manifestInfoPath | ConvertFrom-Json
$manifestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath).Hash.ToLowerInvariant()
if ($manifestHash -ne $manifestInfo.manifest_sha256) {
    throw "Final manifest hash mismatch."
}
$allTrials = @(Import-Csv -LiteralPath $manifestPath | Sort-Object { [int]$_.trial_order })
if ($allTrials.Count -ne 70 -or @($allTrials.trial_id | Select-Object -Unique).Count -ne 70) {
    throw "The frozen final manifest must contain 70 unique trials."
}
$expectedCounts = @{
    dog_bark = 10
    glass_breaking = 10
    gunshot_gunfire = 10
    siren = 10
    speech = 10
    thunderstorm = 10
    out_of_distribution = 10
}
foreach ($className in $expectedCounts.Keys) {
    $count = @($allTrials | Where-Object { $_.expected_class -eq $className }).Count
    if ($count -ne $expectedCounts[$className]) {
        throw "Expected $($expectedCounts[$className]) $className trials; found $count."
    }
}
if (@($allTrials | Where-Object {
    [int]$_.volume_percent -ne 75 -or [int]$_.distance_cm -ne 30 -or
    $_.firmware_commit -ne "9a614d2" -or
    $_.model_name -ne "YAMNet-256 Hazard-5 + Speech int8"
}).Count -ne 0) {
    throw "Frozen final physical or system settings changed."
}

foreach ($trial in $allTrials) {
    $audioPath = (Resolve-Path -LiteralPath (Join-Path $repoRoot ($trial.stimulus_path -replace "/", "\"))).Path
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $audioPath).Hash.ToLowerInvariant()
    if ($actualHash -ne $trial.sha256.ToLowerInvariant()) {
        throw "Stimulus hash mismatch for $($trial.trial_id)."
    }
}
if ($ValidateOnly) {
    Write-Host "Validated 70 frozen reserved stimuli, hashes, manifest, physical settings, and serial port $Port."
    Write-Host "No reserved audio was played and no result was captured."
    return
}

$completedAttempts = @(Import-Csv -LiteralPath $attemptsPath)
if (@($completedAttempts | Where-Object { $_.attempt_id -eq $attemptId }).Count -gt 0) {
    throw "Final attempt $attemptId is already registered as complete and cannot be repeated."
}
$existingRuns = @(Import-Csv -LiteralPath $runsPath | Where-Object {
    $_.notes -like "*Reserved final evaluation $evaluationId attempt $attemptId;*"
})
$existingTrialIds = @($existingRuns | ForEach-Object {
    if ($_.stimulus -match "^(FE-\d{3})") { $Matches[1] }
})
if (@($existingTrialIds | Select-Object -Unique).Count -ne $existingTrialIds.Count) {
    throw "Duplicate final trial IDs already exist. Stop and tell Codex."
}
$trials = @($allTrials | Where-Object {
    [int]$_.trial_order -ge $StartOrder -and [int]$_.trial_order -le $EndOrder
})
$overlap = @($trials | Where-Object { $_.trial_id -in $existingTrialIds })
if ($overlap.Count -gt 0) {
    throw "The selected range includes already captured trial $($overlap[0].trial_id). Select only uncaptured trials and preserve existing evidence."
}

Write-Host "STM32N6 one-time reserved final evaluation: $($trials.Count) selected trials."
Write-Host "Before continuing:"
Write-Host "  1. Set Windows playback volume to 75 percent."
Write-Host "  2. Place the speaker 30 cm from the onboard microphone."
Write-Host "  3. Keep the room quiet and do not move the speaker or board."
Write-Host "  4. Press NRST once and do not reset during the attempt."
Write-Host "  5. Stop and report any material interference; never repeat a model failure."
$captureSeconds = ($trials | Measure-Object -Property capture_duration_s -Sum).Sum
Write-Host "Capture time is approximately $([math]::Ceiling($captureSeconds / 60)) minutes plus file-loading time."
if (-not $AutoConfirm) {
    $confirmation = Read-Host "Type START to consume the reserved final test"
    if ($confirmation -ne "START") {
        throw "Final evaluation cancelled before capture."
    }
}

foreach ($trial in $trials) {
    $order = [int]$trial.trial_order
    $audioPath = (Resolve-Path -LiteralPath (Join-Path $repoRoot ($trial.stimulus_path -replace "/", "\"))).Path
    Write-Host ""
    Write-Host "[$order/70] $($trial.trial_id)"
    & $captureScript `
        -Port $Port `
        -BaudRate 14400 `
        -DurationSeconds ([int]$trial.capture_duration_s) `
        -Stimulus "$($trial.trial_id) | reserved final stimulus | $($trial.stimulus_file)" `
        -ExpectedClass $trial.expected_class `
        -QualityLevel controlled `
        -TestType $trial.test_type `
        -Source "$($trial.source_dataset) $($trial.source_partition) frozen reserved playback" `
        -DistanceCm ([int]$trial.distance_cm) `
        -VolumePercent ([int]$trial.volume_percent) `
        -StimulusHash $trial.sha256 `
        -Notes "Reserved final evaluation $evaluationId attempt $attemptId; order $order; true category $($trial.true_category); source $($trial.source_dataset) $($trial.source_partition) $($trial.source_id); delivery reference $($trial.class_delivery_gain_reference_db) dB; applied delivery gain $($trial.class_delivery_gain_db) dB; repetitions $($trial.repetitions); manifest $manifestHash." `
        -PlaybackFile $audioPath `
        -PlaybackDelaySeconds ([int]$trial.playback_delay_s) `
        -FirmwareCommit "9a614d2" `
        -ModelName "YAMNet-256 Hazard-5 + Speech int8" `
        -ModelClasses 6
}

$allFinalRuns = @(Import-Csv -LiteralPath $runsPath | Where-Object {
    $_.notes -like "*Reserved final evaluation $evaluationId attempt $attemptId;*"
} | Sort-Object recorded_at)
$allFinalTrialIds = @($allFinalRuns | ForEach-Object {
    if ($_.stimulus -match "^(FE-\d{3})") { $Matches[1] }
})
if ($allFinalRuns.Count -eq 70 -and @($allFinalTrialIds | Select-Object -Unique).Count -eq 70) {
    $operatorNote = if ($AutoConfirm) {
        ""
    } else {
        Read-Host "Optional overall room/playback observation (press Enter to skip)"
    }
    [pscustomobject][ordered]@{
        attempt_id = $attemptId
        status = "completed"
        started_at = $allFinalRuns[0].recorded_at
        completed_at = (Get-Date).ToString("o")
        first_run_id = $allFinalRuns[0].run_id
        last_run_id = $allFinalRuns[-1].run_id
        captured_trials = 70
        volume_percent = 75
        distance_cm = 30
        manifest_sha256 = $manifestHash
        operator_note = $operatorNote
    } | Export-Csv -LiteralPath $attemptsPath -NoTypeInformation -Append -Encoding utf8
    Write-Host ""
    Write-Host "All 70 reserved final trials are complete. Tell Codex it is done."
} else {
    Write-Host ""
    Write-Host "Captured $($allFinalRuns.Count)/70 final trials. Preserve the data and continue only with the uncaptured range."
}
