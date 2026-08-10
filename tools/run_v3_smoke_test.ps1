param(
    [switch]$Redo,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$manifestPath = Join-Path $repoRoot "experiments\v3_smoke_test\manifest.csv"
$responsePath = Join-Path $repoRoot "experiments\v3_smoke_test\responses.csv"

if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Smoke-test manifest is missing. Run ml\prepare_v3_smoke_test.py first."
}

$trials = @(Import-Csv -LiteralPath $manifestPath | Sort-Object { [int]$_.order })
$existing = @{}
if (Test-Path -LiteralPath $responsePath) {
    foreach ($row in Import-Csv -LiteralPath $responsePath) {
        $existing[$row.smoke_id] = $row
    }
}

foreach ($trial in $trials) {
    $audioPath = [IO.Path]::GetFullPath((Join-Path $repoRoot $trial.stimulus_path))
    if (-not (Test-Path -LiteralPath $audioPath -PathType Leaf)) {
        throw "Missing smoke-test audio: $audioPath"
    }
    $actualHash = (Get-FileHash -LiteralPath $audioPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $trial.stimulus_sha256) {
        throw "Smoke-test audio hash mismatch: $audioPath"
    }
}

if ($ValidateOnly) {
    Write-Host "Validated $($trials.Count) V3 smoke-test clips. No audio was played."
    exit 0
}

$displayNames = @{
    speech = "ČLOVEŠKI GOVOR"
    siren = "SIRENA"
    dog_bark = "PASJI LAJEŽ"
    glass_breaking = "RAZBITJE STEKLA"
    gunshot_gunfire = "STREL"
    thunderstorm = "NEVIHTA"
}
$labelAliases = @{
    human_speech = "speech"
    speech = "speech"
    emergency_siren = "siren"
    siren = "siren"
    dog_bark = "dog_bark"
    glass_breaking = "glass_breaking"
    gunshot = "gunshot_gunfire"
    gunshot_gunfire = "gunshot_gunfire"
    thunderstorm = "thunderstorm"
}

Write-Host "Funkcionalni preizkus YAMNet-1024 V3: $($trials.Count) posnetkov."
Write-Host "To ni končno vrednotenje pravilnosti. Rezultat preberi z zaslona plošče."
Write-Host "Med celotnim preizkusom ohrani enako udobno glasnost in razdaljo."
$volumePercent = (Read-Host "Glasnost sistema Windows v odstotkih (lahko pustiš prazno)").Trim()
$distanceCm = (Read-Host "Razdalja med zvočnikom in ploščo v centimetrih (lahko pustiš prazno)").Trim()
$idleAlert = (Read-Host "Ali je v približno 20 sekundah tišine nastal lažni alarm? [da/ne/ni preizkušeno]").Trim()

foreach ($trial in $trials) {
    if ((-not $Redo) -and $existing.ContainsKey($trial.smoke_id)) {
        Write-Host "Skipping completed $($trial.smoke_id)."
        continue
    }

    $audioPath = [IO.Path]::GetFullPath((Join-Path $repoRoot $trial.stimulus_path))
    while ($true) {
        Write-Host ""
        Write-Host "[$($trial.order)/$($trials.Count)] $($trial.smoke_id) | pričakovano: $($displayNames[$trial.expected_class])"
        Read-Host "Pritisni Enter za predvajanje"
        $player = [System.Media.SoundPlayer]::new($audioPath)
        try {
            $player.Load()
            $player.PlaySync()
        }
        finally {
            $player.Dispose()
        }

        $detected = (Read-Host "Glavna zaznana oznaka; r za ponovitev ali q za konec").Trim()
        if ($detected.ToLowerInvariant() -eq "r") { continue }
        if ($detected.ToLowerInvariant() -eq "q") {
            Write-Host "Stopped. Run the same command to resume."
            exit 0
        }
        $confidence = (Read-Host "Najvišji prikazani odstotek zaupanja (0-100; prazno ob zgrešeni zaznavi)").Trim()
        if ($confidence -and (($confidence -as [int]) -eq $null -or [int]$confidence -lt 0 -or [int]$confidence -gt 100)) {
            Write-Host "Invalid confidence; replaying the trial."
            continue
        }
        $note = Read-Host "Neobvezna opomba"
        # Accept a label copied together with its displayed percentage, for
        # example "glass breaking 98%".
        $labelOnly = ($detected.ToLowerInvariant() -replace '\s+\d+\s*%?\s*$', '').Trim()
        $normalizedDetected = $labelOnly.Replace(" ", "_")
        $internalDetected = if ($labelAliases.ContainsKey($normalizedDetected)) {
            $labelAliases[$normalizedDetected]
        } else {
            $normalizedDetected
        }
        $correct = $internalDetected -eq $trial.expected_class
        $row = [pscustomobject]@{
            recorded_at = (Get-Date).ToString("o")
            smoke_id = $trial.smoke_id
            expected_class = $trial.expected_class
            detected_label = $detected
            confidence_percent = $confidence
            correct = $correct
            stimulus_sha256 = $trial.stimulus_sha256
            volume_percent = $volumePercent
            distance_cm = $distanceCm
            idle_false_alert = $idleAlert
            note = $note
        }
        $existing[$trial.smoke_id] = $row
        @($existing.Values | Sort-Object smoke_id) |
            Export-Csv -LiteralPath $responsePath -NoTypeInformation -Encoding UTF8
        Write-Host "Saved $($trial.smoke_id)."
        break
    }
}

Write-Host "Preizkus je končan. Napiši Codexu, da si končal."
