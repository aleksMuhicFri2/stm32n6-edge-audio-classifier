param(
    [string]$Port = "COM3",
    [ValidateRange(1, 21)]
    [int]$StartOrder = 1,
    [ValidateRange(1, 21)]
    [int]$EndOrder = 21,
    [switch]$ValidateOnly,
    [switch]$AutoConfirm
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$testDir = Join-Path $repoRoot "experiments\v3_acceptance_test"
$manifestPath = Join-Path $testDir "manifest.csv"
$manifestInfoPath = Join-Path $testDir "manifest.json"
$attemptsPath = Join-Path $testDir "attempts.csv"
$captureScript = Join-Path $PSScriptRoot "capture_uart_experiment.ps1"
$runsPath = Join-Path $repoRoot "experiments\runs.csv"
$evaluationId = "STM32N6-HAZARD6-ACCEPTANCE-001"
$attemptId = "AT-A01"
$modelName = "YAMNet-1024 Hazard-5 + Speech V3 int8"
$firmwareCommit = "9c7c7b7401bb7ad298565a4aad34eb3a670b832c"

if ($StartOrder -gt $EndOrder) {
    throw "StartOrder must be less than or equal to EndOrder."
}
foreach ($requiredPath in @($manifestPath, $manifestInfoPath, $attemptsPath, $captureScript, $runsPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Missing acceptance-test file: $requiredPath"
    }
}
if ($Port -notin [System.IO.Ports.SerialPort]::GetPortNames()) {
    throw "Serial port $Port is not currently available."
}

$manifestInfo = Get-Content -Raw -LiteralPath $manifestInfoPath | ConvertFrom-Json
$manifestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath).Hash.ToLowerInvariant()
if ($manifestHash -ne $manifestInfo.manifest_sha256) {
    throw "Acceptance-test manifest hash mismatch."
}
$allTrials = @(Import-Csv -LiteralPath $manifestPath | Sort-Object { [int]$_.trial_order })
if ($allTrials.Count -ne 21 -or @($allTrials.trial_id | Select-Object -Unique).Count -ne 21) {
    throw "The frozen acceptance manifest must contain 21 unique trials."
}

$expectedCounts = @{
    dog_bark = 3
    glass_breaking = 3
    gunshot_gunfire = 3
    siren = 3
    speech = 3
    thunderstorm = 3
    out_of_distribution = 3
}
foreach ($className in $expectedCounts.Keys) {
    $count = @($allTrials | Where-Object { $_.expected_class -eq $className }).Count
    if ($count -ne $expectedCounts[$className]) {
        throw "Expected $($expectedCounts[$className]) $className trials; found $count."
    }
}
foreach ($attenuation in @(0, -6, -12)) {
    $count = @($allTrials | Where-Object { [int]$_.attenuation_db -eq $attenuation }).Count
    $expected = if ($attenuation -eq 0) { 9 } else { 6 }
    if ($count -ne $expected) {
        throw "Expected $expected trials at $attenuation dB; found $count."
    }
}
if (@($allTrials | Where-Object {
    [int]$_.volume_percent -ne 70 -or [int]$_.distance_cm -ne 30 -or
    $_.firmware_commit -ne $firmwareCommit -or $_.model_name -ne $modelName
}).Count -ne 0) {
    throw "Frozen physical or system settings changed."
}

foreach ($trial in $allTrials) {
    $audioPath = (Resolve-Path -LiteralPath (Join-Path $repoRoot ($trial.stimulus_path -replace "/", "\"))).Path
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $audioPath).Hash.ToLowerInvariant()
    if ($actualHash -ne $trial.sha256.ToLowerInvariant()) {
        throw "Stimulus hash mismatch for $($trial.trial_id)."
    }
}
if ($ValidateOnly) {
    Write-Host "Validated 21 frozen stimuli from nine previously approved recordings."
    Write-Host "The clean-shatter source, all hashes, fixed settings, and serial port $Port are valid."
    Write-Host "No audio was played and no result was captured."
    return
}

$completedAttempts = @(Import-Csv -LiteralPath $attemptsPath)
if (@($completedAttempts | Where-Object { $_.attempt_id -eq $attemptId }).Count -gt 0) {
    throw "Acceptance attempt $attemptId is already registered as complete."
}
$existingRuns = @(Import-Csv -LiteralPath $runsPath | Where-Object {
    $_.notes -like "*Acceptance test $evaluationId attempt $attemptId;*"
})
$existingTrialIds = @($existingRuns | ForEach-Object {
    if ($_.stimulus -match "^(AT-\d{3})") { $Matches[1] }
})
if (@($existingTrialIds | Select-Object -Unique).Count -ne $existingTrialIds.Count) {
    throw "Duplicate acceptance trial identifiers already exist. Stop and preserve the evidence."
}
$trials = @($allTrials | Where-Object {
    [int]$_.trial_order -ge $StartOrder -and [int]$_.trial_order -le $EndOrder
})
$overlap = @($trials | Where-Object { $_.trial_id -in $existingTrialIds })
if ($overlap.Count -gt 0) {
    throw "The selected range includes captured trial $($overlap[0].trial_id). Continue only with uncaptured trials."
}

Write-Host "STM32N6 controlled V3 acceptance test: $($trials.Count) selected trials."
Write-Host "This test uses only recordings that were already approved by listening."
Write-Host "Before continuing:"
Write-Host "  1. Set Windows playback volume to 70 percent."
Write-Host "  2. Place the speaker 30 cm from the onboard microphone."
Write-Host "  3. Keep the room quiet and do not move the board or speaker."
Write-Host "  4. Press NRST once and do not reset during the attempt."
Write-Host "  5. Do not repeat a model failure. Report material interference afterward."
$captureSeconds = ($trials | Measure-Object -Property capture_duration_s -Sum).Sum
Write-Host "Capture time is approximately $([math]::Ceiling($captureSeconds / 60)) minutes plus loading time."
if (-not $AutoConfirm) {
    $confirmation = Read-Host "Type START to begin the frozen acceptance test"
    if ($confirmation -ne "START") {
        throw "Acceptance test cancelled before capture."
    }
}

foreach ($trial in $trials) {
    $order = [int]$trial.trial_order
    $audioPath = (Resolve-Path -LiteralPath (Join-Path $repoRoot ($trial.stimulus_path -replace "/", "\"))).Path
    Write-Host ""
    Write-Host "[$order/21] $($trial.trial_id) | approved source $($trial.source_review_id) | $($trial.attenuation_db) dB"
    & $captureScript `
        -Port $Port `
        -BaudRate 14400 `
        -DurationSeconds ([int]$trial.capture_duration_s) `
        -Stimulus "$($trial.trial_id) | approved V3 acceptance stimulus | $($trial.stimulus_file)" `
        -ExpectedClass $trial.expected_class `
        -QualityLevel controlled `
        -TestType $trial.test_type `
        -Source "$($trial.source_dataset) approved source $($trial.source_review_id)" `
        -DistanceCm ([int]$trial.distance_cm) `
        -VolumePercent ([int]$trial.volume_percent) `
        -StimulusHash $trial.sha256 `
        -Notes "Acceptance test $evaluationId attempt $attemptId; order $order; true category $($trial.true_category); approved source $($trial.source_test_id)/$($trial.source_review_id); attenuation $($trial.attenuation_db) dB; manifest $manifestHash; interpretation controlled acceptance not independent generalisation." `
        -PlaybackFile $audioPath `
        -PlaybackDelaySeconds ([int]$trial.playback_delay_s) `
        -FirmwareCommit $firmwareCommit `
        -ModelName $modelName `
        -ModelClasses 6
}

$allAcceptanceRuns = @(Import-Csv -LiteralPath $runsPath | Where-Object {
    $_.notes -like "*Acceptance test $evaluationId attempt $attemptId;*"
} | Sort-Object recorded_at)
$allAcceptanceTrialIds = @($allAcceptanceRuns | ForEach-Object {
    if ($_.stimulus -match "^(AT-\d{3})") { $Matches[1] }
})
if ($allAcceptanceRuns.Count -eq 21 -and @($allAcceptanceTrialIds | Select-Object -Unique).Count -eq 21) {
    $operatorNote = if ($AutoConfirm) { "" } else {
        Read-Host "Optional room or playback observation (press Enter to skip)"
    }
    [pscustomobject][ordered]@{
        attempt_id = $attemptId
        status = "completed"
        started_at = $allAcceptanceRuns[0].recorded_at
        completed_at = (Get-Date).ToString("o")
        first_run_id = $allAcceptanceRuns[0].run_id
        last_run_id = $allAcceptanceRuns[-1].run_id
        captured_trials = 21
        volume_percent = 70
        distance_cm = 30
        manifest_sha256 = $manifestHash
        operator_note = $operatorNote
    } | Export-Csv -LiteralPath $attemptsPath -NoTypeInformation -Append -Encoding utf8
    Write-Host ""
    Write-Host "All 21 acceptance trials are complete. Tell Codex it is done."
} else {
    Write-Host ""
    Write-Host "Captured $($allAcceptanceRuns.Count)/21 trials. Preserve them and continue with the first uncaptured range."
}
