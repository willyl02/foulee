# Essai complet de l'installateur sur un Windows propre (GitHub Actions) :
# installation silencieuse, relance automatique, interface, Claude (serveur MCP), démarrage avec
# Windows, mise à jour par-dessus l'application ouverte, puis désinstallation.
#
#   pwsh -File packaging\smoke-test.ps1 [-Setup build\out\Foulee-Setup-x.exe]

param([string]$Setup = "")

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
# Accents corrects entre Python et PowerShell
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Setup) { $Setup = (Get-ChildItem (Join-Path $Root "build\out") -Filter "Foulee-Setup-*.exe" | Select-Object -First 1).FullName }
$Expected = [regex]::Match((Split-Path $Setup -Leaf), 'Foulee-Setup-(.+)\.exe').Groups[1].Value
$Dir = Join-Path $env:LOCALAPPDATA "Programs\Foulee"
$Python = Join-Path $Dir "python\python.exe"
$Base = Join-Path $env:LOCALAPPDATA "Foulee"
$Logs = Join-Path $env:RUNNER_TEMP "foulee-essai"
$RunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
New-Item -ItemType Directory -Force $Logs | Out-Null
$script:Step = 0

function Ok($text) { Write-Host "  OK  $text" -ForegroundColor Green }
function Step($text) { $script:Step++; Write-Host "`n[$script:Step] $text" -ForegroundColor Cyan }
function Fail($text) {
    Write-Host "::error title=Essai de l'installateur::$text"
    foreach ($file in @((Join-Path $Base "donnees\logs\app.log"), (Join-Path $Logs "installation-1.log"), (Join-Path $Logs "installation-2.log"))) {
        if (Test-Path $file) { Write-Host "`n--- $file"; Get-Content $file -Tail 60 }
    }
    throw $text
}

# Attend la fin du processus lui-même, pas celle de ce qu'il lance (l'installateur relance Foulée)
function Run-Wait($file, [string[]]$arguments) {
    $process = Start-Process $file -ArgumentList $arguments -PassThru
    $null = $process.Handle  # sans ça, le code de sortie se perd
    $process.WaitForExit()
    return $process.ExitCode
}

function Install($name) {
    $log = Join-Path $Logs "$name.log"
    $code = Run-Wait $Setup @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=`"$log`"")
    if ($code -ne 0) { Fail "installation ($name) : code $code" }
}

function App-Info {
    $file = Join-Path $Base "app.json"
    if (-not (Test-Path $file)) { return $null }
    try { return Get-Content $file -Raw | ConvertFrom-Json } catch { return $null }
}

function Wait-App($notPid, $seconds = 90) {
    $end = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $end) {
        $info = App-Info
        if ($info -and $info.pid -ne $notPid) {
            try {
                $boot = Invoke-RestMethod "http://127.0.0.1:$($info.port)/api/bootstrap" -TimeoutSec 5
                return @{ Info = $info; Boot = $boot }
            } catch { }
        }
        Start-Sleep -Milliseconds 500
    }
    Fail "l'application ne répond pas (attendu : un nouveau processus)"
}

Step "Installation silencieuse de $(Split-Path $Setup -Leaf)"
Install "installation-1"
foreach ($file in @("python\Foulee.exe", "python\python.exe", "Foulee.ico", "unins000.exe")) {
    if (-not (Test-Path (Join-Path $Dir $file))) { Fail "fichier manquant : $file" }
}
Ok "programme dans $Dir"
$Version = (& $Python -m foulee --version).Trim()
if ($Version -ne "Foulée $Expected") { Fail "version : « $Version » au lieu de « Foulée $Expected »" }
Ok $Version
$Packaged = (& $Python -c "import foulee.config as c; print(c.is_packaged(), c.default_data_dir())").Trim()
if ($Packaged -ne "True $Base\donnees") { Fail "mode installé : $Packaged" }
Ok "données par défaut : $Base\donnees"
$Startup = (Get-ItemProperty $RunKey -Name Foulee -ErrorAction SilentlyContinue).Foulee
if (-not $Startup -or $Startup -notlike "*Foulee.exe*--demarrage*") { Fail "lancement à l'ouverture de session absent : $Startup" }
Ok "lancement à l'ouverture de session : $Startup"
if (-not (Test-Path (Join-Path ([Environment]::GetFolderPath("Desktop")) "Foulée.lnk"))) { Fail "raccourci du Bureau absent" }
Ok "raccourci sur le Bureau"

Step "Relance automatique après l'installation silencieuse"
$first = Wait-App 0
$boot = $first.Boot
if ($boot.version -ne $Expected -or $boot.installation -ne "exe" -or -not $boot.application) {
    Fail "bootstrap inattendu : version=$($boot.version) installation=$($boot.installation) application=$($boot.application)"
}
Ok "interface sur le port $($first.Info.port) (processus $($first.Info.pid)), installation « exe »"
$appProcess = Get-Process -Id $first.Info.pid
if ($appProcess.Path -ne (Join-Path $Dir "python\Foulee.exe")) { Fail "processus inattendu : $($appProcess.Path)" }
Ok "processus Foulee.exe"
$url = "http://127.0.0.1:$($first.Info.port)"
$majInfo = Invoke-RestMethod "$url/api/maj"
if ($majInfo.mode -ne "exe") { Fail "mode de mise à jour : $($majInfo.mode)" }
Ok "mises à jour par GitHub (canal $($majInfo.canal))"

Step "Démarrage avec Windows depuis les Réglages"
$headers = @{ "X-Foulee" = "1" }
$off = Invoke-RestMethod "$url/api/app" -Method Put -Headers $headers -ContentType "application/json" -Body '{"demarrage_windows": false}'
if ($off.demarrage_windows -or (Get-ItemProperty $RunKey -Name Foulee -ErrorAction SilentlyContinue)) { Fail "désactivation sans effet" }
$on = Invoke-RestMethod "$url/api/app" -Method Put -Headers $headers -ContentType "application/json" -Body '{"demarrage_windows": true}'
if (-not $on.demarrage_windows) { Fail "réactivation sans effet" }
Ok "désactivé puis réactivé"

Step "Claude Desktop : serveur MCP"
$mcp = & $Python (Join-Path $PSScriptRoot "mcp_check.py") $Python 2>&1
if ($LASTEXITCODE -ne 0) { Write-Host ($mcp | Out-String); Fail "serveur MCP" }
Ok ($mcp | Select-Object -Last 1)

Step "Mise à jour par-dessus l'application ouverte"
Install "installation-2"
$second = Wait-App $first.Info.pid
if (Get-Process -Id $first.Info.pid -ErrorAction SilentlyContinue) { Fail "l'ancienne application tourne encore" }
Ok "ancienne application fermée, nouvelle relancée (processus $($second.Info.pid))"
$Startup = (Get-ItemProperty $RunKey -Name Foulee -ErrorAction SilentlyContinue).Foulee
if (-not $Startup) { Fail "la mise à jour a perdu le lancement à l'ouverture de session" }
Ok "réglages conservés"

Step "Désinstallation silencieuse"
$uninstallCode = Run-Wait (Join-Path $Dir "unins000.exe") @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")
$end = (Get-Date).AddSeconds(90)
while ((Test-Path (Join-Path $Dir "python")) -and (Get-Date) -lt $end) { Start-Sleep -Milliseconds 500 }
if (Test-Path (Join-Path $Dir "python")) { Fail "le programme est encore là après désinstallation" }
Ok "programme retiré (code $uninstallCode)"
if (Get-Process -Id $second.Info.pid -ErrorAction SilentlyContinue) { Fail "l'application tourne encore" }
Ok "application fermée"
if (Get-ItemProperty $RunKey -Name Foulee -ErrorAction SilentlyContinue) { Fail "lancement à l'ouverture de session encore présent" }
Ok "lancement à l'ouverture de session retiré"
if (-not (Test-Path (Join-Path $Base "donnees\foulee.db"))) { Fail "les données auraient dû être conservées" }
Ok "données conservées dans $Base"

$size = [math]::Round((Get-Item $Setup).Length / 1MB, 1)
Write-Host "::notice title=Installateur::$(Split-Path $Setup -Leaf) ($size Mo) : installation, relance, MCP, mise à jour et désinstallation OK"
Write-Host "`nEssai réussi." -ForegroundColor Green
