param([switch]$ValidateOnly, [switch]$Redo)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dir = Join-Path $repoRoot "experiments\pilot2_evaluation"
$manifestPath = Join-Path $dir "pilot2_ambient_candidates.csv"
$responsePath = Join-Path $dir "pilot2_ambient_responses.csv"
$trials = @(Import-Csv -LiteralPath $manifestPath | Sort-Object { [int]$_.candidate_order })
if ($trials.Count -ne 4) { throw "Expected four ambient candidates." }

$existing = @{}
if (Test-Path -LiteralPath $responsePath) {
    foreach ($row in Import-Csv -LiteralPath $responsePath) { $existing[$row.review_id] = $row }
}
foreach ($trial in $trials) {
    $audioPath = [IO.Path]::GetFullPath((Join-Path $repoRoot $trial.stimulus_path))
    $hash = (Get-FileHash -LiteralPath $audioPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $trial.stimulus_sha256.ToLowerInvariant()) {
        throw "Hash mismatch for $($trial.review_id)."
    }
}
if ($ValidateOnly) {
    Write-Host "Validated four ambient candidates. No audio was played."
    exit 0
}

Write-Host "Final four-clip ambient check. Keep the STM32 screen hidden."
Write-Host "Set Windows playback volume to 50 percent and keep it fixed."
Write-Host "Judge only whether each clip clearly sounds like the stated safe sound."
foreach ($trial in $trials) {
    if ((-not $Redo) -and $existing.ContainsKey($trial.review_id)) { continue }
    $audioPath = [IO.Path]::GetFullPath((Join-Path $repoRoot $trial.stimulus_path))
    while ($true) {
        Write-Host ""
        Write-Host "$($trial.review_id) | intended safe sound: $($trial.true_category)"
        $player = [System.Media.SoundPlayer]::new($audioPath)
        try { $player.Load(); $player.PlaySync() } finally { $player.Dispose() }
        $rep = (Read-Host "Representativeness [c=canonical, a=atypical-valid, x=wrong, r=replay, q=quit]").Trim().ToLowerInvariant()
        if ($rep -eq "r") { continue }
        if ($rep -eq "q") { exit 0 }
        if ($rep -notin @("c", "a", "x")) { continue }
        $aud = (Read-Host "Audibility [n=normal, q=quiet, l=loud/distorted]").Trim().ToLowerInvariant()
        if ($aud -notin @("n", "q", "l")) { continue }
        $note = Read-Host "Optional audio-only note"
        $existing[$trial.review_id] = [pscustomobject][ordered]@{
            candidate_order = [int]$trial.candidate_order
            review_id = $trial.review_id
            expected_class = $trial.expected_class
            true_category = $trial.true_category
            stimulus_sha256 = $trial.stimulus_sha256
            representativeness = @{ c = "canonical"; a = "atypical_valid"; x = "ambiguous_wrong" }[$rep]
            audibility = @{ n = "normal"; q = "quiet"; l = "loud_distorted" }[$aud]
            variant = "not_recorded"
            note = $note
        }
        @($existing.Values) | Sort-Object { [int]$_.candidate_order } |
            Export-Csv -LiteralPath $responsePath -NoTypeInformation -Encoding utf8
        break
    }
}
Write-Host "Ambient review complete. Tell Codex when it is done."
