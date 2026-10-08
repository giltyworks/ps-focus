; Separate preview installer. Never uses the production app's ID, startup entry or custom uninstaller.
#ifndef AppVersion
  #error Pass /DAppVersion=x.y.z
#endif
#ifndef NoticesFile
  #error Pass /DNoticesFile=<generated notices path>
#endif
#define AppName "PS Focus Qt Preview"
#define AppExe "PS Focus Qt Preview.exe"
#ifndef AppExecutable
  #define AppExecutable "..\dist\qt-preview\PS Focus Qt Preview.exe"
#endif

[Setup]
AppId={{B9608271-5AC7-486C-934C-59B68AC34739}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Giltyworks
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} installer
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\TERMS.md
Uninstallable=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
CloseApplications=yes
CloseApplicationsFilter={#AppExe}
RestartApplications=no
SetupIconFile=..\assets\icons\PSFocus.ico
WizardStyle=modern
; A single solid block and a larger dictionary shrink the retained offline installer.
Compression=lzma2/ultra64
LZMANumBlockThreads=1
LZMANumFastBytes=273
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\qt-preview
OutputBaseFilename=PS-Focus-Qt-Preview-Setup-{#AppVersion}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#AppExecutable}"; DestDir: "{app}"; DestName: "{#AppExe}"; Flags: ignoreversion
#ifdef AppRuntimeDir
Source: "{#AppRuntimeDir}\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
#endif
Source: "..\TERMS.md"; DestDir: "{app}"; DestName: "Terms of Use.txt"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "License.txt"; Flags: ignoreversion
Source: "..\PRIVACY.md"; DestDir: "{app}"; DestName: "Privacy Policy.txt"; Flags: ignoreversion
Source: "{#NoticesFile}"; DestDir: "{app}"; DestName: "Third-Party Notices.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "PSFocus.PSFocus.QtPreview"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon; AppUserModelID: "PSFocus.PSFocus.QtPreview"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch Qt preview"; Flags: nowait postinstall skipifsilent

; Default Inno uninstall removes only its installed files/shortcuts. No AppData or Google token deletion.
#ifdef AppRuntimeDir
[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then begin
    { Compress only these program files; Windows reads them transparently.
      Unsupported filesystems retain the functional uncompressed installation. }
    if not Exec(ExpandConstant('{sys}\compact.exe'),
      '/C /I /Q /EXE:LZX /S:"' + ExpandConstant('{app}') + '" "' + ExpandConstant('{app}\*') + '"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      Log('Program compression could not start')
    else
      Log(Format('Program compression exit code: %d', [ResultCode]));
  end;
end;
#endif
