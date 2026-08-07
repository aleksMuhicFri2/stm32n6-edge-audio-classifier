param(
    [string]$Port = "COM3",
    [int]$BaudRate = 14400,
    [ValidateRange(1, 3600)]
    [int]$DurationSeconds = 30,
    [Parameter(Mandatory = $true)]
    [string]$Stimulus,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedClass,
    [ValidateSet("preliminary", "controlled")]
    [string]$QualityLevel = "preliminary",
    [ValidateSet("positive", "ood", "idle", "performance")]
    [string]$TestType = "positive",
    [string]$Source = "unspecified",
    [Nullable[int]]$DistanceCm = $null,
    [Nullable[int]]$VolumePercent = $null,
    [string]$StimulusHash = "",
    [string]$Notes = "",
    [string]$PlaybackFile = "",
    [ValidateRange(0, 60)]
    [int]$PlaybackDelaySeconds = 3,
    [string]$FirmwareCommit = "",
    [string]$ModelName = "YAMNet-256 Hazard-5 + Speech int8",
    [ValidateRange(1, 1000)]
    [int]$ModelClasses = 6
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$experimentsDir = Join-Path $repoRoot "experiments"
$rawDir = Join-Path $experimentsDir "raw"
$runsPath = Join-Path $experimentsDir "runs.csv"
$framesPath = Join-Path $experimentsDir "frames.csv"

if (-not (Test-Path -LiteralPath $runsPath) -or -not (Test-Path -LiteralPath $framesPath)) {
    throw "Experiment CSV files are missing. Run this tool from the thesis repository."
}
if ($QualityLevel -eq "controlled" -and $TestType -ne "idle") {
    if ($null -eq $DistanceCm -or $null -eq $VolumePercent -or $Source -eq "unspecified" -or -not $StimulusHash) {
        throw "Controlled non-idle runs require -DistanceCm, -VolumePercent, -Source, and -StimulusHash."
    }
}
if ($PlaybackFile -and -not (Test-Path -LiteralPath $PlaybackFile)) {
    throw "Playback file does not exist: $PlaybackFile"
}

$start = Get-Date
$runId = "RUN-" + $start.ToString("yyyyMMdd-HHmmss")
$rawRelativePath = "experiments/raw/$runId.txt"
$rawPath = Join-Path $repoRoot ($rawRelativePath -replace "/", "\")
$sourceCommit = (& git -C $repoRoot rev-parse --short HEAD 2>$null)
if (-not $sourceCommit) { $sourceCommit = "unknown" }
$gitCommit = if ($FirmwareCommit) { $FirmwareCommit } else { $sourceCommit }
$resolvedPlaybackFile = if ($PlaybackFile) {
    (Resolve-Path -LiteralPath $PlaybackFile).Path
} else {
    ""
}

$serial = [System.IO.Ports.SerialPort]::new(
    $Port,
    $BaudRate,
    [System.IO.Ports.Parity]::None,
    8,
    [System.IO.Ports.StopBits]::One
)
$serial.Handshake = [System.IO.Ports.Handshake]::None
$serial.ReadTimeout = 500
$rawText = ""
$player = $null
$playbackStarted = $false

if ($resolvedPlaybackFile) {
    $player = [System.Media.SoundPlayer]::new($resolvedPlaybackFile)
    $player.Load()
}

Write-Host "Starting $runId on $Port for $DurationSeconds seconds."
Write-Host "Stimulus: $Stimulus | Expected: $ExpectedClass | Type: $TestType"

try {
    $serial.Open()
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt $DurationSeconds) {
        if ($player -and -not $playbackStarted -and
            $timer.Elapsed.TotalSeconds -ge $PlaybackDelaySeconds) {
            Write-Host "Playing $resolvedPlaybackFile"
            $player.Play()
            $playbackStarted = $true
        }
        $chunk = $serial.ReadExisting()
        if ($chunk) { $rawText += $chunk }
        Start-Sleep -Milliseconds 50
    }
}
finally {
    if ($player) {
        $player.Stop()
        $player.Dispose()
    }
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
}

$end = Get-Date
$ansiPattern = [char]27 + "\[[0-9;?]*[ -/]*[@-~]"
$cleanText = [regex]::Replace($rawText, $ansiPattern, "")
$header = @(
    "run_id=$runId",
    "recorded_at=$($start.ToString('o'))",
    "port=$Port",
    "baud_rate=$BaudRate",
    "duration_seconds=$DurationSeconds",
    "stimulus=$Stimulus",
    "stimulus_hash=$StimulusHash",
    "expected_class=$ExpectedClass",
    "test_type=$TestType",
    "source=$Source",
    "distance_cm=$DistanceCm",
    "volume_percent=$VolumePercent",
    "firmware_git_commit=$gitCommit",
    "capture_source_git_commit=$sourceCommit",
    "playback_file=$resolvedPlaybackFile",
    "playback_delay_seconds=$PlaybackDelaySeconds",
    "decision_filter=activity 4000; EMA alpha 0.65; enter 0.65; release 0.50; switch margin 0.08; speech guard 0.27",
    "notes=$Notes",
    "--- UART ---"
) -join [Environment]::NewLine
[System.IO.File]::WriteAllText($rawPath, $header + [Environment]::NewLine + $cleanText)

$framePattern = "\|\s*(\d+)\s*\|\s*([\d.]+)%\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|"
$aedPattern = "AED_CSV,(\d+),([01]),([^,\r\n]+),([^,\r\n]+),([\d.]+),([^,\r\n]+),([\d.]+),([^,\r\n]+),([\d.]+),([^,\r\n]+),([\d.]+),([01])"
$statsByFrame = @{}

foreach ($match in [regex]::Matches($cleanText, $framePattern)) {
    $statsByFrame[[int]$match.Groups[1].Value] = [pscustomobject]@{
        cpu_load_percent = [double]$match.Groups[2].Value
        preprocess_ms = [double]$match.Groups[3].Value
        inference_ms = [double]$match.Groups[4].Value
        postprocess_ms = [double]$match.Groups[5].Value
    }
}

$aedMatches = [regex]::Matches($cleanText, $aedPattern)
if ($aedMatches.Count -eq 0) {
    throw "No AED_CSV records were parsed. Flash the temporal-filter firmware first. Raw UART was saved to $rawPath."
}

$safeOutputClasses = @("unknown", "waiting", "no_output", "speech")
$hazardClasses = @("dog_bark", "glass_breaking", "gunshot_gunfire", "siren", "thunderstorm")
$frames = [System.Collections.Generic.List[object]]::new()
for ($index = 0; $index -lt $aedMatches.Count; $index++) {
    $match = $aedMatches[$index]
    $frameId = [int]$match.Groups[1].Value
    $predictedClass = $match.Groups[4].Value
    $stats = $statsByFrame[$frameId]
    if ($TestType -in @("ood", "idle")) {
        $isCorrect = $predictedClass -in $safeOutputClasses
    }
    else {
        $isCorrect = $predictedClass -eq $ExpectedClass
    }

    $frames.Add([pscustomobject][ordered]@{
        run_id = $runId
        timestamp_offset_s = [math]::Round(($index / [math]::Max(1, $aedMatches.Count - 1)) * $DurationSeconds, 3)
        frame_id = $frameId
        expected_class = $ExpectedClass
        test_type = $TestType
        predicted_class = $predictedClass
        is_correct = $isCorrect
        cpu_load_percent = if ($null -ne $stats) { $stats.cpu_load_percent } else { $null }
        preprocess_ms = if ($null -ne $stats) { $stats.preprocess_ms } else { $null }
        inference_ms = if ($null -ne $stats) { $stats.inference_ms } else { $null }
        postprocess_ms = if ($null -ne $stats) { $stats.postprocess_ms } else { $null }
        record_completeness = if ($null -ne $stats) { "direct_complete_estimated_offset" } else { "decision_complete_no_timing" }
        audio_active = [bool]([int]$match.Groups[2].Value)
        decision_confidence = [double]$match.Groups[5].Value
        top1_class = $match.Groups[6].Value
        top1_confidence = [double]$match.Groups[7].Value
        top2_class = $match.Groups[8].Value
        top2_confidence = [double]$match.Groups[9].Value
        top3_class = $match.Groups[10].Value
        top3_confidence = [double]$match.Groups[11].Value
        decision_changed = [bool]([int]$match.Groups[12].Value)
    })
}

$frames | Export-Csv -LiteralPath $framesPath -NoTypeInformation -Append -Encoding utf8
$detections = @($frames | Where-Object { $_.predicted_class -notin @("no_output", "unknown", "waiting") })
$hazardDetections = @($frames | Where-Object { $_.predicted_class -in $hazardClasses })
$correct = @($frames | Where-Object { $_.is_correct }).Count
$unknown = @($frames | Where-Object { $_.predicted_class -eq "unknown" }).Count
$result = if ($TestType -eq "positive") {
    if (@($frames | Where-Object { $_.predicted_class -eq $ExpectedClass }).Count -gt 0) { "pass_with_detection" } else { "fail_no_target_detection" }
} elseif ($hazardDetections.Count -eq 0) {
    "pass_no_false_positive"
} else {
    "fail_false_positive"
}

$run = [pscustomobject][ordered]@{
    run_id = $runId
    recorded_at = $start.ToString("o")
    quality_level = $QualityLevel
    test_type = $TestType
    board = "STM32N6570-DK"
    board_revision = "Rev B"
    firmware_commit = $gitCommit
    configuration = "BM EMA-0.65 hysteresis"
    model_name = $ModelName
    model_classes = $ModelClasses
    stimulus = $Stimulus
    expected_class = $ExpectedClass
    source = $Source
    distance_cm = $DistanceCm
    volume_percent = $VolumePercent
    duration_s = [math]::Round(($end - $start).TotalSeconds, 3)
    frame_start = $frames[0].frame_id
    frame_end = $frames[$frames.Count - 1].frame_id
    frames_observed = $frames.Count
    detection_events = $detections.Count
    correct_events = $correct
    unknown_events = $unknown
    cpu_load_percent_mean = [math]::Round(($frames | Measure-Object cpu_load_percent -Average).Average, 4)
    preprocess_ms_mean = [math]::Round(($frames | Measure-Object preprocess_ms -Average).Average, 4)
    inference_ms_mean = [math]::Round(($frames | Measure-Object inference_ms -Average).Average, 4)
    postprocess_ms_mean = [math]::Round(($frames | Measure-Object postprocess_ms -Average).Average, 4)
    result = $result
    raw_log_path = $rawRelativePath
    notes = $Notes
    stimulus_hash = $StimulusHash
}
$run | Export-Csv -LiteralPath $runsPath -NoTypeInformation -Append -Encoding utf8

Write-Host "Saved raw UART: $rawRelativePath"
Write-Host "Parsed frames: $($frames.Count); detections: $($detections.Count); result: $result"
