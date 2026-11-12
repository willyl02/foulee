# Installation de Foulée (Windows 10/11, sans droits administrateur)
# Lancé par « Installer-Foulee.cmd ». Chaque étape demande ton accord.

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Ask([string]$question) {
    $answer = Read-Host "$question [O/n]"
    return -not ($answer -match '^\s*[nN]')
}

Write-Host ""
Write-Host "=== Installation de Foulée ===" -ForegroundColor White
Write-Host "Dossier : $Root"
Write-Host ""

if ($Root -match "OneDrive") {
    Write-Warning "Ce dossier est dans OneDrive : tes données de santé y seraient copiées dans le cloud."
    Write-Warning "Conseil : déplace le dossier Foulee vers C:\Users\$env:USERNAME\Foulee puis relance l'installation."
    if (-not (Ask "Continuer quand même ?")) { exit 1 }
}

# 1. uv : installe Python et les dépendances dans le dossier du projet (.venv)
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
    $candidate = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
    if (Test-Path $candidate) { $uv = $candidate }
}
if (-not $uv) {
    Write-Host "uv (l'outil qui installe Python et les bibliothèques) n'est pas encore présent."
    if (-not (Ask "L'installer maintenant depuis astral.sh ?")) { Write-Host "Installation annulée."; exit 1 }
    powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
    if (-not (Test-Path $uv)) { throw "uv introuvable après installation : ouvre une nouvelle fenêtre et relance." }
}
Write-Host "`n[1/6] Installation de Python et des bibliothèques (une à deux minutes la première fois)..." -ForegroundColor Cyan
& $uv sync --no-dev
if ($LASTEXITCODE -ne 0) { throw "L'installation des bibliothèques a échoué (voir les messages ci-dessus)." }

$Foulee = Join-Path $Root ".venv\Scripts\foulee.exe"
$PythonW = Join-Path $Root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $PythonW)) { $PythonW = Join-Path $Root ".venv\Scripts\python.exe" }

Write-Host "`n[2/6] Base de démonstration (données fictives, séparées des tiennes)..." -ForegroundColor Cyan
& $Foulee demo

Write-Host "`n[3/6] Ta clé API Garmin" -ForegroundColor Cyan
if (Ask "Enregistrer ta clé maintenant et lancer le premier import ?") {
    & $Foulee setup
} else {
    Write-Host "Plus tard : double-clique sur Configurer-cle-Garmin.cmd."
}

Write-Host "`n[4/6] Claude Desktop" -ForegroundColor Cyan
if (Ask "Ajouter Foulée aux outils de Claude Desktop (sauvegarde de ta configuration avant modification) ?") {
    & $Foulee claude-config --ecrire
}

Write-Host "`n[5/6] Raccourci sur le Bureau" -ForegroundColor Cyan
if (Ask "Créer le raccourci « Foulée » sur le Bureau ?") {
    $shell = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath("Desktop")
    $link = $shell.CreateShortcut((Join-Path $desktop "Foulée.lnk"))
    $link.TargetPath = Join-Path $Root "Ouvrir-Foulee.cmd"
    $link.WorkingDirectory = $Root
    $link.WindowStyle = 7
    $link.Description = "Ouvrir l'interface Foulée"
    $link.IconLocation = "$env:SystemRoot\System32\SHELL32.dll,13"
    $link.Save()
    Write-Host "Raccourci créé."
}

Write-Host "`n[6/6] Synchro automatique" -ForegroundColor Cyan
if (Ask "Synchroniser automatiquement (tâche planifiée Windows, invisible ; toutes les 3 heures par défaut) ?") {
    try {
        # --auto : seulement les sources dont la synchro est due, au rythme choisi dans les Réglages (3 heures par défaut)
        $action = New-ScheduledTaskAction -Execute $PythonW -Argument "-m foulee sync --quiet --auto" -WorkingDirectory $Root
        # Tous les jours à 5 h 17, puis toutes les 15 minutes pendant 23 h 45 (motif fiable sous Windows PowerShell 5.1)
        $trigger = New-ScheduledTaskTrigger -Daily -At "05:17"
        $trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "05:17" -RepetitionInterval (New-TimeSpan -Minutes 15) `
            -RepetitionDuration (New-TimeSpan -Hours 23 -Minutes 45)).Repetition
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
        Register-ScheduledTask -TaskName "Foulee - synchro" -Action $action -Trigger $trigger -Settings $settings `
            -Description "Synchronise Foulée (Garmin, Withings) au rythme choisi dans ses Réglages" -Force | Out-Null
        Write-Host "Tâche « Foulee - synchro » créée (visible dans le Planificateur de tâches)."
    } catch {
        Write-Warning "Création de la tâche impossible : $($_.Exception.Message)"
        Write-Warning "Tu pourras toujours synchroniser depuis l'interface ou en demandant à Claude."
    }
}

Write-Host ""
Write-Host "=== C'est prêt ===" -ForegroundColor Green
Write-Host "Interface : raccourci « Foulée » sur le Bureau (ou Ouvrir-Foulee.cmd)."
Write-Host "Démo      : Ouvrir-Foulee-demo.cmd"
Write-Host "Claude    : relance Claude Desktop ; Foulée apparaît dans Paramètres → Développeur (une vingtaine de secondes la première fois)."
Write-Host "Mise à jour : télécharge la nouvelle archive (foulee-<version>.zip) puis double-clique sur Mettre-a-jour-Foulee.cmd."
Write-Host ""
