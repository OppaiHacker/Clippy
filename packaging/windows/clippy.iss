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
; Teto is drawn by [Code] as a full-height strip on every page, so the window must keep its size
WizardResizable=no
; several sizes: Inno picks the one matching the display scale
WizardSmallImageFile=art\small-*.bmp

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
Name: autostart; Description: "Start Clippy with Windows"; Flags: unchecked

[InstallDelete]
; an update over an older version must not keep its stale Python modules and DLLs (user data lives in %LOCALAPPDATA%\Clippy)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "art\wizard-*.bmp"; Flags: dontcopy
Source: "..\..\dist\Clippy\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Clippy"; Filename: "{app}\Clippy.exe"
Name: "{userdesktop}\Clippy"; Filename: "{app}\Clippy.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Clippy"; ValueData: """{app}\Clippy.exe"" --background"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\Clippy.exe"; Description: "Launch Clippy"; Flags: nowait postinstall skipifsilent

[Code]
{ Move the page's controls left into the space of its (hidden) built-in wizard image. }
procedure DropPageImage(Page: TNewNotebookPage; Img: TBitmapImage);
var
  I: Integer;
  C: TControl;
begin
  Img.Visible := False;
  for I := 0 to Page.ControlCount - 1 do begin
    C := Page.Controls[I];
    if C.Left > Img.Left then begin
      C.Left := C.Left - Img.Width;
      C.Width := C.Width + Img.Width;
    end;
  end;
end;

procedure InitializeWizard;
var
  I, N, W, H: Integer;
  Lefts, Widths: array of Integer;
  Art: String;
  Teto: TBitmapImage;
begin
  H := WizardForm.ClientHeight;
  W := H * 164 div 314;  { aspect ratio of the artwork }
  { smallest artwork at least as tall as the window, so it is only ever shrunk }
  if H <= 314 then Art := 'wizard-164.bmp'
  else if H <= 459 then Art := 'wizard-240.bmp'
  else if H <= 628 then Art := 'wizard-328.bmp'
  else if H <= 797 then Art := 'wizard-410.bmp'
  else Art := 'wizard-480.bmp';
  ExtractTemporaryFile(Art);

  DropPageImage(WizardForm.WelcomePage, WizardForm.WizardBitmapImage);
  DropPageImage(WizardForm.FinishedPage, WizardForm.WizardBitmapImage2);

  { widen the window by the strip and put every control back where it was, shifted right; geometry is
    saved first because anchored controls move or stretch on their own when the window grows }
  N := WizardForm.ControlCount;
  SetArrayLength(Lefts, N);
  SetArrayLength(Widths, N);
  for I := 0 to N - 1 do begin
    Lefts[I] := WizardForm.Controls[I].Left;
    Widths[I] := WizardForm.Controls[I].Width;
  end;
  WizardForm.ClientWidth := WizardForm.ClientWidth + W;
  for I := 0 to N - 1 do
    WizardForm.Controls[I].SetBounds(Lefts[I] + W, WizardForm.Controls[I].Top, Widths[I], WizardForm.Controls[I].Height);

  Teto := TBitmapImage.Create(WizardForm);
  Teto.Parent := WizardForm;
  Teto.SetBounds(0, 0, W, H);
  Teto.Stretch := True;
  Teto.Bitmap.LoadFromFile(ExpandConstant('{tmp}\') + Art);
end;
