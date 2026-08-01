# Hazard candidate data acquisition

The official FSD50K ground truth and metadata have already been downloaded and
verified under the local `ml-workspace/datasets/FSD50K-audit` directory. They
are sufficient to audit class counts, source IDs, titles, uploaders, and
per-clip Creative Commons license URLs without downloading the audio.

The next host-side experiment needs development audio for `Screaming` and
`Gunshot_and_gunfire`. The official FSD50K development archive is a split ZIP:

- download: 18,412,790,687 bytes (17.15 GiB);
- six archive parts;
- expected extracted development WAV files: 40,966;
- recommended free space before download and extraction: 45 GiB.

The repository script downloads with resume support, verifies the exact Zenodo
file sizes and MD5 checksums, and extracts with the locally installed WinRAR:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\ml\acquire_fsd50k.ps1
```

The evaluation archive is deliberately excluded at this stage so its clips
remain untouched. It can later be acquired with `-IncludeEvaluation` after the
candidate taxonomy and thresholds are frozen.

Do not copy the audio into Git. Only manifests, per-clip provenance, metrics,
and hashes belong in the repository.
