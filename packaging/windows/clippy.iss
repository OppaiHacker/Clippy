; Build: iscc /DAppVersion=1.2.3 packaging\windows\clippy.iss  (after PyInstaller has produced dist\Clippy)
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{B6D2F0C4-3A57-4E0B-9C1E-5D7A8F2E1C90}
AppName=Clippy
AppVersion={#AppVersion}
AppPublisher=OppaiHacker
DefaultDirName={localappdata}\Programs\Clippy
DefaultGroupName=Clippy
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=clippy.ico
UninstallDisplayIcon={app}\Clippy.exe
OutputDir=..\..\dist
OutputBaseFilename=ClippySetup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
CloseApplications=force
WizardStyle=modern

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
Name: autostart; Description: "Start Clippy with Windows"; Flags: unchecked

[Files]
Source: "..\..\dist\Clippy\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Clippy"; Filename: "{app}\Clippy.exe"
Name: "{userdesktop}\Clippy"; Filename: "{app}\Clippy.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Clippy"; ValueData: """{app}\Clippy.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\Clippy.exe"; Description: "Launch Clippy"; Flags: nowait postinstall skipifsilent
