param(
    [switch]$ValidateOnly,
    [switch]$Redo
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$experimentDir = Join-Path $repoRoot "experiments\pilot2_evaluation"
$manifestPath = Join-Path $experimentDir "pilot2_review_candidates.csv"
$responsePath = Join-Path $experimentDir "pilot2_review_responses.csv"

if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Pilot 2 review manifest is missing. Run ml/prepare_pilot2_candidates.py first."
}

$trials = @(Import-Csv -LiteralPath $manifestPath | Sort-Object { [int]$_.candidate_order })
if ($trials.Count -ne 58) {
    throw "Expected 58 Pilot 2 review candidates; found $($trials.Count)."
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
        throw "Missing normalized WAV for $($trial.review_id): $audioPath"
    }
    if ([IO.Path]::GetExtension($audioPath).ToLowerInvariant() -ne ".wav") {
        throw "SoundPlayer requires WAV input: $audioPath"
    }
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $audioPath).Hash.ToLowerInvariant()
    if ($actualHash -ne $trial.stimulus_sha256.ToLowerInvariant()) {
        throw "Stimulus hash mismatch for $($trial.review_id)."
    }
}

if ($ValidateOnly) {
    Write-Host "Validated all $($trials.Count) Pilot 2 review clips and SHA-256 hashes."
    Write-Host "No audio was played and no response was written."
    exit 0
}

function Get-FriendlyLabel($trial) {
    if ($trial.test_type -eq "ood") {
        return "safe non-hazard: $($trial.true_category -replace '_', ' ')"
    }
    return $trial.expected_class -replace "_", " "
}

function Read-Variant($trial) {
    if ($trial.expected_class -eq "speech") {
        while ($true) {
            $answer = (Read-Host "Speech form [c=normal conversation, o=other voice, n=not speech]").Trim().ToLowerInvariant()
            if ($answer -in @("c", "o", "n")) {
                return @{ c = "normal_conversation"; o = "other_voice"; n = "not_speech" }[$answer]
            }
            Write-Host "Invalid response."
        }
    }
    if ($trial.expected_class -eq "glass_breaking") {
        while ($true) {
            $answer = (Read-Host "Glass form [s=clean shatter, i=shatter plus impact, h=handling/clink]").Trim().ToLowerInvariant()
            if ($answer -in @("s", "i", "h")) {
                return @{ s = "clean_shatter"; i = "shatter_plus_impact"; h = "handling_or_clink" }[$answer]
            }
            Write-Host "Invalid response."
        }
    }
    if ($trial.expected_class -eq "gunshot_gunfire") {
        while ($true) {
            $answer = (Read-Host "Gunfire form [s=single shot, m=multiple shots, i=impact/unclear]").Trim().ToLowerInvariant()
            if ($answer -in @("s", "m", "i")) {
                return @{ s = "single_shot"; m = "multiple_shots"; i = "impact_or_unclear" }[$answer]
            }
            Write-Host "Invalid response."
        }
    }
    return "not_recorded"
}

Write-Host "Pilot 2 blinded semantic review: $($trials.Count) normalized development clips."
Write-Host "Set Windows playback volume to 50 percent and keep it fixed."
Write-Host "No board prediction, model score, source filename, or Pilot 1 result is displayed."
Write-Host "Responses are saved after every clip to $responsePath"
Write-Host "Canonical means a clear, ordinary example suitable for the product."

foreach ($trial in $trials) {
    if ((-not $Redo) -and $existing.ContainsKey($trial.review_id)) {
        Write-Host "Skipping completed $($trial.review_id)."
        continue
    }

    $audioPath = [IO.Path]::GetFullPath((Join-Path $repoRoot $trial.stimulus_path))
    while ($true) {
        Write-Host ""
        Write-Host "$($trial.review_id) | intended sound: $(Get-FriendlyLabel $trial)"
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
            Write-Host "Review stopped safely. Run the same command to resume."
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
        $variant = Read-Variant $trial
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
        $existing[$trial.review_id] = [pscustomobject][ordered]@{
            candidate_order = [int]$trial.candidate_order
            review_id = $trial.review_id
            expected_class = $trial.expected_class
            true_category = $trial.true_category
            stimulus_sha256 = $trial.stimulus_sha256
            representativeness = $representationMap[$representativeness]
            audibility = $audibilityMap[$audibility]
            variant = $variant
            note = $note
        }

        @($existing.Values) |
            Sort-Object { [int]$_.candidate_order } |
            Export-Csv -LiteralPath $responsePath -NoTypeInformation -Encoding utf8
        Write-Host "Saved $($trial.review_id)."
        break
    }
}

Write-Host "Pilot 2 stimulus review complete. Tell Codex when it is done."
