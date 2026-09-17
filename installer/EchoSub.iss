; SPDX-License-Identifier: GPL-3.0-only
; Copyright (C) 2026 Mohammad Al-Safadi
;
; Inno Setup 6 script for the EchoSub installer. Build it with scripts\build-installer.ps1, which passes
; /DAppVersion=<version> and expects the PyInstaller output in dist\EchoSub.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "EchoSub"
#define AppPublisher "Mohammad Al-Safadi"
#define AppURL "https://github.com/mPhpMaster/echo-sub"
#define AppExe "EchoSub.exe"

[Setup]
AppId={{6F1E3C2A-9B7D-4E58-A1C4-3D2B8E7F5A91}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
AppCopyright=Copyright (C) 2026 {#AppPublisher}
AppComments=Live, translated captions for anything your PC plays.
AppContact=mPhpMaster@gmail.com
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
VersionInfoCopyright=Copyright (C) 2026 {#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist\installer
OutputBaseFilename=EchoSub-Setup-{#AppVersion}
SetupIconFile=..\echosub\assets\echosub.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
; ~2 GB of CUDA libraries: compress in Inno's separate 64-bit process (the compiler itself is 32-bit and runs
; out of memory with ultra64's 1 GB dictionary).
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMADictionarySize=262144
LZMANumBlockThreads=4
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; Install for the current user without admin rights by default; the user can choose all users instead.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Ask to close a running EchoSub before installing or uninstalling (the app owns this mutex).
AppMutex=EchoSubAppMutex
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[CustomMessages]
english.StartWithWindows=Start {#AppName} when I sign in to Windows
arabic.StartWithWindows=تشغيل {#AppName} عند تسجيل الدخول إلى ويندوز
english.RemoveData=Also delete EchoSub's settings, downloaded AI models, logs and transcripts?%n%n(%1)
arabic.RemoveData=هل تريد أيضاً حذف إعدادات EchoSub ونماذج الذكاء الاصطناعي التي تم تنزيلها والسجلات والنصوص؟%n%n(%1)
english.FirstRunNote=On first start, EchoSub downloads its AI models (about 2.3 GB).
arabic.FirstRunNote=عند التشغيل الأول، يقوم EchoSub بتنزيل نماذج الذكاء الاصطناعي (حوالي 2.3 جيجابايت).

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startup"; Description: "{cm:StartWithWindows}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\EchoSub\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\PRIVACY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Live, translated captions for anything your PC plays"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; \
    ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpFinished then
    WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 + CustomMessage('FirstRunNote');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\{#AppName}');
    if DirExists(DataDir) and not UninstallSilent() then
      if MsgBox(FmtMessage(CustomMessage('RemoveData'), [DataDir]), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
