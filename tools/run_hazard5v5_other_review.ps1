param([switch]$ValidateOnly)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$reviewRoot = Join-Path $repoRoot 'experiments\hazard5v5_other_review_v9'
$manifestPath = Join-Path $reviewRoot 'manifest.csv'
$responsePath = Join-Path $reviewRoot 'responses.csv'

if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw 'Other-class review manifest is missing.'
}
$trials = @(Import-Csv -LiteralPath $manifestPath | Sort-Object { [int]$_.review_order })
$existing = @{}
if (Test-Path -LiteralPath $responsePath) {
    foreach ($row in Import-Csv -LiteralPath $responsePath) {
        $existing[$row.review_id] = $row
    }
}

foreach ($trial in $trials) {
    $audioPath = [IO.Path]::GetFullPath($trial.stimulus_path)
    if (-not (Test-Path -LiteralPath $audioPath -PathType Leaf)) {
        throw "Missing review audio: $audioPath"
    }
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $audioPath).Hash.ToLowerInvariant()
    if ($actualHash -ne $trial.stimulus_sha256.ToLowerInvariant()) {
        throw "Review hash mismatch for $($trial.review_id)."
    }
}
if ($ValidateOnly) {
    Write-Host "Validated all $($trials.Count) other-class review files and hashes."
    exit 0
}

Write-Host "Blinded review of $($trials.Count) difficult OTHER training candidates."
Write-Host 'Model predictions and scores are intentionally hidden.'
Write-Host 'Responses are saved after every clip and the review can be resumed.'

foreach ($trial in $trials) {
    if ($existing.ContainsKey($trial.review_id)) {
        Write-Host "Skipping completed $($trial.review_id)."
        continue
    }
    $audioPath = [IO.Path]::GetFullPath($trial.stimulus_path)
    while ($true) {
        Write-Host ''
        Write-Host "[$($trial.review_order)/$($trials.Count)] $($trial.review_id) | group: $($trial.other_group -replace '_',' ')"
        Write-Host "Source labels: $($trial.source_labels -replace '_',' ')"
        $player = [System.Media.SoundPlayer]::new($audioPath)
        try { $player.Load(); $player.PlaySync() } finally { $player.Dispose() }
        $validity = (Read-Host 'OTHER example [o=clear other, a=ambiguous other, x=wrong/target/speech, r=replay, q=quit]').Trim().ToLowerInvariant()
        if ($validity -eq 'r') { continue }
        if ($validity -eq 'q') {
            Write-Host 'Review stopped safely. Run the same command to resume.'
            exit 0
        }
        if ($validity -notin @('o', 'a', 'x')) { continue }
        $target = (Read-Host 'Contains a target hazard or intelligible speech? [n=no, y=yes, u=unsure]').Trim().ToLowerInvariant()
        if ($target -notin @('n', 'y', 'u')) { continue }
        $audibility = (Read-Host 'Audibility [n=normal, q=quiet, l=loud/distorted]').Trim().ToLowerInvariant()
        if ($audibility -notin @('n', 'q', 'l')) { continue }
        $note = Read-Host 'Optional short note'
        $validityMap = @{ o = 'clear_other'; a = 'ambiguous_other'; x = 'wrong_target_or_speech' }
        $targetMap = @{ n = 'no'; y = 'yes'; u = 'unsure' }
        $audibilityMap = @{ n = 'normal'; q = 'quiet'; l = 'loud_distorted' }
        $existing[$trial.review_id] = [pscustomobject][ordered]@{
            review_order = [int]$trial.review_order
            review_id = $trial.review_id
            stimulus_sha256 = $trial.stimulus_sha256
            other_validity = $validityMap[$validity]
            contains_target_or_speech = $targetMap[$target]
            audibility = $audibilityMap[$audibility]
            note = $note
        }
        @($existing.Values) |
            Sort-Object { [int]$_.review_order } |
            Export-Csv -LiteralPath $responsePath -NoTypeInformation -Encoding utf8
        break
    }
}

$python = Join-Path (Split-Path $repoRoot -Parent) 'ml-workspace\.venv\Scripts\python.exe'
& $python (Join-Path $repoRoot 'ml\analyze_hazard5v5_other_review.py')
if ($LASTEXITCODE -ne 0) {
    throw "Other-class listening review failed with exit code $LASTEXITCODE"
}
Write-Host 'Review complete and quality gate passed. Tell Codex when it is done.'
