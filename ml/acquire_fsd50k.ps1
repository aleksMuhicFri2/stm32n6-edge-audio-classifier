[CmdletBinding()]
param(
    [string]$Destination,
    [switch]$IncludeEvaluation,
    [switch]$DownloadOnly
)

$ErrorActionPreference = 'Stop'

if (-not $Destination) {
    $Destination = [IO.Path]::GetFullPath(
        (Join-Path $PSScriptRoot '..\..\ml-workspace\datasets\FSD50K'))
}
$Destination = [IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Force -Path $Destination | Out-Null

$dev = @(
    @{Name='FSD50K.dev_audio.z01'; Size=3221225472; Md5='faa7cf4cc076fc34a44a479a5ed862a3'},
    @{Name='FSD50K.dev_audio.z02'; Size=3221225472; Md5='8f9b66153e68571164fb1315d00bc7bc'},
    @{Name='FSD50K.dev_audio.z03'; Size=3221225472; Md5='1196ef47d267a993d30fa98af54b7159'},
    @{Name='FSD50K.dev_audio.z04'; Size=3221225472; Md5='d088ac4e11ba53daf9f7574c11cccac9'},
    @{Name='FSD50K.dev_audio.z05'; Size=3221225472; Md5='81356521aa159accd3c35de22da28c7f'},
    @{Name='FSD50K.dev_audio.zip'; Size=2306663327; Md5='c480d119b8f7a7e32fdb58f3ea4d6c5a'}
)
$eval = @(
    @{Name='FSD50K.eval_audio.z01'; Size=3221225472; Md5='3090670eaeecc013ca1ff84fe4442aeb'},
    @{Name='FSD50K.eval_audio.zip'; Size=3037675767; Md5='6fa47636c3a3ad5c7dfeba99f2637982'}
)
$files = @($dev | ForEach-Object { $_ })
if ($IncludeEvaluation) {
    $files += @($eval | ForEach-Object { $_ })
}

$archiveBytes = [int64]0
foreach ($file in $files) {
    $archiveBytes += [int64]$file.Size
}
$drive = [IO.DriveInfo]::new(([IO.Path]::GetPathRoot($Destination)))
$requiredFree = if ($IncludeEvaluation) { 60GB } else { 45GB }
if ($drive.AvailableFreeSpace -lt $requiredFree) {
    throw ('Insufficient free space. Required at least {0:N1} GiB; available {1:N1} GiB.' -f `
        ($requiredFree / 1GB), ($drive.AvailableFreeSpace / 1GB))
}

Write-Host ('Destination: {0}' -f $Destination)
Write-Host ('Archive download: {0:N2} GiB' -f ($archiveBytes / 1GB))
Write-Host ('Available disk space: {0:N2} GiB' -f ($drive.AvailableFreeSpace / 1GB))

foreach ($file in $files) {
    $target = Join-Path $Destination $file.Name
    $url = 'https://zenodo.org/api/records/4060432/files/{0}/content' -f $file.Name
    if ((Test-Path $target) -and
        ((Get-Item $target).Length -eq $file.Size) -and
        ((Get-FileHash $target -Algorithm MD5).Hash.ToLowerInvariant() -eq $file.Md5)) {
        Write-Host ('Verified existing {0}' -f $file.Name)
        continue
    }

    Write-Host ('Downloading {0} ({1:N2} GiB)...' -f $file.Name, ($file.Size / 1GB))
    $attempt = 0
    while (-not (Test-Path $target) -or (Get-Item $target).Length -lt $file.Size) {
        $attempt++
        if ($attempt -gt 60) {
            throw "Download did not complete after 60 resumable connections: $($file.Name)"
        }
        $beforeBytes = if (Test-Path $target) { (Get-Item $target).Length } else { 0 }
        if ($beforeBytes -gt $file.Size) {
            throw "Partial file exceeds official size: $($file.Name)"
        }
        Write-Host ('Connection {0}; resuming at {1:N2} GiB' -f $attempt, ($beforeBytes / 1GB))
        & curl.exe -L --fail --connect-timeout 30 --max-time 300 `
            --speed-limit 1024 --speed-time 60 --continue-at - `
            --output $target $url
        $afterBytes = if (Test-Path $target) { (Get-Item $target).Length } else { 0 }
        if ($afterBytes -gt $file.Size) {
            throw "Downloaded file exceeds official size: $($file.Name)"
        }
        if ($LASTEXITCODE -ne 0) {
            Write-Warning ('Connection ended with curl exit {0}; preserved {1:N2} GiB and will resume.' -f `
                $LASTEXITCODE, ($afterBytes / 1GB))
        }
        if ($afterBytes -le $beforeBytes) {
            Start-Sleep -Seconds 10
        }
    }
    if ((Get-Item $target).Length -ne $file.Size) {
        throw "Size verification failed: $($file.Name)"
    }
    $actualMd5 = (Get-FileHash $target -Algorithm MD5).Hash.ToLowerInvariant()
    if ($actualMd5 -ne $file.Md5) {
        throw "MD5 verification failed: $($file.Name)"
    }
    Write-Host ('Verified {0}' -f $file.Name)
}

if ($DownloadOnly) {
    Write-Host 'Download and checksum verification complete; extraction skipped.'
    exit 0
}

$winRar = 'C:\Program Files\WinRAR\WinRAR.exe'
if (-not (Test-Path $winRar)) {
    throw 'WinRAR is required to extract the split ZIP archive but was not found.'
}

foreach ($archive in @('FSD50K.dev_audio.zip', 'FSD50K.eval_audio.zip')) {
    $archivePath = Join-Path $Destination $archive
    if (-not (Test-Path $archivePath)) {
        continue
    }
    Write-Host ('Extracting {0}...' -f $archive)
    $extract = Start-Process -FilePath $winRar `
        -ArgumentList @('x', '-inul', '-y', $archivePath, ($Destination.TrimEnd('\') + '\')) `
        -WindowStyle Hidden `
        -Wait `
        -PassThru
    if ($extract.ExitCode -ne 0) {
        throw "Extraction failed: $archive"
    }
}

$devAudio = Join-Path $Destination 'FSD50K.dev_audio'
if (-not (Test-Path $devAudio)) {
    throw 'Development audio directory was not created.'
}
$devCount = (Get-ChildItem $devAudio -Filter '*.wav' -File).Count
if ($devCount -ne 40966) {
    throw "Expected 40966 development WAV files after extraction; found $devCount."
}

if ($IncludeEvaluation) {
    $evalAudio = Join-Path $Destination 'FSD50K.eval_audio'
    $evalCount = (Get-ChildItem $evalAudio -Filter '*.wav' -File).Count
    if ($evalCount -ne 10231) {
        throw "Expected 10231 evaluation WAV files after extraction; found $evalCount."
    }
}

Write-Host ('FSD50K acquisition complete. Development WAV files: {0}' -f $devCount)
