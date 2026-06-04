; TARAlytics Windows Installer Script
; Requires: Inno Setup 6.x  (https://jrsoftware.org/isinfo.php)
;
; Build (after PyInstaller has run):
;   ISCC.exe installer\TARAlytics.iss
;
; Override version from CI:
;   ISCC.exe /DAppVersion=1.2.3 installer\TARAlytics.iss
;
; Output: dist\installer\TARAlytics_Setup_<version>.exe

; ── Version (overridable from command line with /DAppVersion=x.y.z) ──────────
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

; VersionInfoVersion / VersionInfoProductVersion must be purely numeric (x.y.z.w).
; Strip any pre-release suffix (e.g. "1.1.0-rc1" -> "1.1.0") for those fields; the
; full display version (with the suffix) is still used everywhere else.
#define NumericVersion AppVersion
#if Pos("-", NumericVersion) > 0
  #define NumericVersion Copy(NumericVersion, 1, Pos("-", NumericVersion) - 1)
#endif

; ── Core identifiers ─────────────────────────────────────────────────────────
#define AppName       "TARAlytics Log Analyzer"
#define AppShortName  "TARAlytics"
#define AppPublisher  "TARA UAV"
#define AppURL        "https://github.com/TARA-UAV/TARAlytics"
#define AppExeName    "TARAlytics.exe"
#define AppSrcDir     "..\dist\TARAlytics"

; ─────────────────────────────────────────────────────────────────────────────
[Setup]
; Unique installer identity — do NOT change AppId after first release
AppId={{8F2A1B3C-4D5E-6F7A-8B9C-0D1E2F3A4B5C}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}

; Installation directory — defaults to C:\Program Files\TARAlytics
DefaultDirName={autopf}\{#AppShortName}
DefaultGroupName={#AppShortName}
AllowNoIcons=yes

; Require 64-bit Windows 10+
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

; Require administrator for Program Files install
PrivilegesRequired=admin

; Output
OutputDir=..\dist\installer
OutputBaseFilename=TARAlytics_Setup_{#AppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

; Compression
Compression=lzma2
SolidCompression=yes

; UI
WizardStyle=modern
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
ShowLanguageDialog=no

; Version metadata embedded in the installer exe
VersionInfoVersion={#NumericVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#NumericVersion}

; ─────────────────────────────────────────────────────────────────────────────
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ─────────────────────────────────────────────────────────────────────────────
[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Additional shortcuts:"

; ─────────────────────────────────────────────────────────────────────────────
[Files]
; Copy the entire PyInstaller bundle — Python runtime + Qt + NumPy + Pandas +
; cryptography — all included. No additional software required on the target PC.
Source: "{#AppSrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; ─────────────────────────────────────────────────────────────────────────────
[Icons]
Name: "{group}\{#AppName}";                Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#AppShortName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";          Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

; ─────────────────────────────────────────────────────────────────────────────
[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent; WorkingDir: "{app}"

; ─────────────────────────────────────────────────────────────────────────────
[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\{#AppShortName}\cache"
Type: dirifempty;     Name: "{localappdata}\{#AppShortName}"

; ─────────────────────────────────────────────────────────────────────────────
[Registry]
Root: HKLM; Subkey: "Software\{#AppPublisher}\{#AppShortName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\{#AppPublisher}\{#AppShortName}"; ValueType: string; ValueName: "Version";     ValueData: "{#AppVersion}"
