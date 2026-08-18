# Izvede slepi slušni pregled kandidatov brez prikaza napovedi modela ali ploščice.
# Odgovor se shrani po vsakem posnetku, zato je pregled mogoče varno nadaljevati.
param([switch]$ValidateOnly)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$reviewRoot = Join-Path $repoRoot "experiments\final_evaluation_v4_independent_review"
$manifestPath = Join-Path $reviewRoot "manifest_six_class.csv"
$responsePath = Join-Path $reviewRoot "responses.csv"

if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Independent V4 candidate manifest is missing."
}
$trials = @(Import-Csv -LiteralPath $manifestPath | Sort-Object { [int]$_.review_order })
$existing = @{}
if (Test-Path -LiteralPath $responsePath) {
    foreach ($row in Import-Csv -LiteralPath $responsePath) {
        $existing[$row.candidate_id] = $row
    }
}

foreach ($trial in $trials) {
    $audioPath = [IO.Path]::GetFullPath($trial.stimulus_path)
    if (-not (Test-Path -LiteralPath $audioPath -PathType Leaf)) {
        throw "Missing candidate audio: $audioPath"
    }
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $audioPath).Hash.ToLowerInvariant()
    if ($actualHash -ne $trial.stimulus_sha256.ToLowerInvariant()) {
        throw "Candidate hash mismatch for $($trial.candidate_id)."
    }
}
if ($ValidateOnly) {
    Write-Host "Validated all $($trials.Count) independent candidate files and hashes."
    exit 0
}

Write-Host "Blind semantic review of $($trials.Count) source-disjoint candidates."
Write-Host "The board and model are not used; predictions are unavailable."
Write-Host "Responses are saved after each clip and the command can be resumed."

foreach ($trial in $trials) {
    if ($existing.ContainsKey($trial.candidate_id)) {
        Write-Host "Skipping completed $($trial.candidate_id)."
        continue
    }
    $audioPath = [IO.Path]::GetFullPath($trial.stimulus_path)
    while ($true) {
        Write-Host ""
        Write-Host "[$($trial.review_order)/$($trials.Count)] $($trial.candidate_id) | intended sound: $($trial.true_category -replace '_',' ')"
        $player = [System.Media.SoundPlayer]::new($audioPath)
        try { $player.Load(); $player.PlaySync() } finally { $player.Dispose() }
        $validity = (Read-Host "Sound [c=canonical, a=atypical but valid, x=wrong/absent, r=replay, q=quit]").Trim().ToLowerInvariant()
        if ($validity -eq "r") { continue }
        if ($validity -eq "q") {
            Write-Host "Review stopped safely. Run the same command to resume."
            exit 0
        }
        if ($validity -notin @("c", "a", "x")) { continue }
        $completeness = (Read-Host "Event [f=complete, t=truncated/cut, u=unsure]").Trim().ToLowerInvariant()
        if ($completeness -notin @("f", "t", "u")) { continue }
        $audibility = (Read-Host "Audibility [n=normal, q=quiet, l=loud/distorted]").Trim().ToLowerInvariant()
        if ($audibility -notin @("n", "q", "l")) { continue }
        $artifact = (Read-Host "Artifact [n=none, h=high-pitched tone, s=static/noise, o=other]").Trim().ToLowerInvariant()
        if ($artifact -notin @("n", "h", "s", "o")) { continue }
        $note = Read-Host "Optional short note"
        $validityMap = @{ c = "canonical"; a = "atypical_valid"; x = "wrong_or_absent" }
        $completenessMap = @{ f = "complete"; t = "truncated"; u = "unsure" }
        $audibilityMap = @{ n = "normal"; q = "quiet"; l = "loud_distorted" }
        $artifactMap = @{ n = "none"; h = "high_pitched_tone"; s = "static_or_noise"; o = "other" }
        $existing[$trial.candidate_id] = [pscustomobject][ordered]@{
            review_order = [int]$trial.review_order
            candidate_id = $trial.candidate_id
            stimulus_sha256 = $trial.stimulus_sha256
            validity = $validityMap[$validity]
            completeness = $completenessMap[$completeness]
            audibility = $audibilityMap[$audibility]
            artifact = $artifactMap[$artifact]
            note = $note
        }
        @($existing.Values) |
            Sort-Object { [int]$_.review_order } |
            Export-Csv -LiteralPath $responsePath -NoTypeInformation -Encoding utf8
        break
    }
}

$python = Join-Path (Split-Path $repoRoot -Parent) "ml-workspace\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Project Python environment is missing: $python"
}
& $python (Join-Path $repoRoot "ml\analyze_final_evaluation_v4_independent_review.py")
if ($LASTEXITCODE -ne 0) {
    throw "Independent candidate review analysis failed with exit code $LASTEXITCODE"
}
Write-Host "Candidate review complete. Tell Codex when it is done."
