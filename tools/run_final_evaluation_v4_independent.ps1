param(
    [string]$Port = "COM3",
    [ValidateRange(1, 60)]
    [int]$StartOrder = 1,
    [ValidateRange(1, 60)]
    [int]$EndOrder = 60,
    [switch]$ValidateOnly,
    [switch]$AutoConfirm
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$evaluationDir = Join-Path $repoRoot "experiments\final_evaluation_v4_independent"
$manifestPath = Join-Path $evaluationDir "manifest.csv"
$manifestInfoPath = Join-Path $evaluationDir "manifest.json"
$lockPath = Join-Path $evaluationDir "LOCK.json"
$attemptsPath = Join-Path $evaluationDir "attempts.csv"
$captureScript = Join-Path $PSScriptRoot "capture_uart_experiment.ps1"
$analysisScript = Join-Path $repoRoot "ml\analyze_final_evaluation_v4_independent.py"
$runsPath = Join-Path $repoRoot "experiments\runs.csv"
$evaluationId = "STM32N6-HAZARD6-FINAL-003"
$attemptId = "FE4-A01"
$modelName = "YAMNet-1024 V5 int8; six system classes (thunder merged into other)"
$modelHash = "6805110184e8295d73af52fc4093443a5a9867794e36b03e702e12c5a3d7548e"
$weightsHash = "0979d852a24f3f2180e10f32f920eddeee166fabc5148841af5678731c33352e"
$applicationHash = "e7e5e0d134cae4fe57bc2ab33848830b6efdff025e2e70af6bce3c3f9365d6bb"

if ($StartOrder -gt $EndOrder) {
    throw "StartOrder must be less than or equal to EndOrder."
}
foreach ($requiredPath in @(
    $manifestPath,
    $manifestInfoPath,
    $lockPath,
    $attemptsPath,
    $captureScript,
    $runsPath
)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Missing frozen final-evaluation file: $requiredPath"
    }
}

$info = Get-Content -LiteralPath $manifestInfoPath -Raw | ConvertFrom-Json
$lock = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
$manifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($info.evaluation_id -ne $evaluationId -or $info.attempt_id -ne $attemptId) {
    throw "Unexpected six-class final-evaluation identity."
}
if ($manifestHash -ne $info.manifest_sha256 -or $manifestHash -ne $lock.manifest_sha256) {
    throw "Frozen final-evaluation manifest hash mismatch."
}
if ($info.model_onnx_sha256 -ne $modelHash -or
    $info.weights_sha256 -ne $weightsHash -or
    $info.application_binary_sha256 -ne $applicationHash) {
    throw "Frozen model, weights or application identity changed."
}

$allTrials = @(Import-Csv -LiteralPath $manifestPath | Sort-Object { [int]$_.trial_order })
if ($allTrials.Count -ne 60 -or @($allTrials.trial_id | Select-Object -Unique).Count -ne 60) {
    throw "The frozen final manifest must contain 60 unique trials."
}
$expectedClasses = @(
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "other",
    "siren",
    "speech"
)
foreach ($className in $expectedClasses) {
    $count = @($allTrials | Where-Object expected_class -eq $className).Count
    if ($count -ne 10) { throw "Expected 10 $className trials; found $count." }
}
$otherCategories = @($allTrials | Where-Object expected_class -eq "other" | Select-Object -ExpandProperty true_category -Unique)
if ($otherCategories.Count -ne 10) {
    throw "The frozen other class must contain ten distinct categories."
}
foreach ($trial in $allTrials) {
    if ([int]$trial.volume_percent -ne 100 -or [int]$trial.distance_cm -ne 30 -or
        $trial.model_name -ne $modelName -or $trial.model_onnx_sha256 -ne $modelHash -or
        $trial.weights_sha256 -ne $weightsHash -or
        $trial.application_binary_sha256 -ne $applicationHash -or
        [int]$trial.system_classes -ne 6 -or [int]$trial.model_output_classes -ne 7) {
        throw "Frozen physical or system settings changed for $($trial.trial_id)."
    }
    $audioPath = (Resolve-Path -LiteralPath (
        Join-Path $repoRoot ($trial.stimulus_path -replace "/", "\")
    )).Path
    $actualHash = (Get-FileHash -LiteralPath $audioPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $trial.sha256) {
        throw "Stimulus hash mismatch for $($trial.trial_id)."
    }
}
if ($ValidateOnly) {
    Write-Host "Validated 60 reviewed stimuli, hashes, class balance and frozen settings."
    Write-Host "No audio was played and no result was captured."
    return
}
if ($Port -notin [System.IO.Ports.SerialPort]::GetPortNames()) {
    throw "Serial port $Port is not currently available."
}

$notePrefix = "Independent six-class final evaluation $evaluationId attempt $attemptId;"
$existingRuns = @(Import-Csv -LiteralPath $runsPath | Where-Object {
    $_.notes -like "$notePrefix*"
})
$existingTrialIds = @($existingRuns | ForEach-Object {
    ($_.stimulus -split "\|")[0].Trim()
})
if (@($existingTrialIds | Select-Object -Unique).Count -ne $existingTrialIds.Count) {
    throw "Duplicate final trial IDs already exist. Stop and tell Codex."
}
$trials = @($allTrials | Where-Object {
    [int]$_.trial_order -ge $StartOrder -and [int]$_.trial_order -le $EndOrder
})
$overlap = @($trials | Where-Object trial_id -in $existingTrialIds)
if ($overlap.Count) {
    throw "The selected range includes captured trial $($overlap[0].trial_id). Preserve evidence and select only uncaptured trials."
}

Write-Host "Frozen STM32N6 six-class evaluation: $($trials.Count) selected trials."
Write-Host "Before continuing:"
Write-Host "  1. Set Windows playback volume to 100 percent."
Write-Host "  2. Place the speaker 30 cm from the onboard microphone."
Write-Host "  3. Keep the room quiet and do not move the board or speaker."
Write-Host "  4. Press NRST once and do not reset during this attempt."
Write-Host "  5. Stop after material interference; do not repeat a model error."
Write-Host "The selected range takes approximately $([math]::Ceiling(($trials.Count * 18) / 60)) minutes plus loading time."
if (-not $AutoConfirm) {
    $confirmation = Read-Host "Type START to begin the frozen final evaluation"
    if ($confirmation -ne "START") {
        throw "Final evaluation cancelled before capture."
    }
}

$firstAudio = (Resolve-Path -LiteralPath (
    Join-Path $repoRoot ($trials[0].stimulus_path -replace "/", "\")
)).Path
$warmup = [System.Media.SoundPlayer]::new($firstAudio)
try {
    $warmup.Load()
    $warmup.Play()
    Start-Sleep -Milliseconds 250
    $warmup.Stop()
}
finally { $warmup.Dispose() }
Start-Sleep -Seconds 1

foreach ($trial in $trials) {
    $order = [int]$trial.trial_order
    $audioPath = (Resolve-Path -LiteralPath (
        Join-Path $repoRoot ($trial.stimulus_path -replace "/", "\")
    )).Path
    Write-Host ""
    Write-Host "[$order/60] $($trial.trial_id)"
    & $captureScript `
        -Port $Port `
        -BaudRate 14400 `
        -DurationSeconds ([int]$trial.capture_duration_s) `
        -Stimulus "$($trial.trial_id) | frozen reviewed six-class stimulus | $($trial.stimulus_file)" `
        -ExpectedClass $trial.expected_class `
        -QualityLevel controlled `
        -TestType positive `
        -Source "$($trial.source_dataset) $($trial.source_partition) independent playback" `
        -DistanceCm ([int]$trial.distance_cm) `
        -VolumePercent ([int]$trial.volume_percent) `
        -StimulusHash $trial.sha256 `
        -Notes "$notePrefix order $order; candidate $($trial.review_candidate_id); true category $($trial.true_category); source $($trial.source_dataset) $($trial.source_partition) $($trial.source_id); target max100ms $($trial.target_output_max_100ms_rms_dbfs) dBFS; manifest $manifestHash; application $applicationHash; weights $weightsHash." `
        -PlaybackFile $audioPath `
        -PlaybackDelaySeconds ([int]$trial.playback_delay_s) `
        -FirmwareCommit "bin-e7e5e0d" `
        -ModelName $modelName `
        -ModelClasses 7
}

$allFinalRuns = @(Import-Csv -LiteralPath $runsPath | Where-Object {
    $_.notes -like "$notePrefix*"
} | Sort-Object recorded_at)
$allIds = @($allFinalRuns | ForEach-Object {
    ($_.stimulus -split "\|")[0].Trim()
})
if ($allFinalRuns.Count -eq 60 -and @($allIds | Select-Object -Unique).Count -eq 60) {
    $operatorNote = if ($AutoConfirm) { "" } else {
        Read-Host "Optional room or playback observation (press Enter to skip)"
    }
    [pscustomobject][ordered]@{
        attempt_id = $attemptId
        status = "completed"
        started_at = $allFinalRuns[0].recorded_at
        completed_at = (Get-Date).ToString("o")
        first_run_id = $allFinalRuns[0].run_id
        last_run_id = $allFinalRuns[-1].run_id
        captured_trials = 60
        volume_percent = 100
        distance_cm = 30
        manifest_sha256 = $manifestHash
        operator_note = $operatorNote
    } | Export-Csv -LiteralPath $attemptsPath -NoTypeInformation -Append -Encoding utf8
    Write-Host "All 60 frozen trials are complete."
    if (Test-Path -LiteralPath $analysisScript -PathType Leaf) {
        $python = Join-Path (Split-Path $repoRoot -Parent) "ml-workspace\.venv\Scripts\python.exe"
        if (Test-Path -LiteralPath $python -PathType Leaf) {
            & $python $analysisScript
            if ($LASTEXITCODE -ne 0) {
                throw "Final analysis failed with exit code $LASTEXITCODE"
            }
        }
    }
    Write-Host "Tell Codex it is done."
} else {
    Write-Host "Captured $($allFinalRuns.Count)/60 final trials. Continue only with an uncaptured range."
}
