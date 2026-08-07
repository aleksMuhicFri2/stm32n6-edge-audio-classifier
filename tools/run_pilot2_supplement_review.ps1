param(
    [switch]$ValidateOnly,
    [switch]$Redo
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$experimentDir = Join-Path $repoRoot "experiments\pilot2_evaluation"
$manifestPath = Join-Path $experimentDir "pilot2_supplement_candidates.csv"
$responsePath = Join-Path $experimentDir "pilot2_supplement_responses.csv"

if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Pilot 2 supplement manifest is missing."
}
$trials = @(Import-Csv -LiteralPath $manifestPath | Sort-Object { [int]$_.candidate_order })
if ($trials.Count -ne 24) {
    throw "Expected 24 supplemental candidates; found $($trials.Count)."
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
    Write-Host "Validated all 24 supplemental clips and hashes. No audio was played."
    exit 0
}

function Get-FriendlyLabel($trial) {
    if ($trial.test_type -eq "ood") {
        return "safe non-hazard: $($trial.true_category -replace '_', ' ')"
    }
    return $trial.expected_class -replace "_", " "
}

Write-Host "Short Pilot 2 supplemental review: 24 clips."
Write-Host "IMPORTANT: disconnect the STM32 board or completely cover/turn away its screen."
Write-Host "Do not inspect the board during this review. These labels must describe audio only."
Write-Host "Keep Windows playback volume fixed at 50 percent."
Write-Host "This supplement omits speech, siren, dog bark, and gunfire."

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

        $rep = (Read-Host "Representativeness [c=canonical, a=atypical-valid, x=ambiguous/wrong, r=replay, s=skip, q=quit]").Trim().ToLowerInvariant()
        if ($rep -eq "r") { continue }
        if ($rep -eq "q") {
            Write-Host "Review stopped safely. Run the same command to resume."
            exit 0
        }
        if ($rep -eq "s") { break }
        if ($rep -notin @("c", "a", "x")) {
            Write-Host "Invalid response; replaying."
            continue
        }

        $audibility = (Read-Host "Audibility [n=normal, q=quiet, l=loud/distorted]").Trim().ToLowerInvariant()
        if ($audibility -notin @("n", "q", "l")) {
            Write-Host "Invalid audibility response; replaying."
            continue
        }
        $variant = "not_recorded"
        if ($trial.expected_class -eq "glass_breaking") {
            while ($true) {
                $form = (Read-Host "Glass form [s=clean shatter, i=shatter plus impact, h=handling/clink]").Trim().ToLowerInvariant()
                if ($form -in @("s", "i", "h")) {
                    $variant = @{ s = "clean_shatter"; i = "shatter_plus_impact"; h = "handling_or_clink" }[$form]
                    break
                }
                Write-Host "Invalid response."
            }
        }
        $note = Read-Host "Optional audio-only note (Enter to leave blank)"
        $existing[$trial.review_id] = [pscustomobject][ordered]@{
            candidate_order = [int]$trial.candidate_order
            review_id = $trial.review_id
            expected_class = $trial.expected_class
            true_category = $trial.true_category
            stimulus_sha256 = $trial.stimulus_sha256
            representativeness = @{ c = "canonical"; a = "atypical_valid"; x = "ambiguous_wrong" }[$rep]
            audibility = @{ n = "normal"; q = "quiet"; l = "loud_distorted" }[$audibility]
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

Write-Host "Supplemental review complete. Tell Codex when it is done."
