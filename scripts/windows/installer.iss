; Inno Setup Script for Luga Assist
; Generates standalone Windows Installer (Setup.exe) with Desktop & Start Menu shortcuts

#define MyAppName "Luga Assist"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Luga Assist Team"
#define MyAppURL "https://github.com/oceanondawave/luga-assist"
#define MyAppExeName "Luga Assist.exe"

#ifndef AppRootDir
  #define AppRootDir "..\.."
#endif

#ifndef DistSourceDir
  #define DistSourceDir AppRootDir + "\dist\Luga Assist"
#endif

#ifndef OutputDir
  #define OutputDir AppRootDir + "\dist"
#endif

[Setup]
AppId={{8B1D4F37-5674-4C4A-9A4B-3D4F5A6B7C8D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=Luga-Assist-Setup
#if FileExists(AppRootDir + "\app.ico")
SetupIconFile={#AppRootDir}\app.ico
#endif
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
CloseApplications=yes
CloseApplicationsFilter=*.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "Khoi dong cung Windows (Run on startup)"; GroupDescription: "Cau hinh khoi dong:"; Flags: unchecked

[Files]
Source: "{#DistSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#AppRootDir}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#AppRootDir}\README.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Go cai dat {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c taskkill /F /IM ""{#MyAppExeName}"" >nul 2>&1"; Flags: runhidden

