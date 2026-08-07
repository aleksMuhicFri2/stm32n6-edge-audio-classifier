param(
    [string]$Port = "COM3",
    [ValidateRange(1, 28)]
    [int]$StartOrder = 1,
    [ValidateRange(1, 28)]
    [int]$EndOrder = 28,
    [switch]$ValidateOnly,
    [switch]$AutoConfirm
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$manifestPath = Join-Path $repoRoot "experiments\pilot2_evaluation\pilot2_manifest.csv"
$captureScript = Join-Path $PSScriptRoot "capture_uart_experiment.ps1"
$attemptId = "P2-A02"

if ($StartOrder -gt $EndOrder) {
    throw "StartOrder must be less than or equal to EndOrder."
}
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Pilot 2 is not frozen. Complete the review and run ml/finalize_pilot2_manifest.py."
}
if ($Port -notin [System.IO.Ports.SerialPort]::GetPortNames()) {
    throw "Serial port $Port is not currently available."
}

$allTrials = @(Import-Csv -LiteralPath $manifestPath | Sort-Object { [int]$_.trial_order })
if ($allTrials.Count -ne 28) {
    throw "Expected 28 frozen targeted Pilot 2 trials; found $($allTrials.Count)."
}
if (@($allTrials | Where-Object { [int]$_.volume_percent -ne 75 }).Count -ne 0) {
    throw "Pilot 2 replacement manifest must use Windows volume 75 percent."
}
$gunshotHigh = @($allTrials | Where-Object {
    $_.expected_class -eq "gunshot_gunfire" -and [double]$_.derived_gain_db -eq 5.0
})
$gunshotLow = @($allTrials | Where-Object {
    $_.expected_class -eq "gunshot_gunfire" -and [double]$_.derived_gain_db -eq -1.0
})
if ($gunshotHigh.Count -ne 4 -or $gunshotLow.Count -ne 4) {
    throw "Pilot 2 replacement manifest must contain four +5 dB and four -1 dB gunshot trials."
}
$trials = @($allTrials | Where-Object {
    [int]$_.trial_order -ge $StartOrder -and [int]$_.trial_order -le $EndOrder
})

foreach ($trial in $trials) {
    $audioPath = (Resolve-Path -LiteralPath (Join-Path $repoRoot ($trial.stimulus_path -replace "/", "\"))).Path
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $audioPath).Hash.ToLowerInvariant()
    if ($actualHash -ne $trial.sha256.ToLowerInvariant()) {
        throw "Stimulus hash mismatch for $($trial.trial_id): $audioPath"
    }
}

if ($ValidateOnly) {
    Write-Host "Validated $($trials.Count) frozen Pilot 2 stimuli, hashes, and serial port $Port."
    Write-Host "No audio was played."
    return
}

Write-Host "STM32N6 targeted clean-stimulus development verification: $($trials.Count) trials."
Write-Host "Attempt: $attemptId (P2-A01 at 50 percent is retained but excluded)."
Write-Host "Before continuing:"
Write-Host "  1. Put the speaker 30 cm from the board microphone."
Write-Host "  2. Set Windows playback volume to 75 percent."
Write-Host "  3. Keep the room quiet and do not move the board or speaker."
Write-Host "  4. Confirm the unchanged firmware is running and press NRST once."
Write-Host "  5. If external interference occurs, stop the run and report it."
$captureSeconds = ($trials | Measure-Object -Property capture_duration_s -Sum).Sum
Write-Host "The selected run takes approximately $([math]::Ceiling($captureSeconds / 60)) minutes plus brief file-loading time."
if (-not $AutoConfirm) {
    $confirmation = Read-Host "Type START to begin"
    if ($confirmation -ne "START") {
        throw "Pilot 2 cancelled before data capture."
    }
}

foreach ($trial in $trials) {
    $order = [int]$trial.trial_order
    $audioPath = (Resolve-Path -LiteralPath (Join-Path $repoRoot ($trial.stimulus_path -replace "/", "\"))).Path
    $source = "$($trial.source_dataset) $($trial.source_partition) normalized development playback"
    Write-Host ""
    Write-Host "[$order/28] $($trial.trial_id) | $($trial.loudness_stratum)"

    & $captureScript `
        -Port $Port `
        -BaudRate 14400 `
        -DurationSeconds ([int]$trial.capture_duration_s) `
        -Stimulus "$($trial.trial_id) | $($trial.review_id) | $($trial.stimulus_file)" `
        -ExpectedClass $trial.expected_class `
        -QualityLevel controlled `
        -TestType $trial.test_type `
        -Source $source `
        -DistanceCm ([int]$trial.distance_cm) `
        -VolumePercent ([int]$trial.volume_percent) `
        -StimulusHash $trial.sha256 `
        -Notes "Targeted Pilot 2 attempt $attemptId; order $order; true category $($trial.true_category); semantic variant $($trial.variant); loudness stratum $($trial.loudness_stratum); derived gain $($trial.derived_gain_db) dB; gain processing $($trial.gain_processing); limited samples $($trial.limited_samples); final-order seed 210." `
        -PlaybackFile $audioPath `
        -PlaybackDelaySeconds 3 `
        -FirmwareCommit "9a614d2" `
        -ModelName "YAMNet-256 Hazard-5 + Speech int8" `
        -ModelClasses 6
}

Write-Host ""
Write-Host "Pilot 2 capture complete. Preserve all raw logs and tell Codex it is done."
