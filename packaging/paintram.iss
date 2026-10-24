; Inno Setup script. Built by packaging/build.py: expects dist\Paintram (PyInstaller) and build\models (model weights).
#define AppName "Paintram"
#ifndef AppVersion
  #define AppVersion "2.1.0"
#endif

[Setup]
AppId={{6E1B2B8A-5C47-4D0E-9F51-3A7A0C2D91B4}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Paintram
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=..\build\installer
OutputBaseFilename=PaintramSetup-{#AppVersion}
SetupIconFile=..\icons\paint.ico
UninstallDisplayIcon={app}\Paintram.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
; the bundle is several GB: split into <2 GiB slices (GitHub release assets and FAT limits)
DiskSpanning=yes
DiskSliceSize=1900000000
SlicesPerDisk=1
Compression=lzma2/fast
SolidCompression=no
WizardStyle=modern
DisableProgramGroupPage=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\Paintram\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; model weights are already compressed
Source: "..\build\models\*"; DestDir: "{app}\models"; Flags: recursesubdirs createallsubdirs ignoreversion nocompression

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Paintram.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Paintram.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Paintram.exe"; Description: "Launch Paintram"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
  if not FileExists(ExpandConstant('{sys}\nvcuda.dll')) then
    MsgBox('No NVIDIA driver was found. Paintram will still install and work, but AI image generation ' +
           'will run on the CPU and be very slow. Install the latest NVIDIA driver for GPU speed.',
           mbInformation, MB_OK);
end;
