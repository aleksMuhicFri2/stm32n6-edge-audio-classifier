param(
    [string]$Port = "COM3",
    [ValidateRange(1, 35)]
    [int]$StartOrder = 1,
    [ValidateRange(1, 35)]
    [int]$EndOrder = 35,
    [switch]$ValidateOnly,
    [switch]$AutoConfirm
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$manifestPath = Join-Path $repoRoot "experiments\pilot_evaluation\pilot_manifest.csv"
$captureScript = Join-Path $PSScriptRoot "capture_uart_experiment.ps1"

if ($StartOrder -gt $EndOrder) {
    throw "StartOrder must be less than or equal to EndOrder."
}
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Pilot manifest is missing. Run tools/prepare_pilot_manifest.mjs first."
}
if ($Port -notin [System.IO.Ports.SerialPort]::GetPortNames()) {
    throw "Serial port $Port is not currently available."
}

$trials = @(Import-Csv -LiteralPath $manifestPath | Where-Object {
    [int]$_.trial_order -ge $StartOrder -and [int]$_.trial_order -le $EndOrder
})
if ($trials.Count -eq 0) {
    throw "No trials selected."
}

foreach ($trial in $trials) {
    $audioPath = (Resolve-Path -LiteralPath (Join-Path $repoRoot ($trial.stimulus_path -replace "/", "\"))).Path
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $audioPath).Hash.ToLowerInvariant()
    if ($actualHash -ne $trial.sha256.ToLowerInvariant()) {
        throw "Stimulus hash mismatch for $($trial.trial_id): $audioPath"
    }
}

if ($ValidateOnly) {
    Write-Host "Validated $($trials.Count) pilot stimuli, hashes, and serial port $Port. No audio was played."
    return
}

Write-Host "STM32N6 controlled pilot: $($trials.Count) trials ($StartOrder through $EndOrder)."
Write-Host "Before continuing:"
Write-Host "  1. Put the speaker 30 cm from the board microphone."
Write-Host "  2. Set Windows playback volume to 50 percent."
Write-Host "  3. Keep the room quiet and do not move the board or speaker."
Write-Host "  4. Confirm that the board is monitoring and press TAMP once."
Write-Host "The run takes about $([math]::Ceiling($trials.Count * 20 / 60)) minutes and plays automatically."
if (-not $AutoConfirm) {
    $confirmation = Read-Host "Type START to begin"
    if ($confirmation -ne "START") {
        throw "Pilot cancelled before data capture."
    }
}

foreach ($trial in $trials) {
    $order = [int]$trial.trial_order
    $audioPath = (Resolve-Path -LiteralPath (Join-Path $repoRoot ($trial.stimulus_path -replace "/", "\"))).Path
    $source = "$($trial.source_dataset) $($trial.source_partition) via Windows speaker"
    Write-Host ""
    Write-Host "[$order/35] $($trial.trial_id)"

    & $captureScript `
        -Port $Port `
        -BaudRate 14400 `
        -DurationSeconds ([int]$trial.capture_duration_s) `
        -Stimulus "$($trial.trial_id) | $($trial.stimulus_file)" `
        -ExpectedClass $trial.expected_class `
        -QualityLevel controlled `
        -TestType $trial.test_type `
        -Source $source `
        -DistanceCm ([int]$trial.distance_cm) `
        -VolumePercent ([int]$trial.volume_percent) `
        -StimulusHash $trial.sha256 `
        -Notes "Pilot order $order; true category $($trial.true_category); fixed seed 120." `
        -PlaybackFile $audioPath `
        -PlaybackDelaySeconds 3 `
        -FirmwareCommit "9a614d2" `
        -ModelName "YAMNet-256 Hazard-5 + Speech int8" `
        -ModelClasses 6
}

Write-Host ""
Write-Host "Pilot capture complete. Do not edit experiments/runs.csv or experiments/frames.csv manually."
Write-Host "Tell Codex that the pilot is done so the workbook and graphs can be rebuilt."
