$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "run_transient_event_review.ps1") `
    -ReviewDirectory "experiments\patch_balanced_augmentation_review_v3"

Write-Host "Review responses were saved. Tell Codex that the review is done."
