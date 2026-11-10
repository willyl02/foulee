# Désinstallation de Foulée : retire la tâche planifiée, le raccourci, l'entrée Claude Desktop
# et (si tu le confirmes) la clé API. Tes données restent dans le dossier « data ».

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Unregister-ScheduledTask -TaskName "Foulee - synchro" -Confirm:$false -ErrorAction SilentlyContinue
$desktop = [Environment]::GetFolderPath("Desktop")
Remove-Item (Join-Path $desktop "Foulée.lnk") -ErrorAction SilentlyContinue

$Foulee = Join-Path $Root ".venv\Scripts\foulee.exe"
if (Test-Path $Foulee) {
    # Foulée sait où chaque version de Claude Desktop range sa configuration (sauvegarde avant modification)
    & $Foulee claude-config --retirer
} else {
    $configs = @()
    $configs += Get-ChildItem (Join-Path $env:LOCALAPPDATA "Claude-Data") -Directory -Filter "claude_*" -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName "claude_desktop_config.json" }
    $configs += Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
    $configs += Get-ChildItem (Join-Path $env:LOCALAPPDATA "Packages") -Directory -Filter "Claude_*" -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName "LocalCache\Roaming\Claude\claude_desktop_config.json" }
    foreach ($path in $configs) {
        if (Test-Path $path) {
            $json = [System.IO.File]::ReadAllText($path) | ConvertFrom-Json
            if ($json.mcpServers -and $json.mcpServers.PSObject.Properties["foulee"]) {
                Copy-Item $path "$path.avant-desinstallation-foulee" -Force
                $json.mcpServers.PSObject.Properties.Remove("foulee")
                # UTF-8 sans BOM : Claude Desktop ne lit pas un JSON précédé d'un BOM
                $text = $json | ConvertTo-Json -Depth 20
                [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))
                Write-Host "Foulée retiré de $path"
            }
        }
    }
}

$answer = Read-Host "Supprimer aussi ta clé API Garmin de ce PC ? [o/N]"
if ($answer -match '^\s*[oOyY]' -and (Test-Path $Foulee)) { & $Foulee forget-key }

Write-Host "Terminé. Pour tout effacer, supprime ensuite le dossier $Root (il contient tes données)."
