# Construit l'installateur Windows de Foulée : build\out\Foulee-Setup-<version>.exe + SHA256SUMS.txt
#
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#
# Il faut uv (https://docs.astral.sh/uv/) et Inno Setup 6.3 ou plus récent (iscc).
# Étapes :
#  1. un Python autonome (python-build-standalone, celui qu'installe uv), copié dans le programme ;
#  2. Foulée et ses bibliothèques, aux versions exactes du fichier uv.lock (empreintes vérifiées) ;
#  3. Foulee.exe (pythonw.exe renommé, avec l'icône de Foulée) et Foulee.ico ;
#  4. l'installateur (Inno Setup) et ses empreintes SHA-256.

param(
    [string]$Version = "",
    [string]$Iscc = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
# Accents corrects entre Python et PowerShell
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
$Build = Join-Path $Root "build"
$Stage = Join-Path $Build "stage"
$Out = Join-Path $Build "out"

function Step($text) { Write-Host "`n=== $text" -ForegroundColor Cyan }
function Run($exe, [string[]]$arguments) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "« $exe $($arguments -join ' ') » a échoué (code $LASTEXITCODE)" }
}

if (-not $Version) {
    $Version = (Select-String -Path (Join-Path $Root "foulee\__init__.py") -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
}
if ($Version -notmatch '^(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?$') { throw "Version illisible : $Version" }
# Version numérique pour les propriétés du fichier (0.4.0b1 -> 0.4.0.1 ; 0.4.0 -> 0.4.0.0)
$Numeric = "$($Matches[1]).$($Matches[2]).$($Matches[3]).$(if ($Matches[5]) { $Matches[5] } else { 0 })"
Write-Host "Foulée $Version ($Numeric)"

if (Test-Path $Build) { Remove-Item -Recurse -Force $Build }
New-Item -ItemType Directory -Force $Stage, $Out | Out-Null

Step "1. Python autonome"
$PyVersion = (Get-Content (Join-Path $Root ".python-version") -Raw).Trim()
Run uv @("python", "install", $PyVersion, "--install-dir", (Join-Path $Build "py"))
$PyHome = Get-ChildItem (Join-Path $Build "py") -Directory |
    Where-Object { $_.Name -match '^cpython-\d+\.\d+\.\d+-windows-x86_64' -and -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) } |
    Select-Object -First 1
if (-not $PyHome) { throw "Python autonome introuvable dans $Build\py" }
Copy-Item $PyHome.FullName (Join-Path $Stage "python") -Recurse
$Python = Join-Path $Stage "python\python.exe"
Remove-Item (Join-Path $Stage "python\Lib\EXTERNALLY-MANAGED") -ErrorAction SilentlyContinue
Run $Python @("--version")

Step "2. Foulée et ses bibliothèques (uv.lock)"
$Requirements = Join-Path $Build "requirements.txt"
Push-Location $Root
try {
    Run uv @("export", "--frozen", "--no-dev", "--no-emit-project", "--format", "requirements.txt", "-o", $Requirements)
    Run uv @("build", "--wheel", "--out-dir", (Join-Path $Build "dist"))
} finally { Pop-Location }
$Wheel = Get-ChildItem (Join-Path $Build "dist") -Filter "foulee-*.whl" | Select-Object -First 1
Run uv @("pip", "install", "--python", $Python, "--break-system-packages", "--no-cache", "--require-hashes", "-r", $Requirements)
Run uv @("pip", "install", "--python", $Python, "--break-system-packages", "--no-cache", "--no-deps", $Wheel.FullName)
# Ce qui ne sert pas à Foulée : tests, IDLE, lanceurs de pip…
foreach ($useless in @("Lib\test", "Lib\idlelib", "Lib\tkinter\test", "Lib\lib2to3\tests", "Lib\ensurepip", "Scripts")) {
    Remove-Item (Join-Path $Stage "python\$useless") -Recurse -Force -ErrorAction SilentlyContinue
}
# Bytecode compilé d'avance : premier démarrage rapide (un fichier qui ne compile pas n'est pas grave)
& $Python -m compileall -q -j 0 (Join-Path $Stage "python\Lib") | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Warning "compileall : certains fichiers n'ont pas été précompilés" }
$Installed = & $Python -c "import foulee, foulee.config as c; print(foulee.__version__, c.is_packaged())"
if ($Installed -ne "$Version True") { throw "Contrôle de l'installation raté : « $Installed »" }

Step "3. Foulee.exe et son icône"
Run $Python @("-m", "foulee.icon", (Join-Path $Stage "Foulee.ico"))
$Exe = Join-Path $Stage "python\Foulee.exe"
Copy-Item (Join-Path $Stage "python\pythonw.exe") $Exe
$Rcedit = Join-Path $Build "rcedit-x64.exe"
try {
    Invoke-WebRequest "https://github.com/electron/rcedit/releases/download/v2.0.0/rcedit-x64.exe" -OutFile $Rcedit
    Run $Rcedit @($Exe, "--set-icon", (Join-Path $Stage "Foulee.ico"),
        "--set-version-string", "FileDescription", "Foulée",
        "--set-version-string", "ProductName", "Foulée",
        "--set-version-string", "CompanyName", "Foulée",
        "--set-version-string", "OriginalFilename", "Foulee.exe",
        "--set-version-string", "InternalName", "Foulee",
        "--set-product-version", $Version,
        "--set-file-version", $Numeric)
} catch {
    Write-Warning "Icône de Foulee.exe non appliquée ($_) : il garde celle de Python."
}

Step "4. Installateur"
if (-not $Iscc) {
    $Iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
              "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Iscc) { throw "Inno Setup 6 (ISCC.exe) introuvable" }
Run $Iscc @("/Qp", "/DAppVersion=$Version", "/DNumericVersion=$Numeric", "/DStageDir=$Stage", "/DOutputDir=$Out",
    (Join-Path $PSScriptRoot "foulee.iss"))
$Setup = Join-Path $Out "Foulee-Setup-$Version.exe"
$Hash = (Get-FileHash $Setup -Algorithm SHA256).Hash.ToLowerInvariant()
# Format de sha256sum : « empreinte  nom » (vérifiable avec sha256sum -c ou Get-FileHash)
[IO.File]::WriteAllText((Join-Path $Out "SHA256SUMS.txt"), "$Hash  Foulee-Setup-$Version.exe`n")
$Size = [math]::Round((Get-Item $Setup).Length / 1MB, 1)
Write-Host "`nPrêt : $Setup ($Size Mo)`nSHA-256 : $Hash" -ForegroundColor Green
