param(
    [string[]]$Classes = @("speech", "glass_breaking", "gunshot_gunfire"),
    [switch]$ValidateOnly,
    [switch]$Redo
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$manifestPath = Join-Path $repoRoot "experiments\pilot_evaluation\pilot_manifest.csv"
$responsePath = Join-Path $repoRoot "experiments\pilot_evaluation\listening_review_responses.csv"

$trials = @(
    Import-Csv -LiteralPath $manifestPath |
        Where-Object { $_.expected_class -in $Classes } |
        Sort-Object { [int]$_.trial_order }
)

if ($trials.Count -eq 0) {
    throw "No listening-review trials matched: $($Classes -join ', ')"
}

$existing = @{}
if (Test-Path -LiteralPath $responsePath) {
    foreach ($row in Import-Csv -LiteralPath $responsePath) {
        $existing[$row.trial_id] = $row
    }
}

foreach ($trial in $trials) {
    $audioPath = [IO.Path]::GetFullPath((Join-Path $repoRoot $trial.stimulus_path))
    if (-not (Test-Path -LiteralPath $audioPath -PathType Leaf)) {
        throw "Missing WAV for $($trial.trial_id): $audioPath"
    }
    if ([IO.Path]::GetExtension($audioPath).ToLowerInvariant() -ne ".wav") {
        throw "SoundPlayer requires WAV input: $audioPath"
    }
}

if ($ValidateOnly) {
    Write-Host "Validated $($trials.Count) blinded listening-review clips. No audio was played."
    exit 0
}

Write-Host "Blinded pilot-stimulus review: $($trials.Count) clips."
Write-Host "Board predictions and pass/fail results are intentionally hidden."
Write-Host "Responses are saved after every clip to $responsePath"

Add-Type -AssemblyName System.Windows.Extensions

foreach ($trial in $trials) {
    if ((-not $Redo) -and $existing.ContainsKey($trial.trial_id)) {
        Write-Host "Skipping completed $($trial.trial_id)."
        continue
    }

    $audioPath = [IO.Path]::GetFullPath((Join-Path $repoRoot $trial.stimulus_path))
    while ($true) {
        Write-Host ""
        Write-Host "$($trial.trial_id) | expected: $($trial.expected_class) | $($trial.stimulus_file)"
        $player = [System.Media.SoundPlayer]::new($audioPath)
        try {
            $player.Load()
            $player.PlaySync()
        }
        finally {
            $player.Dispose()
        }

        $representativeness = (Read-Host "Representativeness [c=canonical, a=atypical-valid, x=ambiguous/wrong, r=replay, s=skip, q=quit]").Trim().ToLowerInvariant()
        if ($representativeness -eq "r") { continue }
        if ($representativeness -eq "q") {
            Write-Host "Review stopped. Run the same command to resume."
            exit 0
        }
        if ($representativeness -eq "s") { break }
        if ($representativeness -notin @("c", "a", "x")) {
            Write-Host "Invalid response; replaying the clip."
            continue
        }

        $audibility = (Read-Host "Audibility [n=normal, q=quiet, l=loud/distorted]").Trim().ToLowerInvariant()
        if ($audibility -notin @("n", "q", "l")) {
            Write-Host "Invalid audibility response; replaying the clip."
            continue
        }
        $note = Read-Host "Optional short note (Enter to leave blank)"

        $representationMap = @{
            c = "canonical"
            a = "atypical_valid"
            x = "ambiguous_wrong"
        }
        $audibilityMap = @{
            n = "normal"
            q = "quiet"
            l = "loud_distorted"
        }
        $existing[$trial.trial_id] = [pscustomobject][ordered]@{
            trial_order = [int]$trial.trial_order
            trial_id = $trial.trial_id
            expected_class = $trial.expected_class
            stimulus_file = $trial.stimulus_file
            representativeness = $representationMap[$representativeness]
            audibility = $audibilityMap[$audibility]
            note = $note
        }

        @($existing.Values) |
            Sort-Object { [int]$_.trial_order } |
            Export-Csv -LiteralPath $responsePath -NoTypeInformation -Encoding utf8
        Write-Host "Saved $($trial.trial_id)."
        break
    }
}

Write-Host "Listening review complete. Tell Codex when it is done."
