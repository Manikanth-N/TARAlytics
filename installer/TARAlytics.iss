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

; Compression — lzma2 gives best ratio for Python bundles
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; UI
WizardStyle=modern
WizardSizePercent=110
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
ShowLanguageDialog=no

; Versioning
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}

; ─────────────────────────────────────────────────────────────────────────────
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ─────────────────────────────────────────────────────────────────────────────
[CustomMessages]
; Shown on the welcome page below the big welcome header
WelcomeLabel2=This will install [name/ver] on your computer.%n%n\
All required components are included — Python runtime, Qt libraries, NumPy, %n\
Pandas, and cryptography support — no additional software needed.%n%n\
It is recommended that you close all other applications before continuing.

; ─────────────────────────────────────────────────────────────────────────────
[Tasks]
; Desktop shortcut (opt-in — unchecked by default)
Name: "desktopicon"; \
     Description: "Create a &Desktop shortcut"; \
     GroupDescription: "Additional shortcuts:"

; ─────────────────────────────────────────────────────────────────────────────
[Files]
; Copy the entire PyInstaller output (Python runtime + all bundled libraries)
Source: "{#AppSrcDir}\*"; \
        DestDir: "{app}"; \
        Flags: ignoreversion recursesubdirs createallsubdirs

; ─────────────────────────────────────────────────────────────────────────────
[Icons]
; Start Menu
Name: "{group}\{#AppName}"; \
      Filename: "{app}\{#AppExeName}"; \
      WorkingDir: "{app}"; \
      IconFilename: "{app}\{#AppExeName}"

; Uninstall entry in Start Menu
Name: "{group}\Uninstall {#AppShortName}"; \
      Filename: "{uninstallexe}"

; Desktop shortcut (only if task selected)
Name: "{autodesktop}\{#AppName}"; \
      Filename: "{app}\{#AppExeName}"; \
      WorkingDir: "{app}"; \
      IconFilename: "{app}\{#AppExeName}"; \
      Tasks: desktopicon

; ─────────────────────────────────────────────────────────────────────────────
[Run]
; Offer to launch the app at the end of installation
Filename: "{app}\{#AppExeName}"; \
          Description: "Launch {#AppName} now"; \
          Flags: nowait postinstall skipifsilent; \
          WorkingDir: "{app}"

; ─────────────────────────────────────────────────────────────────────────────
[UninstallDelete]
; Remove Qt / PyInstaller temp caches left by the app
Type: filesandordirs; Name: "{localappdata}\{#AppShortName}\cache"
Type: dirifempty;     Name: "{localappdata}\{#AppShortName}"

; ─────────────────────────────────────────────────────────────────────────────
[Registry]
; Write the install path so external tools can find the executable
Root: HKLM; Subkey: "Software\{#AppPublisher}\{#AppShortName}"; \
      ValueType: string; ValueName: "InstallPath"; \
      ValueData: "{app}"; Flags: uninsdeletekey

Root: HKLM; Subkey: "Software\{#AppPublisher}\{#AppShortName}"; \
      ValueType: string; ValueName: "Version"; \
      ValueData: "{#AppVersion}"
