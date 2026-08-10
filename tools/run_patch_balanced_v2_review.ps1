$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

& (Join-Path $PSScriptRoot "run_transient_event_review.ps1") `
    -ReviewDirectory "experiments\patch_balanced_augmentation_review_v2"

Write-Host "Review responses were saved. Tell Codex that the review is done."
