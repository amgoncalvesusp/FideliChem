; Inno Setup definition for the Windows installer.
; CI supplies /DAppVersion=0.1.1 from the release tag.

#ifndef AppVersion
  #define AppVersion "0.1.1"
#endif

[Setup]
AppId={{5C177E5E-1D7A-4F57-9F0E-9B6D9F5F2E17}
AppName=FideliChem
AppVersion={#AppVersion}
AppPublisher=Adriano Marques Gonçalves (UNIARA)
AppPublisherURL=https://github.com/amgoncalvesusp/FideliChem
DefaultDirName={localappdata}\Programs\FideliChem
DefaultGroupName=FideliChem
DisableProgramGroupPage=yes
OutputDir=..\release-assets
OutputBaseFilename=FideliChem-{#AppVersion}-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\src\fidelichem\gui\assets\fidelichem-mark.ico
UninstallDisplayIcon={app}\FideliChem.exe
PrivilegesRequired=lowest

[Files]
Source: "..\release-assets\pyinstaller-dist\FideliChem\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\FideliChem"; Filename: "{app}\FideliChem.exe"; IconFilename: "{app}\FideliChem.exe"
Name: "{userdesktop}\FideliChem"; Filename: "{app}\FideliChem.exe"; IconFilename: "{app}\FideliChem.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\FideliChem.exe"; Description: "Launch FideliChem"; Flags: nowait postinstall skipifsilent
