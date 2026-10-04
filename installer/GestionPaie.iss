; Installateur Windows de « Gestion des Salaires » (Inno Setup 6).
;
; Prérequis : l'exécutable construit en mode dossier
;   python -m PyInstaller --noconfirm GestionPaie.spec   (-> dist\GestionPaie\)
; Puis, depuis ce dossier :
;   "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" GestionPaie.iss
; Résultat : dist_installer\Setup_GestionPaie_<version>.exe
;
; Les données (base, sauvegardes, modèles) vivent dans %APPDATA%\GestionPaie,
; jamais dans le dossier d'installation : une mise à jour ou une
; désinstallation ne les touche pas.

#define NomApp "Gestion des Salaires"
#define VersionApp "1.8.0"
#define Editeur "Daniel Tchomtchi"
#define Exe "GestionPaie.exe"

[Setup]
AppId={{7C2F5E61-3B8D-4E7A-9C41-5D0B8F2A6E13}
AppName={#NomApp}
AppVersion={#VersionApp}
AppVerName={#NomApp} {#VersionApp}
AppPublisher={#Editeur}
AppContact=tchomtchidaniel@gmail.com
AppCopyright=Copyright (c) 2026 {#Editeur}. Tous droits réservés.
VersionInfoVersion={#VersionApp}
DefaultDirName={autopf}\GestionPaie
DefaultGroupName={#NomApp}
DisableProgramGroupPage=yes
LicenseFile=LICENCE_UTILISATION.txt
OutputDir=..\dist_installer
OutputBaseFilename=Setup_GestionPaie_{#VersionApp}
SetupIconFile=..\assets\favicon.ico
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#NomApp}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; Installation possible sans droits administrateur (pour l'utilisateur
; courant) ; l'assistant propose aussi « pour tous les utilisateurs ».
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "Créer une icône sur le Bureau"; GroupDescription: "Raccourcis :"

[Files]
; Jamais de dossier data\ à côté de l'exécutable : l'application passerait
; en mode « portable » et rangerait les données dans le dossier d'installation.
Source: "..\dist\GestionPaie\*"; DestDir: "{app}"; Excludes: "data"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#NomApp}"; Filename: "{app}\{#Exe}"
Name: "{autodesktop}\{#NomApp}"; Filename: "{app}\{#Exe}"; Tasks: bureau

[Run]
Filename: "{app}\{#Exe}"; Description: "Lancer {#NomApp}"; Flags: nowait postinstall skipifsilent
