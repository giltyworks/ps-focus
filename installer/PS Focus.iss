; PS Focus installer for Inno Setup 6. Build it with tools/build_release.py, which supplies these values
; and the files listed under [Files]. Installs for the current Windows user only, so no administrator rights are needed.
; Since 1.1 the app is a folder, the program and its _internal runtime, compressed on disk once installed. It installs
; over the single-file Tk versions before it, keeping their place, Installed apps entry, startup entry and data
#ifndef AppVersion
  #error Pass /DAppVersion=x.y.z (tools/build_release.py does this)
#endif
#ifndef NoticesFile
  #error Pass /DNoticesFile=<path to the generated third-party notices>
#endif
#ifndef AppFolder
  #error Pass /DAppFolder=<the program folder PyInstaller made>
#endif

#define AppName "PS Focus"
#define AppPublisher "Giltyworks"
#define AppExe "PS Focus.exe"
; Must match UNINSTALL_KEY_PATH in uninstall.py
#define UninstallKey "Software\Microsoft\Windows\CurrentVersion\Uninstall\PS Focus"

[Setup]
AppId={{73954352-C339-4838-85CB-012734CDBD98}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppContact=giltyworks@gmail.com
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} installer
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
LicenseFile=..\TERMS.md
; The app removes itself when run with --uninstall, registered below, so Inno Setup adds no uninstaller of its own
Uninstallable=no
CloseApplications=force
RestartApplications=no
SetupIconFile=..\assets\icons\PSFocus.ico
WizardStyle=modern
; One solid block with a large dictionary keeps the download small
Compression=lzma2/ultra64
LZMANumBlockThreads=1
LZMANumFastBytes=273
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\installer
OutputBaseFilename=PS-Focus-Setup-{#AppVersion}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
; Offered only to a new installation; an existing one keeps the choice made in Settings. Left ticked, the app
; registers itself the first time it runs; unticked, a starting settings file tells it not to (see IsNewInstallation)
Name: "startwithwindows"; Description: "Start PS Focus with Windows"; Check: IsNewInstallation

[Files]
Source: "{#AppFolder}\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#AppFolder}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\TERMS.md"; DestDir: "{app}"; DestName: "Terms of Use.txt"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "License.txt"; Flags: ignoreversion
Source: "..\PRIVACY.md"; DestDir: "{app}"; DestName: "Privacy Policy.txt"; Flags: ignoreversion
Source: "{#NoticesFile}"; DestDir: "{app}"; DestName: "Third-Party Notices.txt"; Flags: ignoreversion

[InstallDelete]
; Versions before 1.0.1 installed a separate uninstaller, which the app has since absorbed
Type: files; Name: "{app}\Uninstall PS Focus.exe"
; The runtime folder is replaced whole, so files a newer build no longer needs do not linger from an older one
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; The Installed apps entry, which runs the app's uninstall mode with its option to delete user data
Root: HKCU; Subkey: "{#UninstallKey}"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#AppName}"
Root: HKCU; Subkey: "{#UninstallKey}"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#AppVersion}"
Root: HKCU; Subkey: "{#UninstallKey}"; ValueType: string; ValueName: "Publisher"; ValueData: "{#AppPublisher}"
Root: HKCU; Subkey: "{#UninstallKey}"; ValueType: string; ValueName: "DisplayIcon"; ValueData: "{app}\{#AppExe}"
Root: HKCU; Subkey: "{#UninstallKey}"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"
Root: HKCU; Subkey: "{#UninstallKey}"; ValueType: string; ValueName: "UninstallString"; ValueData: """{app}\{#AppExe}"" --uninstall"
Root: HKCU; Subkey: "{#UninstallKey}"; ValueType: dword; ValueName: "NoModify"; ValueData: 1
Root: HKCU; Subkey: "{#UninstallKey}"; ValueType: dword; ValueName: "NoRepair"; ValueData: 1

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch PS Focus"; Flags: nowait postinstall skipifsilent

[Code]
// A running PS Focus is asked to close itself before its files are replaced. Closed instead by Windows'
// Restart Manager, the launcher at the front of the app waits about 30 seconds to be ended by force.
// The names must match SingleInstance in windows_startup.py. Versions before 1.0.4 do not know the
// request, and the Restart Manager still closes those as before
const
  EVENT_MODIFY_STATE = $0002;
  ExitRequestName = 'Local\PSFocus.ExitRequest';
  RunningCopyName = 'Local\PSFocus.RunningCopy';
  ExitWaitMilliseconds = 15000;

function OpenEvent(DesiredAccess: Cardinal; InheritHandle: Boolean; Name: String): THandle;
  external 'OpenEventW@kernel32.dll stdcall';
function SetEvent(Event: THandle): Boolean;
  external 'SetEvent@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitRequest: THandle;
  Waited: Integer;
begin
  Result := '';
  ExitRequest := OpenEvent(EVENT_MODIFY_STATE, False, ExitRequestName);
  if ExitRequest = 0 then
    Exit;
  SetEvent(ExitRequest);
  CloseHandle(ExitRequest);
  // The app holds this name for as long as it runs
  Waited := 0;
  while CheckForMutexes(RunningCopyName) and (Waited < ExitWaitMilliseconds) do
  begin
    Sleep(100);
    Waited := Waited + 100;
  end;
  // Then the launcher deletes the app's temporary files and ends too
  Sleep(1000);
end;

// No settings yet, under either the current or the pre-rename data folder: PS Focus has never run for this user
function IsNewInstallation: Boolean;
begin
  Result := not FileExists(ExpandConstant('{userappdata}\PS Focus\settings.json')) and
    not FileExists(ExpandConstant('{userappdata}\FocusTrace\settings.json'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  // The program files are compressed by Windows, which reads them back transparently; on a drive that cannot
  // compress, the installation simply stays as it is
  if CurStep = ssPostInstall then
  begin
    if not Exec(ExpandConstant('{sys}\compact.exe'),
      '/C /I /Q /EXE:LZX /S:"' + ExpandConstant('{app}') + '" "' + ExpandConstant('{app}\*') + '"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      Log('Program compression could not start')
    else
      Log(Format('Program compression exit code: %d', [ResultCode]));
  end;
  // The app fills in every other setting with its defaults when it reads this file
  if (CurStep = ssPostInstall) and IsNewInstallation and not WizardIsTaskSelected('startwithwindows') then
  begin
    ForceDirectories(ExpandConstant('{userappdata}\PS Focus'));
    SaveStringToFile(ExpandConstant('{userappdata}\PS Focus\settings.json'), '{"launch_on_startup": false}', False);
  end;
end;
