; Installateur Windows de Foulée (Inno Setup 6).
;
; Construit par packaging\build.ps1 (sur GitHub Actions, à chaque version publiée) :
;   iscc /DAppVersion=0.4.0b1 /DNumericVersion=0.4.0.1 /DStageDir=...\build\stage /DOutputDir=...\build\out foulee.iss
;
; - installation pour l'utilisateur seul, sans droits d'administrateur :
;   %LOCALAPPDATA%\Programs\Foulee (programme) ; les données vont dans %LOCALAPPDATA%\Foulee ;
; - une mise à jour se fait par-dessus : Foulée se ferme, le programme est remplacé, Foulée se relance ;
; - la désinstallation garde les données, sauf si on demande de les effacer.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef NumericVersion
  #define NumericVersion "0.0.0.0"
#endif
#ifndef StageDir
  #define StageDir "..\build\stage"
#endif
#ifndef OutputDir
  #define OutputDir "..\build\out"
#endif
#define AppGuid "{6D3F2E8A-4C1B-4F5E-9A7D-2B8C0E1F4A93}"
#define RunKey "Software\Microsoft\Windows\CurrentVersion\Run"

[Setup]
AppId={#StringChange(AppGuid, "{", "{{")}
AppName=Foulée
AppVersion={#AppVersion}
AppVerName=Foulée {#AppVersion}
AppPublisher=Foulée
AppPublisherURL=https://github.com/willyl02/foulee
AppSupportURL=https://github.com/willyl02/foulee
AppUpdatesURL=https://github.com/willyl02/foulee/releases
VersionInfoVersion={#NumericVersion}
VersionInfoProductName=Foulée
VersionInfoProductTextVersion={#AppVersion}
VersionInfoDescription=Installation de Foulée
DefaultDirName={localappdata}\Programs\Foulee
DefaultGroupName=Foulée
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=Foulee-Setup-{#AppVersion}
SetupIconFile={#StageDir}\Foulee.ico
UninstallDisplayIcon={app}\Foulee.ico
UninstallDisplayName=Foulée
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no
LanguageDetectionMethod=none
UsePreviousTasks=yes
SetupLogging=yes

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[CustomMessages]
fr.TaskDesktop=Créer une icône sur le Bureau
fr.TaskStartup=Lancer Foulée à l'ouverture de session (synchro automatique)
fr.RunNow=Ouvrir Foulée maintenant
fr.EraseQuestion=Effacer aussi tes données Foulée de ce PC ?%n%nBase (séances, mesures, vues), fichiers FIT, réglages et clé API Garmin.%n%nRéponds « Non » pour les garder, par exemple pour réinstaller Foulée plus tard.
fr.KeptData=Foulée est désinstallé. Tes données sont conservées : tu les retrouveras en réinstallant Foulée.

[Tasks]
Name: "bureau"; Description: "{cm:TaskDesktop}"
Name: "demarrage"; Description: "{cm:TaskStartup}"

[InstallDelete]
; L'ancien Python et ses bibliothèques partent avant la copie du nouveau : rien ne traîne d'une version à l'autre
Type: filesandordirs; Name: "{app}\python"

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Foulée"; Filename: "{app}\python\Foulee.exe"; Parameters: "-m foulee app"; WorkingDir: "{app}"; IconFilename: "{app}\Foulee.ico"; Comment: "Tes données Garmin, chez toi"
Name: "{autodesktop}\Foulée"; Filename: "{app}\python\Foulee.exe"; Parameters: "-m foulee app"; WorkingDir: "{app}"; IconFilename: "{app}\Foulee.ico"; Comment: "Tes données Garmin, chez toi"; Tasks: bureau

[Registry]
; Seulement à la première installation : ensuite, c'est le réglage de l'application qui décide
Root: HKCU; Subkey: "{#RunKey}"; ValueType: string; ValueName: "Foulee"; ValueData: """{app}\python\Foulee.exe"" -m foulee app --demarrage"; Tasks: demarrage; Check: not WasInstalled

[Run]
Filename: "{app}\python\Foulee.exe"; Parameters: "-m foulee app"; WorkingDir: "{app}"; Description: "{cm:RunNow}"; Flags: postinstall nowait skipifsilent
; Mise à jour silencieuse lancée depuis Foulée : il se relance tout seul
Filename: "{app}\python\Foulee.exe"; Parameters: "-m foulee app --apres-maj"; WorkingDir: "{app}"; Flags: nowait; Check: WizardSilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
var
  WasInstalledFlag: Boolean;
  EraseData: Boolean;

function WasInstalled: Boolean;
begin
  Result := WasInstalledFlag;
end;

function InitializeSetup: Boolean;
begin
  WasInstalledFlag := RegKeyExists(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppGuid}_is1');
  Result := True;
end;

{ Mise à jour : les choix de la première installation restent (icônes, démarrage) }
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = wpSelectTasks) and WasInstalledFlag;
end;

{ Arrête ce qui tourne encore depuis le dossier du programme (serveur MCP lancé par Claude Desktop…) }
procedure StopLeftovers;
var
  ResultCode: Integer;
  Folder: String;
begin
  Folder := ExpandConstant('{app}');
  StringChangeEx(Folder, '''', '''''', True);
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "Get-Process | Where-Object { $_.Path -like ''' +
    Folder + '\*'' } | Stop-Process -Force -ErrorAction SilentlyContinue"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  Python: String;
begin
  Result := '';
  Python := ExpandConstant('{app}\python\python.exe');
  if FileExists(Python) then
    { L'application se ferme proprement (elle répond à cette demande) }
    Exec(Python, '-m foulee app --quitter', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if DirExists(ExpandConstant('{app}')) then
    StopLeftovers;
end;

function InitializeUninstall: Boolean;
begin
  EraseData := False;
  if not UninstallSilent then
    EraseData := MsgBox(CustomMessage('EraseQuestion'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
  Python, Params: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    Python := ExpandConstant('{app}\python\python.exe');
    Params := '-m foulee avant-desinstallation';
    if EraseData then
      Params := Params + ' --effacer-donnees';
    if FileExists(Python) then
      Exec(Python, Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    StopLeftovers;
  end;
  if CurUninstallStep = usPostUninstall then
  begin
    RegDeleteValue(HKCU, '{#RunKey}', 'Foulee');
    if not UninstallSilent and not EraseData then
      MsgBox(CustomMessage('KeptData'), mbInformation, MB_OK);
  end;
end;
