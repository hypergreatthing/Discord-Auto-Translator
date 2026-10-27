; Inno Setup Script for Discord Auto Translator
; Download Inno Setup from https://jrsoftware.org/isinfo.php to compile this into a single .exe installer.

#define MyAppName "Discord Auto Translator"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Antigravity"
#define MyAppExeName "start_silent.vbs"

[Setup]
AppId={{D37E3A9C-8A9E-4E2F-A05F-0F54BB42E9D1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={userappdata}\DiscordAutoTranslator
DisableDirPage=no
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=DiscordAutoTranslator_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startupicon"; Description: "Start Discord Auto Translator automatically on Windows boot"; GroupDescription: "Windows Integration:"

[Files]
; Copy all application files to install folder
Source: "..\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".git,.venv,dist,__pycache__,*.pyc,backend\models,backend\config.json"

; Direct copy of BetterDiscord plugin
Source: "..\plugins\betterdiscord\DiscordAutoTranslator.plugin.js"; DestDir: "{userappdata}\BetterDiscord\plugins"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "wscript.exe"; Parameters: """{app}\{#MyAppExeName}"""; WorkingDir: "{app}"; IconFilename: "{sys}\shell32.dll"; IconIndex: 14
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "wscript.exe"; Parameters: """{app}\{#MyAppExeName}"""; WorkingDir: "{app}"; Tasks: desktopicon; IconFilename: "{sys}\shell32.dll"; IconIndex: 14
Name: "{userstartup}\{#MyAppName}"; Filename: "wscript.exe"; Parameters: """{app}\{#MyAppExeName}"""; WorkingDir: "{app}"; Tasks: startupicon; IconFilename: "{sys}\shell32.dll"; IconIndex: 14

[Run]
Filename: "{app}\Easy_Install.bat"; Description: "Run initial environment setup (install dependencies)"; Flags: postinstall shellexec
