; Wheel Launcher — установщик (Inno Setup 6). Собирается build/build.sh.
#define AppName "Wheel Launcher"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{7D3A5C1E-4B62-4F0A-9E8D-2C61B7A0F4D3}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Wheel Launcher
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Wheel_Launcher_Setup_{#AppVersion}
SetupIconFile=..\wheel_launcher.ico
UninstallDisplayIcon={app}\Wheel Launcher.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=admin
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Ярлык на рабочем столе"; GroupDescription: "Ярлыки:"

[Files]
Source: "..\dist\Wheel Launcher\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Wheel Launcher.exe"
Name: "{group}\Руководство"; Filename: "{app}\README.txt"
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\Wheel Launcher.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Wheel Launcher.exe"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent
