param(
    [string]$ReviewDirectory = "experiments\transient_event_review",
    [switch]$ValidateOnly,
    [switch]$Redo
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$reviewDir = if ([IO.Path]::IsPathRooted($ReviewDirectory)) {
    [IO.Path]::GetFullPath($ReviewDirectory)
}
else {
    [IO.Path]::GetFullPath((Join-Path $repoRoot $ReviewDirectory))
}
$manifestPath = Join-Path $reviewDir "transient_event_review_manifest.csv"
$responsePath = Join-Path $reviewDir "transient_event_review_responses.csv"

if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Review manifest is missing. Run ml/prepare_transient_event_windows.py first."
}

$trials = @(Import-Csv -LiteralPath $manifestPath | Sort-Object { [int]$_.review_order })
if ($trials.Count -eq 0) {
    throw "The transient-event review manifest contains no clips."
}

$existing = @{}
if (Test-Path -LiteralPath $responsePath) {
    foreach ($row in Import-Csv -LiteralPath $responsePath) {
        $existing[$row.review_id] = $row
    }
}

foreach ($trial in $trials) {
    $audioPath = [IO.Path]::GetFullPath((Join-Path $repoRoot $trial.stimulus_path))
    if (-not (Test-Path -LiteralPath $audioPath -PathType Leaf)) {
        throw "Missing WAV for $($trial.review_id): $audioPath"
    }
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $audioPath).Hash.ToLowerInvariant()
    if ($actualHash -ne $trial.stimulus_sha256.ToLowerInvariant()) {
        throw "Stimulus hash mismatch for $($trial.review_id)."
    }
}

if ($ValidateOnly) {
    Write-Host "Validated all $($trials.Count) review clips and SHA-256 hashes."
    Write-Host "No audio was played and no response was written."
    exit 0
}

function Get-FriendlyLabel($className) {
    if ($className -eq "gunshot_gunfire") { return "gunshot or gunfire" }
    if ($className -eq "glass_breaking") { return "glass breaking" }
    return $className -replace "_", " "
}

Write-Host "Transient-event extraction review: $($trials.Count) one-second clips."
Write-Host "Keep one comfortable playback volume for the entire review."
Write-Host "The original loudness is preserved; quiet recordings may therefore sound quiet."
Write-Host "Extraction scores and model predictions are intentionally hidden."
Write-Host "Responses are saved after every clip to $responsePath"

foreach ($trial in $trials) {
    if ((-not $Redo) -and $existing.ContainsKey($trial.review_id)) {
        Write-Host "Skipping completed $($trial.review_id)."
        continue
    }

    $audioPath = [IO.Path]::GetFullPath((Join-Path $repoRoot $trial.stimulus_path))
    while ($true) {
        Write-Host ""
        Write-Host "[$($trial.review_order)/$($trials.Count)] $($trial.review_id) | intended sound: $(Get-FriendlyLabel $trial.expected_class)"
        $player = [System.Media.SoundPlayer]::new($audioPath)
        try {
            $player.Load()
            $player.PlaySync()
        }
        finally {
            $player.Dispose()
        }

        $validity = (Read-Host "Event [c=clear/canonical, a=atypical but valid, x=wrong or absent, r=replay, q=quit]").Trim().ToLowerInvariant()
        if ($validity -eq "r") { continue }
        if ($validity -eq "q") {
            Write-Host "Review stopped safely. Run the same command to resume."
            exit 0
        }
        if ($validity -notin @("c", "a", "x")) {
            Write-Host "Invalid response; replaying the clip."
            continue
        }

        $completeness = (Read-Host "Event boundary [f=complete, t=truncated/cut, u=unsure]").Trim().ToLowerInvariant()
        if ($completeness -notin @("f", "t", "u")) {
            Write-Host "Invalid response; replaying the clip."
            continue
        }
        $audibility = (Read-Host "Audibility [n=normal, q=quiet, l=loud/distorted]").Trim().ToLowerInvariant()
        if ($audibility -notin @("n", "q", "l")) {
            Write-Host "Invalid response; replaying the clip."
            continue
        }
        $note = Read-Host "Optional short note (Enter to leave blank)"

        $validityMap = @{ c = "canonical"; a = "atypical_valid"; x = "wrong_or_absent" }
        $completenessMap = @{ f = "complete"; t = "truncated"; u = "unsure" }
        $audibilityMap = @{ n = "normal"; q = "quiet"; l = "loud_distorted" }
        $existing[$trial.review_id] = [pscustomobject][ordered]@{
            review_order = [int]$trial.review_order
            review_id = $trial.review_id
            expected_class = $trial.expected_class
            stimulus_sha256 = $trial.stimulus_sha256
            validity = $validityMap[$validity]
            completeness = $completenessMap[$completeness]
            audibility = $audibilityMap[$audibility]
            note = $note
        }

        @($existing.Values) |
            Sort-Object { [int]$_.review_order } |
            Export-Csv -LiteralPath $responsePath -NoTypeInformation -Encoding utf8
        Write-Host "Saved $($trial.review_id)."
        break
    }
}

Write-Host "Review complete. Tell Codex when it is done."
