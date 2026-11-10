# Mise à jour de Foulée à partir d'une archive foulee-<version>.zip.
# Remplace le programme ; ne touche ni à tes données (dossier data), ni à ta clé, ni à tes vues.
# Lancé par « Mettre-a-jour-Foulee.cmd » (on peut aussi glisser l'archive sur ce fichier).
param([string]$Archive)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Ask([string]$question) {
    $answer = Read-Host "$question [O/n]"
    return -not ($answer -match '^\s*[nN]')
}

function Get-FouleeVersion([string]$dir) {
    $file = Join-Path $dir "foulee\__init__.py"
    if (Test-Path $file) {
        $match = Select-String -Path $file -Pattern '__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
        if ($match) { return $match.Matches[0].Groups[1].Value }
    }
    return "?"
}

Write-Host ""
Write-Host "=== Mise à jour de Foulée ===" -ForegroundColor White
Write-Host "Dossier : $Root"

if (-not (Test-Path (Join-Path $Root ".venv"))) {
    Write-Host "Ce dossier n'est pas une installation de Foulée (pas de dossier .venv)." -ForegroundColor Yellow
    Write-Host "Lance Mettre-a-jour-Foulee.cmd depuis ton dossier Foulee habituel,"
    Write-Host "ou Installer-Foulee.cmd s'il s'agit d'une première installation."
    exit 1
}

# 1. L'archive : celle qu'on a glissée sur le script, sinon la plus récente du dossier Téléchargements
if (-not $Archive) {
    $downloads = $null
    try { $downloads = (New-Object -ComObject Shell.Application).NameSpace('shell:Downloads').Self.Path } catch { }
    if (-not $downloads) { $downloads = Join-Path $env:USERPROFILE "Downloads" }
    $latest = Get-ChildItem -Path $downloads -Filter "foulee*.zip" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) {
        Write-Host "Aucune archive foulee*.zip dans $downloads." -ForegroundColor Yellow
        Write-Host "Télécharge la nouvelle version, ou glisse l'archive sur Mettre-a-jour-Foulee.cmd."
        exit 1
    }
    $Archive = $latest.FullName
}
$Archive = (Resolve-Path -LiteralPath $Archive).Path
Write-Host "Archive : $Archive (du $((Get-Item -LiteralPath $Archive).LastWriteTime.ToString('dd/MM/yyyy HH:mm')))"

$temp = Join-Path $env:TEMP ("foulee-maj-" + [guid]::NewGuid().ToString("N"))
try {
    Unblock-File -LiteralPath $Archive -ErrorAction SilentlyContinue
    Expand-Archive -LiteralPath $Archive -DestinationPath $temp -Force
    $source = Join-Path $temp "Foulee"
    if (-not (Test-Path (Join-Path $source "foulee\__init__.py"))) {
        if (Test-Path (Join-Path $temp "foulee\__init__.py")) { $source = $temp }
        else { throw "Cette archive ne contient pas Foulée." }
    }
    $old = Get-FouleeVersion $Root
    $new = Get-FouleeVersion $source
    Write-Host "Version installée : $old    version de l'archive : $new"
    if (-not (Ask "Mettre à jour ?")) { Write-Host "Rien n'a changé."; exit 1 }

    # 2. Foulée ne doit pas tourner pendant la copie (interface, serveur de Claude Desktop, synchro)
    $running = @(Get-CimInstance Win32_Process -Filter "Name LIKE 'python%' OR Name = 'foulee.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'foulee' })
    if ($running.Count -gt 0) {
        Write-Host "Foulée tourne en ce moment ($($running.Count) processus : interface, Claude Desktop ou synchro)."
        if (Ask "Les arrêter pour la mise à jour ?") {
            $running | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            Start-Sleep -Seconds 2
        } else {
            Write-Warning "Je continue ; si un fichier est bloqué, relance la mise à jour après avoir fermé Foulée."
        }
    }

    # 3. Copie par-dessus : ajoute et remplace, ne supprime jamais rien (tes données ne sont pas dans l'archive)
    Write-Host "`nCopie des nouveaux fichiers..." -ForegroundColor Cyan
    robocopy "$source" "$Root" /E /XD data .venv __pycache__ .pytest_cache /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "La copie des fichiers a échoué (code robocopy $LASTEXITCODE)." }

    # 4. Bibliothèques : uv ne réinstalle que ce qui a changé
    $uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
    if (-not $uv) {
        $candidate = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
        if (Test-Path $candidate) { $uv = $candidate }
    }
    if ($uv) {
        Write-Host "Mise à jour des bibliothèques..." -ForegroundColor Cyan
        & $uv sync --no-dev
        if ($LASTEXITCODE -ne 0) { Write-Warning "La mise à jour des bibliothèques a échoué : ferme Foulée et Claude Desktop, puis relance la mise à jour." }
    } else {
        Write-Warning "uv introuvable : relance Installer-Foulee.cmd pour terminer la mise à jour."
    }
} finally {
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "=== Foulée est à jour (version $(Get-FouleeVersion $Root)) ===" -ForegroundColor Green
Write-Host "Relance Claude Desktop (clic droit sur son icône près de l'horloge, Quitter, puis rouvre-le)"
Write-Host "et l'interface (raccourci Foulée) pour profiter de la nouvelle version."
