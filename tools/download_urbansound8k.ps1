# Prenese uradni arhiv UrbanSound8K in pred razširitvijo preveri kontrolno vsoto.
# Zbirka ostane zunaj repozitorija; v Gitu so shranjeni samo njeni manifesti.
param(
    [string]$DatasetRoot = '',
    [string]$ArchivePath = ''
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$projectRoot = (Resolve-Path (Join-Path $repoRoot '..')).Path
$datasetsRoot = Join-Path $projectRoot 'ml-workspace\datasets'
if (-not $DatasetRoot) {
    $DatasetRoot = Join-Path $datasetsRoot 'UrbanSound8K'
}
if (-not $ArchivePath) {
    $ArchivePath = Join-Path $datasetsRoot 'downloads\UrbanSound8K.tar.gz'
}

$expectedMetadata = Join-Path $DatasetRoot 'metadata\UrbanSound8K.csv'
$expectedMd5 = '9aa69802bbf37fb986f71ec1483a196e'
$downloadUrl = 'https://zenodo.org/records/1203745/files/UrbanSound8K.tar.gz?download=1'

if (Test-Path -LiteralPath $expectedMetadata) {
    Write-Output "UrbanSound8K is already available at $DatasetRoot"
    exit 0
}

$archiveDirectory = Split-Path -Parent $ArchivePath
New-Item -ItemType Directory -Force $datasetsRoot, $archiveDirectory | Out-Null

Write-Output 'Downloading the official 6 GB UrbanSound8K archive from Zenodo.'
Write-Output 'The download is resumable, so this command may be run again if interrupted.'
& curl.exe `
    --location `
    --fail `
    --retry 5 `
    --retry-delay 5 `
    --continue-at - `
    --output $ArchivePath `
    $downloadUrl
if ($LASTEXITCODE -ne 0) {
    throw "UrbanSound8K download failed with exit code $LASTEXITCODE"
}

$actualMd5 = (Get-FileHash -LiteralPath $ArchivePath -Algorithm MD5).Hash.ToLowerInvariant()
if ($actualMd5 -ne $expectedMd5) {
    throw "Archive checksum mismatch. Expected $expectedMd5 but got $actualMd5."
}

Write-Output 'Checksum verified. Inspecting archive paths before extraction.'
$entries = & tar.exe -tzf $ArchivePath
if ($LASTEXITCODE -ne 0) {
    throw 'Could not inspect the UrbanSound8K archive.'
}
$unsafeEntry = $entries | Where-Object {
    $_ -match '^[\\/]' -or $_ -match '(^|[\\/])\.\.([\\/]|$)'
} | Select-Object -First 1
if ($unsafeEntry) {
    throw "Archive contains an unsafe path: $unsafeEntry"
}

Write-Output "Extracting UrbanSound8K under $datasetsRoot"
& tar.exe -xzf $ArchivePath -C $datasetsRoot
if ($LASTEXITCODE -ne 0) {
    throw "UrbanSound8K extraction failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath $expectedMetadata)) {
    throw "Extraction completed but expected metadata is missing: $expectedMetadata"
}

$gunshotCount = (
    Import-Csv -LiteralPath $expectedMetadata |
        Where-Object { $_.class -eq 'gun_shot' } |
        Measure-Object
).Count
$audioFiles = (
    Get-ChildItem -LiteralPath (Join-Path $DatasetRoot 'audio') -Recurse -Filter '*.wav' -File |
        Measure-Object
).Count

[pscustomobject]@{
    dataset_root = $DatasetRoot
    archive_path = $ArchivePath
    archive_md5 = $actualMd5
    audio_files = $audioFiles
    gunshot_clips = $gunshotCount
    status = 'downloaded_verified_extracted'
} | ConvertTo-Json
