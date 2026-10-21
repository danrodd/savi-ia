; ─────────────────────────────────────────────────────────────────────
; Instalador de escritorio de SAVI — Inno Setup 6.1+
;
; Compilar con installer\build.ps1 (encadena frontend + PyInstaller +
; este script). Para compilarlo suelto: ISCC.exe installer\savi.iss
;
; El asistente pide lo mínimo que no se puede adivinar y escribe el
; archivo .env de la aplicación:
;   1. Prerrequisitos (Node.js, Git for Windows, CLI de Claude)
;   2. Base de datos del ERP    — obligatoria, PostgreSQL
;   3. Base de datos de SAVI    — SQLite por defecto
;   4. Autenticación de Claude (token o clave de API) y puerto
; ─────────────────────────────────────────────────────────────────────

#define AppName        "SAVI"
; La versión es el tag de git: `build.ps1` la calcula con
; scripts/version.py y la pasa con /DAppVersion (texto, p. ej.
; v1.4.0-14-gbf8eee7) y /DAppVersionNumber (X.Y.Z del último tag). Ver
; installer/README.md#versionado. Los `#ifndef` son solo para compilar
; este .iss suelto (`ISCC.exe installer\savi.iss`) durante el desarrollo
; del propio instalador — y por eso dicen 0.0.0-dev, no un número real.
#ifndef AppVersion
  #define AppVersion   "0.0.0-dev"
#endif
#ifndef AppVersionNumber
  #define AppVersionNumber "0.0.0"
#endif
; URL de SAVI Cloud que se escribe en el .env cuando el asistente recibe un
; token de vinculación. build.ps1 la pasa con /DSaviCloudUrl=<url> (parámetro
; -SaviCloudUrl). Vacía a propósito por defecto: la de producción todavía no
; está definida. Con la URL vacía la página "Conectar con SAVI Cloud" NO se
; muestra y el instalador no escribe nada de SAVI Cloud en el .env.
#ifndef SaviCloudUrl
  #define SaviCloudUrl ""
#endif
; 1 = la vinculación es OBLIGATORIA: el asistente no avanza sin un token válido.
; Es el build de la organización interna (SAVI Master): cada equipo tiene que quedar
; registrado en SAVI Cloud para que SEO Group sepa cuántas instalaciones hay y de quién
; son. build.ps1 lo pasa con /DSaviCloudRequired=1 (parámetro -SaviCloudRequired).
#ifndef SaviCloudRequired
  #define SaviCloudRequired 0
#endif
#define AppPublisher   "SEO Group"
#define AppExe         "SAVI.exe"

; Puerto local por defecto. NO 8000 a proposito: es de los puertos mas
; disputados que existe (lo toman los tutoriales de Django y FastAPI,
; `python -m http.server` y media docena de herramientas), y una colision
; hacia fallar el arranque en el equipo del cliente.
;
; 31900 esta en el rango de puertos de usuario y bien lejos de los
; servicios comunes. Por debajo de 49152 a proposito: desde ahi arranca
; el rango dinamico de Windows, y el sistema puede entregar esos puertos
; a conexiones de salida — un puerto fijo ahi falla de forma intermitente
; y sin patron, que es el peor tipo de error para soportar por telefono.
#define DefaultPort    "31900"

; Versiones fijadas de los prerrequisitos. Al actualizarlas hay que
; verificar que la URL siga viva: un 404 rompe la instalación en el
; equipo del cliente, no acá.
#define NodeVersion    "22.20.0"
#define NodeUrl        "https://nodejs.org/dist/v22.20.0/node-v22.20.0-x64.msi"
#define GitVersion     "2.51.0"
#define GitUrl         "https://github.com/git-for-windows/git/releases/download/v2.51.0.windows.1/Git-2.51.0-64-bit.exe"

[Setup]
AppId={{7D1C4E82-3B96-4A17-9E5D-2F8A6C0B4D31}
AppName={#AppName}
AppVersion={#AppVersion}
; El recurso de versión del .exe del instalador exige N.N.N.N: no acepta
; el texto de git describe.
VersionInfoVersion={#AppVersionNumber}
VersionInfoProductTextVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=output
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Hacen falta privilegios de administrador para escribir en Program
; Files y para instalar Node.js y Git si faltan.
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
; Icono del propio instalador. El de la aplicación y el de los accesos
; directos salen del .exe, que lo lleva embebido desde savi.spec.
SetupIconFile=assets\savi.ico
; Avisa a Windows que cambió el PATH del sistema (entrada de npm global).
ChangesEnvironment=yes
; `force` y no el `yes` por defecto: SAVI.exe corre uvicorn sin ventana y sin
; bucle de mensajes, así que ignora el WM_CLOSE que manda el Restart Manager.
; Con el default, actualizar sobre una instalación en ejecución frena en
; "no pudo cerrar de forma automática todas las aplicaciones" y Reintentar
; no destraba nada — la única salida es matar el proceso a mano.
CloseApplications=force
; No relanzarlo solo al terminar: el acceso directo de postinstalación ya
; ofrece abrirlo, y si además lo levanta el Restart Manager quedan dos
; instancias peleando por el puerto.
RestartApplications=no

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "build\dist\{#AppName}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "env.template"; DestDir: "{app}"; Flags: ignoreversion
; Prueba de conexión del asistente: se extrae a {tmp} durante las páginas de
; configuración, antes de instalar nada. No se copia a {app}.
Source: "build\dbcheck\savi-dbcheck.exe"; Flags: dontcopy

[InstallDelete]
; Inno ejecuta [InstallDelete] ANTES de copiar [Files]. Sin esto, una
; actualización deja encima de la versión nueva las librerías de la anterior
; que ya no existen (PyInstaller las empaqueta en _internal), y una DLL
; vieja puede ganarle a la nueva y romper el arranque de formas difíciles de
; ver. Solo _internal: el .env (y el .env.anterior) viven en {app}, no ahí.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
; Inicio de sesión con la cuenta de Claude del cliente. Queda como acceso
; directo permanente y no solo como paso de la instalación: la sesión se
; puede vencer, y el cliente puede cambiar de cuenta o de plan.
Name: "{group}\Iniciar sesión en Claude"; Filename: "{app}\{#AppExe}"; Parameters: "--login"
; Acceso directo de soporte: valida el .env y prueba las dos conexiones.
Name: "{group}\Diagnosticar {#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--check-config"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; El CLI de Claude se instala con prefijo en ProgramData para que lo vean
; todas las cuentas del equipo; esa ruta tiene que estar en el PATH del
; sistema. `NeedsPathEntry` evita duplicarla al reinstalar.
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
    ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{commonappdata}\npm"; \
    Check: NeedsPathEntry

[Run]
; Sin `nowait`: el inicio de sesión tiene que terminar antes de que
; arranque SAVI, o la primera pregunta al agente falla por falta de
; credencial y parece que la instalación quedó rota.
; Las entradas `postinstall` corren como el usuario que lanzó el instalador
; (no como el administrador que elevó) salvo que lleven `runascurrentuser`,
; que acá no llevan a propósito: la sesión de Claude tiene que guardarse en
; el perfil de quien va a usar SAVI.
Filename: "{app}\{#AppExe}"; Parameters: "--login"; \
    Description: "Iniciar sesión con la cuenta de Claude (abre el navegador)"; \
    Flags: postinstall skipifsilent; Check: NeedsClaudeLogin
Filename: "{app}\{#AppExe}"; Description: "Iniciar {#AppName} ahora"; Flags: postinstall nowait skipifsilent

[Dirs]
; Reporte del diagnóstico que muestra el instalador. Lo escribe SAVI.exe
; corriendo como el usuario que lanzó el instalador (no elevado): por eso
; una carpeta común con permiso de escritura para los usuarios.
Name: "{commonappdata}\SAVI"; Permissions: users-modify

[UninstallDelete]
; El .env se genera en la instalación, no viene en [Files]: sin esto
; queda huérfano al desinstalar.
Type: files; Name: "{app}\.env"
Type: files; Name: "{app}\npm-claude-cli.log"

[Code]
var
  PrereqPage:    TWizardPage;
  ReconfigPage:  TInputOptionWizardPage;
  ErpPage:       TInputQueryWizardPage;
  AgentKindPage: TInputOptionWizardPage;
  AgentPgPage:   TInputQueryWizardPage;
  ClaudePage:    TInputQueryWizardPage;
  CloudPage:     TInputQueryWizardPage;
  DownloadPage:  TDownloadWizardPage;

  NeedsNode: Boolean;
  NeedsGit:  Boolean;
  NeedsCli:  Boolean;
  AlreadyLoggedIn: Boolean;
  // Lo pone VerifyInstallation cuando el diagnostico devuelve el codigo
  // de problema de autenticacion. Sin esto la casilla de login no
  // aparecia justo cuando hacia falta: su condicion exigia instalacion
  // nueva, y daba por buena la credencial con que el archivo existiera
  // — que es cierto tambien con el token vencido.
  AuthNeedsAttention: Boolean;

  // Prueba de conexión (savi-dbcheck.exe). Los datos de la última prueba
  // que salió bien, por página: "Siguiente" no repite una prueba que ya
  // pasó con los mismos valores.
  ErpTestButton:     TNewButton;
  AgentTestButton:   TNewButton;
  DbCheckExtracted:  Boolean;
  LastOkErp:         String;
  LastOkAgent:       String;

{ El PATH del propio proceso no se puede cambiar desde Pascal Script y
  hace falta cambiarlo — el porqué está en `PutNodeOnPath`. }
procedure SetEnvVar(lpName, lpValue: String);
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

{ ── Detección de prerrequisitos ─────────────────────────────────────── }

// HKLM64 y no HKLM, y las dos carpetas de Program Files, a proposito.
//
// Git y Node se instalan en 64 bits: sus claves viven en la vista de 64
// bits del registro y sus binarios en C:\Program Files. Un instalador
// corriendo en 32 bits lee redirigido a Wow6432Node y resuelve la
// constante commonpf como Program Files (x86) — no encuentra ninguno de
// los dos y los reinstala al pedo. Hoy el [Setup] fuerza modo 64 bits,
// pero entonces la deteccion dependeria de que esa directiva no se toque
// nunca. Explicito es mas barato que sutil.
//
// OJO con los comentarios { } en este archivo: terminan en la PRIMERA
// llave de cierre, asi que cualquier constante de Inno escrita adentro
// corta el comentario y lo que sigue se compila como codigo. Por eso
// este bloque usa //.
function FindUnder(const RelativePath: String): String;
begin
  Result := ExpandConstant('{commonpf64}') + RelativePath;
  if FileExists(Result) then
    Exit;
  Result := ExpandConstant('{commonpf32}') + RelativePath;
  if not FileExists(Result) then
    Result := '';
end;

function GitBashPath(): String;
var
  InstallPath: String;
begin
  Result := '';
  if RegQueryStringValue(HKLM64, 'SOFTWARE\GitForWindows', 'InstallPath', InstallPath) then
  begin
    // La clave del registro puede traer barra final; sin recortarla la
    // ruta queda con barra doble y se arrastra a todo lo que se derive
    // de ella.
    InstallPath := RemoveBackslashUnlessRoot(InstallPath);
    if FileExists(InstallPath + '\bin\bash.exe') then
    begin
      Result := InstallPath + '\bin\bash.exe';
      Exit;
    end;
  end;
  Result := FindUnder('\Git\bin\bash.exe');
end;

function NodeExePath(): String;
var
  InstallPath: String;
begin
  Result := '';
  if RegQueryStringValue(HKLM64, 'SOFTWARE\Node.js', 'InstallPath', InstallPath) then
  begin
    InstallPath := RemoveBackslashUnlessRoot(InstallPath);
    if FileExists(InstallPath + '\node.exe') then
    begin
      Result := InstallPath + '\node.exe';
      Exit;
    end;
  end;
  Result := FindUnder('\nodejs\node.exe');
end;

function NpmCmdPath(): String;
var
  NodePath: String;
begin
  Result := '';
  NodePath := NodeExePath();
  if NodePath <> '' then
    Result := ExtractFilePath(NodePath) + 'npm.cmd';
end;

{ Prefijo npm común a toda la máquina.

  `npm install -g` sin prefijo instala en el %APPDATA% del usuario que
  ejecuta npm. Como el instalador corre elevado, ese usuario es el
  administrador y el CLI quedaría fuera del PATH de quien después usa
  SAVI. Con un prefijo en ProgramData + esa ruta en el PATH del sistema,
  el CLI queda disponible para todas las cuentas del equipo. }
function NpmGlobalPrefix(): String;
begin
  Result := ExpandConstant('{commonappdata}\npm');
end;

{ `True` si ese `claude` arranca de verdad — no si el archivo está.

  El paquete de npm pesa 175 KB: lo único que trae es un `postinstall`
  (`node install.cjs`) que baja el binario real a `bin\claude.exe`. npm
  crea el shim ANTES de correr ese postinstall, así que un postinstall
  fallido deja un `claude.cmd` apuntando a un archivo que no existe, y
  el sistema contesta "no puede encontrar la ruta especificada".

  Chequeando existencia, ese equipo daba "CLI instalado": el instalador
  se salteaba la reinstalación y volver a instalar SAVI no lo arreglaba
  nunca. `--version` tarda menos de un segundo y es la diferencia entre
  saber que está y saber que sirve. }
function CliRuns(const CliPath: String): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/C ""' + CliPath + '" --version"',
                 '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

{ Detección del CLI de Claude.

  Replica el orden de búsqueda del SDK (`_find_cli` en
  claude_agent_sdk/_internal/transport/subprocess_cli.py): primero el
  PATH, después las rutas conocidas. Mirar solo las rutas de npm daba un
  falso negativo con el instalador NATIVO del CLI, que deja el binario en
  %USERPROFILE%\.local\bin\claude.exe — un equipo con el CLI andando
  perfecto se llevaba una instalación de Node y npm al pedo.

  Límite conocido: si IT eleva el instalador con una cuenta de
  administrador distinta de la del usuario final, USERPROFILE apunta al
  perfil equivocado y las rutas por-usuario no se ven. En ese caso se
  instala el CLI de más, que es el error barato de los dos. }
function ClaudeCliInstalled(): Boolean;
var
  Home, Found: String;
  Candidates: TArrayOfString;
  I: Integer;
begin
  Result := True;

  { 1. En el PATH — equivale al shutil.which() del SDK. }
  Found := FileSearch('claude.exe', GetEnv('PATH'));
  if (Found <> '') and CliRuns(Found) then
    Exit;
  Found := FileSearch('claude.cmd', GetEnv('PATH'));
  if (Found <> '') and CliRuns(Found) then
    Exit;

  { 2. Rutas conocidas, incluidas las del instalador nativo. }
  Home := GetEnv('USERPROFILE');
  SetArrayLength(Candidates, 8);
  Candidates[0] := NpmGlobalPrefix() + '\claude.cmd';
  Candidates[1] := ExpandConstant('{userappdata}\npm\claude.cmd');
  Candidates[2] := FindUnder('\nodejs\claude.cmd');
  Candidates[3] := Home + '\.local\bin\claude.exe';
  Candidates[4] := Home + '\.claude\local\claude.exe';
  Candidates[5] := Home + '\.npm-global\bin\claude.cmd';
  Candidates[6] := Home + '\node_modules\.bin\claude.cmd';
  Candidates[7] := Home + '\.yarn\bin\claude.cmd';

  for I := 0 to GetArrayLength(Candidates) - 1 do
    if FileExists(Candidates[I]) and CliRuns(Candidates[I]) then
      Exit;

  Result := False;
end;

{ `True` si ya hay una sesión de `claude login` en esta cuenta de Windows.

  El SDK cae acá cuando no encuentra ni CLAUDE_CODE_OAUTH_TOKEN ni
  ANTHROPIC_API_KEY (ver claude_agent_sdk/_internal/session_resume.py).
  Con esto detectado, un equipo donde alguien ya usó Claude Code no
  necesita que el instalador le pida nada: el subproceso se autentica
  solo. }
function ClaudeLoggedIn(): Boolean;
var
  ResultCode: Integer;
begin
  { Se consulta como el usuario que lanzó el instalador y no desde este
    proceso: si TI elevó con OTRA cuenta de administrador, GetEnv('USERPROFILE')
    apunta al perfil de ese administrador. El asistente decía "Sesión ya
    iniciada", saltaba el token, y el usuario final —que no tiene ningún
    ~/.claude— quedaba sin credencial. Es la misma comprobación de archivo de
    antes, delegada a cmd con ExecAsOriginalUser; el código de salida es la
    respuesta. Si no se puede ejecutar, se asume que NO hay sesión: lo
    peor que pasa es pedir un token que no hacía falta. }
  Result := ExecAsOriginalUser(ExpandConstant('{cmd}'),
    '/c if exist "%USERPROFILE%\.claude\.credentials.json" (exit 0) else (exit 1)',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

{ `Check` de la entrada de PATH: sin esto, reinstalar duplica la ruta. }
function NeedsPathEntry(): Boolean;
var
  CurrentPath: String;
begin
  if not RegQueryStringValue(HKLM,
      'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
      'Path', CurrentPath) then
  begin
    Result := True;
    Exit;
  end;
  Result := Pos(Lowercase(NpmGlobalPrefix()), Lowercase(CurrentPath)) = 0;
end;

procedure DetectPrerequisites();
begin
  NeedsGit := GitBashPath() = '';
  NeedsCli := not ClaudeCliInstalled();
  { Node.js NO es un requisito de SAVI: solo se usa para instalar el CLI
    con `npm install -g`. Si el CLI ya está (por ejemplo, puesto con el
    instalador nativo), Node no hace ninguna falta y bajarlo son 30 MB y
    varios minutos regalados. }
  NeedsNode := NeedsCli and (NodeExePath() = '');
  { Si ya hay sesión, el CLI se autentica solo y no hace falta pedir
    token ni clave. Las credenciales viven en el perfil del usuario, no
    junto al binario: da igual si el CLI se instala recién ahora. }
  AlreadyLoggedIn := ClaudeLoggedIn();
end;

{ Marcas de estado, en formato BGR (que es como Windows guarda TColor:
  al reves del #RRGGBB de la web — invertirlo da azules donde deberia
  haber rojos). }
const
  MarkOk      = $004AA316;  { verde  #16A34A }
  MarkMissing = $002626DC;  { rojo   #DC2626 }
  MarkNotNeeded = $007A7171; { gris  #71717A }

{ Una fila de la lista de requisitos: la marca coloreada y el texto.

  Se arma a mano en vez de usar CreateOutputMsgPage porque esa pagina es
  texto plano y no admite color: la unica forma de distinguir un
  requisito cumplido de uno faltante era escribir "[ OK ]" y "[ FALTA ]",
  que obliga a leer para entender algo que un tilde verde comunica de un
  vistazo. Es la primera pantalla que ve el tecnico. }
procedure AddPrereqRow(Page: TWizardPage; var Top: Integer;
                       const Mark: String; MarkColor: Integer; const Text: String);
var
  MarkLabel, TextLabel: TNewStaticText;
begin
  MarkLabel := TNewStaticText.Create(Page);
  MarkLabel.Parent := Page.Surface;
  MarkLabel.Left := ScaleX(4);
  MarkLabel.Top := Top;
  MarkLabel.AutoSize := True;
  MarkLabel.Font.Color := MarkColor;
  MarkLabel.Font.Style := [fsBold];
  MarkLabel.Caption := Mark;

  TextLabel := TNewStaticText.Create(Page);
  TextLabel.Parent := Page.Surface;
  TextLabel.Left := ScaleX(26);
  TextLabel.Top := Top;
  TextLabel.AutoSize := True;
  TextLabel.Caption := Text;

  Top := Top + ScaleY(21);
end;

procedure AddPrereqText(Page: TWizardPage; var Top: Integer; const Text: String; Gap: Integer);
var
  TextLabel: TNewStaticText;
begin
  Top := Top + ScaleY(Gap);
  TextLabel := TNewStaticText.Create(Page);
  TextLabel.Parent := Page.Surface;
  TextLabel.Left := 0;
  TextLabel.Top := Top;
  TextLabel.Width := Page.SurfaceWidth;
  TextLabel.WordWrap := True;
  TextLabel.AutoSize := True;
  TextLabel.Caption := Text;
  Top := Top + TextLabel.Height + ScaleY(4);
end;

procedure BuildPrereqPage(Page: TWizardPage);
var
  Top: Integer;
begin
  Top := 0;
  AddPrereqText(Page,
    Top,
    'SAVI necesita estos programas en el equipo para conectarse con la ' +
    'inteligencia artificial. El instalador descarga e instala los que falten.',
    0);
  Top := Top + ScaleY(10);

  if NeedsCli then
    AddPrereqRow(Page, Top, #$2715, MarkMissing, 'Componente de Claude — falta, se instala ahora')
  else
    AddPrereqRow(Page, Top, #$2713, MarkOk, 'Componente de Claude');

  if NeedsNode then
    AddPrereqRow(Page, Top, #$2715, MarkMissing,
                 'Node.js {#NodeVersion} — falta, se necesita para instalar el componente de Claude')
  else if NodeExePath() = '' then
    AddPrereqRow(Page, Top, #$2013, MarkNotNeeded,
                 'Node.js — no hace falta, el componente de Claude ya está instalado')
  else
    AddPrereqRow(Page, Top, #$2713, MarkOk, 'Node.js');

  if NeedsGit then
    AddPrereqRow(Page, Top, #$2715, MarkMissing,
                 'Git for Windows {#GitVersion} — falta, lo necesita el componente de Claude')
  else
    AddPrereqRow(Page, Top, #$2713, MarkOk, 'Git for Windows');

  if AlreadyLoggedIn then
    AddPrereqRow(Page, Top, #$2713, MarkOk,
                 'Sesión de Claude ya iniciada — no se va a pedir token ni clave');

  if NeedsNode or NeedsGit or NeedsCli then
    AddPrereqText(Page, Top,
      'Hace falta conexión a internet durante la instalación: la descarga puede ' +
      'superar los 150 MB.', 14)
  else
    AddPrereqText(Page, Top, 'Todo listo, no hay nada que descargar.', 14);
end;

function AuthPageDescription(): String;
begin
  if AlreadyLoggedIn then
    Result :=
      'Ya hay una sesión de Claude Code iniciada en este equipo: SAVI la va ' +
      'a usar automáticamente. Deje los dos campos vacíos salvo que quiera ' +
      'forzar una autenticación distinta.'
  else
    Result :=
      'SAVI usa la suscripción de Claude (Pro o Max) del cliente. Lo normal ' +
      'es dejar estos dos campos VACÍOS: al terminar la instalación se abre ' +
      'el navegador para iniciar sesión con esa cuenta, y no hay nada que ' +
      'copiar. Complete un campo solo si le entregaron la credencial ya ' +
      'generada. El puerto es el que usa SAVI en este equipo; cámbielo solo ' +
      'si ya está ocupado — está elegido para no chocar con nada.' + #13#10 +
      'Si el cliente usa Gemini u OpenAI en vez de Claude, deje estos campos ' +
      'vacíos y cargue la clave después en SAVI: Administración → Proveedores de IA.';
end;

{ `True` si en el directorio elegido ya hay una instalación configurada.

  Es lo que convierte a este mismo instalador en el mecanismo de
  actualización: al reinstalar sobre una versión previa, Inno resuelve
  `WizardDirValue` al directorio de la instalación existente (lo recuerda
  por el AppId), así que encontrar el .env ahí significa "esto es una
  actualización, no una instalación nueva".

  Sin esto, actualizar obliga a reescribir a mano el servidor del ERP,
  las dos contraseñas y el token de Claude, y pisa el .env que el cliente
  pueda haber ajustado. }
function IsConfigured(): Boolean;
begin
  Result := FileExists(AddBackslash(WizardDirValue) + '.env');
end;

{ `True` si el usuario pidió rehacer la configuración sobre una
  instalación existente.

  Sin esto no había forma de cambiar el servidor del ERP ni de pasar la
  base de SAVI de archivo local a PostgreSQL: `IsConfigured()` saltea las
  páginas justo para no pisar el .env, y eso dejaba encerrado al que
  necesitaba corregir un dato. Reusa el mismo asistente en vez de sumar
  una pantalla de configuración aparte. }
function WantsReconfigure(): Boolean;
begin
  Result := IsConfigured() and (ReconfigPage.SelectedValueIndex = 1);
end;

{ `True` cuando hay que preguntar la configuración: instalación nueva, o
  actualización en la que se pidió rehacerla. }
function MustAskConfig(): Boolean;
begin
  Result := (not IsConfigured()) or WantsReconfigure();
end;

{ `Check` de la casilla "Iniciar sesión con la cuenta de Claude".

  Solo se ofrece cuando de verdad falta la credencial: en una
  actualización el .env ya la trae, y si el técnico cargó un token o una
  clave en el asistente, o el equipo ya tiene sesión, no hay nada que
  hacer. Ofrecerlo igual invita a re-loguear sobre algo que funciona. }
function NeedsClaudeLogin(): Boolean;
begin
  // El diagnostico manda: si probo la credencial y no sirve, se ofrece
  // renovarla sea instalacion nueva o actualizacion.
  if AuthNeedsAttention then
  begin
    Result := True;
    Exit;
  end;
  Result := MustAskConfig() and (not AlreadyLoggedIn) and
            (Trim(ClaudePage.Values[0]) = '') and (Trim(ClaudePage.Values[1]) = '');
end;

{ ── Prueba de conexión ────────────────────────────────────────────── }

function IsValidPort(const Value: String): Boolean;
var
  Number: Integer;
begin
  { StrToIntDef y no Val: Pascal Script no expone Val. }
  Number := StrToIntDef(Value, -1);
  Result := (Number > 0) and (Number < 65536);
end;

{ `Which` nombra la base en los mensajes de error ("del ERP" / "de SAVI").
  No se llama Label: en Object Pascal es una palabra reservada. }
function ValidateDbPage(Page: TInputQueryWizardPage; const Which: String): Boolean;
begin
  Result := False;
  if Trim(Page.Values[0]) = '' then
  begin
    MsgBox('Indique el servidor de ' + Which + '.', mbError, MB_OK);
    Exit;
  end;
  if not IsValidPort(Trim(Page.Values[1])) then
  begin
    MsgBox('El puerto de ' + Which + ' tiene que ser un número entre 1 y 65535.', mbError, MB_OK);
    Exit;
  end;
  if Trim(Page.Values[2]) = '' then
  begin
    MsgBox('Indique el nombre de la base de datos de ' + Which + '.', mbError, MB_OK);
    Exit;
  end;
  if Trim(Page.Values[3]) = '' then
  begin
    MsgBox('Indique el usuario de ' + Which + '.', mbError, MB_OK);
    Exit;
  end;
  Result := True;
end;

{ >>> utilidades-env: este bloque se extrae tal cual para probarlo; no usar
  nada de afuera (ni constantes de Inno ni variables globales). }

const
  Base64UrlAlphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';

{ CSPRNG de Windows (RtlGenRandom). Se usa directo en vez de PowerShell: en
  equipos con PowerShell bloqueado (GPO, AppLocker, modo de lenguaje
  restringido) el generador devolvía vacío, el instalador escribía
  'CAMBIAR-ESTE-VALOR' y SAVI no arrancaba sin decir nada. }
function RtlGenRandom(RandomBuffer: AnsiString; RandomBufferLength: Cardinal): Boolean;
  external 'SystemFunction036@advapi32.dll stdcall';

{ Base64 URL-safe CON relleno '='. Es el formato de una clave Fernet: 32
  bytes dan exactamente 44 caracteres. }
function Base64UrlEncode(const Raw: AnsiString): String;
var
  I, N, B0, B1, B2, Triple: Integer;
begin
  Result := '';
  N := Length(Raw);
  I := 1;
  while I <= N do
  begin
    B0 := Ord(Raw[I]);
    if I + 1 <= N then B1 := Ord(Raw[I + 1]) else B1 := 0;
    if I + 2 <= N then B2 := Ord(Raw[I + 2]) else B2 := 0;
    Triple := (B0 * 65536) + (B1 * 256) + B2;
    Result := Result + Copy(Base64UrlAlphabet, ((Triple div 262144) mod 64) + 1, 1);
    Result := Result + Copy(Base64UrlAlphabet, ((Triple div 4096) mod 64) + 1, 1);
    if I + 1 <= N then
      Result := Result + Copy(Base64UrlAlphabet, ((Triple div 64) mod 64) + 1, 1)
    else
      Result := Result + '=';
    if I + 2 <= N then
      Result := Result + Copy(Base64UrlAlphabet, (Triple mod 64) + 1, 1)
    else
      Result := Result + '=';
    I := I + 3;
  end;
end;

{ `ByteCount` bytes aleatorios del sistema, en base64 URL-safe. Vacío si la
  API falla o devuelve ceros (no debería, pero un secreto nulo es peor que
  ninguno: el llamador cae al camino de PowerShell). }
function RandomBase64Url(ByteCount: Integer): String;
var
  Raw: AnsiString;
  I: Integer;
  AllZero: Boolean;
begin
  Result := '';
  try
    SetLength(Raw, ByteCount);
    if not RtlGenRandom(Raw, ByteCount) then
      Exit;
    AllZero := True;
    for I := 1 to ByteCount do
      if Ord(Raw[I]) <> 0 then
        AllZero := False;
    if AllZero then
      Exit;
    Result := Base64UrlEncode(Raw);
  except
    Result := '';
  end;
end;

{ Una clave Fernet válida: 44 caracteres del alfabeto URL-safe terminando
  en '='. Es la misma regla que valida Settings en el backend. }
function IsValidFernetKey(const Key: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  if (Length(Key) <> 44) or (Copy(Key, 44, 1) <> '=') then
    Exit;
  for I := 1 to 43 do
    if Pos(Copy(Key, I, 1), Base64UrlAlphabet) = 0 then
      Exit;
  Result := True;
end;

// Valor para el .env entre comillas simples.
//
// Sin comillas python-dotenv (que es lo que lee pydantic-settings) corta el
// valor en ' #', interpola dolar-llave-NOMBRE-llave, recorta los espacios de
// los bordes y descarta valores con comillas sueltas: una contrasena con
// cualquiera de esas cosas llegaba al ERP distinta de la que se probo en el
// asistente.
//
// Dentro de comillas simples solo existen dos escapes: la barra
// invertida doble (\\ vale \) y la comilla precedida de barra (\' vale '). La
// interpolacion, en cambio, dotenv la aplica TAMBIEN entre comillas simples
// y no tiene escape, asi que cada dolar-llave se parte con una variable
// inexistente cuyo valor por defecto es un dolar (SAVI_NO_DEFINIDA con
// default dolar): se lee igual que el original y no se vuelve a interpolar.
// El orden importa: primero las barras, despues las comillas. Es la misma
// regla que quote_env_value en backend/app/launcher.py.
function EnvQuote(const Value: String): String;
begin
  Result := Value;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '''', '\''', True);
  StringChangeEx(Result, '${', '${SAVI_NO_DEFINIDA:-$}{', True);
  Result := '''' + Result + '''';
end;

{ Inversa de EnvQuote para leer un valor del .env de una instalación
  anterior (solo se usa con la clave de cifrado, que no lleva `${`).
  Un valor sin comillas —un .env viejo o editado a mano— se devuelve tal cual. }
function EnvUnquote(const Raw: String): String;
var
  I, N: Integer;
  Current, Following: String;
begin
  Result := Raw;
  N := Length(Raw);
  if (N < 2) or (Copy(Raw, 1, 1) <> '''') then
    Exit;
  Result := '';
  I := 2;
  while I <= N do
  begin
    Current := Copy(Raw, I, 1);
    Following := Copy(Raw, I + 1, 1);
    if (Current = '\') and ((Following = '\') or (Following = '''')) then
    begin
      Result := Result + Following;
      I := I + 2;
    end
    else if Current = '''' then
      Exit
    else
    begin
      Result := Result + Current;
      I := I + 1;
    end;
  end;
end;

{ <<< utilidades-env }

{ Valor de una clave del .env (vacío si no está), sin las comillas. }
function ReadEnvValue(const Path, Key: String): String;
var
  Lines: TArrayOfString;
  I: Integer;
begin
  Result := '';
  if not LoadStringsFromFile(Path, Lines) then
    Exit;
  for I := 0 to GetArrayLength(Lines) - 1 do
    if Pos(Key + '=', Lines[I]) = 1 then
    begin
      Result := EnvUnquote(Trim(Copy(Lines[I], Length(Key) + 2, MaxInt)));
      Exit;
    end;
end;

{ La clave de cifrado de la instalación anterior, si la hay y es real.
  Al reconfigurar se reutiliza: con una nueva, las credenciales que ya
  guarda la base de SAVI (bases del ERP, proveedores de IA) dejaban de
  poder leerse.

  "Real" es una clave Fernet válida: el marcador 'CAMBIAR-ESTE-VALOR' o
  una clave rota no sirven para descifrar nada, así que reutilizarlas solo
  perpetuaría el arranque fallido. }
function ExistingCredentialsKey(): String;
begin
  Result := '';
  if not IsConfigured() then
    Exit;
  Result := ReadEnvValue(AddBackslash(WizardDirValue) + '.env', 'ERP_CREDENTIALS_KEY');
  if not IsValidFernetKey(Result) then
    Result := '';
end;

function PageSignature(Page: TInputQueryWizardPage; const Kind: String): String;
begin
  Result := Kind + #1 + Trim(Page.Values[0]) + #1 + Trim(Page.Values[1]) + #1 +
            Trim(Page.Values[2]) + #1 + Trim(Page.Values[3]) + #1 + Page.Values[4];
end;

// ── SAVI Cloud ───────────────────────────────────────────────────────
//
// El token (svk_enr_...) es un secreto de un solo uso. Reglas de este
// instalador: nunca se pasa a Log(), a un MsgBox ni a la línea de comandos
// de un proceso; solo viaja al .env (entre comillas, con EnvQuote) y, una
// vez canjeado, SAVI vacía esa variable.
function CloudUrl(): String;
begin
  Result := Trim('{#SaviCloudUrl}');
end;

// La página solo existe si el build trae la URL de SAVI Cloud.
function CloudAvailable(): Boolean;
begin
  Result := CloudUrl() <> '';
end;

// Formato: prefijo svk_enr_, algo después del prefijo, sin espacios y como
// mucho 256 caracteres (el límite del API de administración).
function CloudRequired(): Boolean;
begin
  Result := ({#SaviCloudRequired} = 1) and CloudAvailable();
end;

function IsValidCloudToken(const Token: String): Boolean;
begin
  Result := (Length(Token) > Length('svk_enr_')) and (Length(Token) <= 256) and
            (Copy(Token, 1, Length('svk_enr_')) = 'svk_enr_') and
            (Pos(' ', Token) = 0) and (Pos(#9, Token) = 0);
end;

{ Corre savi-dbcheck.exe con los datos de la página. Los datos van en un
  archivo y no en la línea de comandos para que la contraseña no quede
  visible en la lista de procesos; se borra apenas termina. }
procedure RunDbCheck(Page: TInputQueryWizardPage; const Kind: String;
  var Level, Message: String);
var
  Request: TArrayOfString;
  RequestPath, ResultPath, Raw, NewKey: String;
  RawAnsi: AnsiString;
  Code, Separator: Integer;
begin
  Level := 'error';
  Message := 'No se pudo ejecutar la prueba de conexión.';
  if not DbCheckExtracted then
  begin
    ExtractTemporaryFile('savi-dbcheck.exe');
    DbCheckExtracted := True;
  end;
  RequestPath := ExpandConstant('{tmp}\dbcheck-pedido.txt');
  ResultPath  := ExpandConstant('{tmp}\dbcheck-resultado.txt');
  DeleteFile(ResultPath);

  if ExistingCredentialsKey() <> '' then
    NewKey := '0'
  else
    NewKey := '1';
  SetArrayLength(Request, 7);
  Request[0] := Kind;
  Request[1] := Trim(Page.Values[0]);
  Request[2] := Trim(Page.Values[1]);
  Request[3] := Trim(Page.Values[2]);
  Request[4] := Trim(Page.Values[3]);
  Request[5] := Page.Values[4];
  Request[6] := NewKey;
  SaveStringsToUTF8File(RequestPath, Request, False);
  try
    Exec(ExpandConstant('{tmp}\savi-dbcheck.exe'),
         AddQuotes(RequestPath) + ' ' + AddQuotes(ResultPath),
         '', SW_HIDE, ewWaitUntilTerminated, Code);
  finally
    DeleteFile(RequestPath);
  end;

  { El resultado viene en ANSI: primera línea el nivel, después el mensaje. }
  if LoadStringFromFile(ResultPath, RawAnsi) then
  begin
    Raw := String(RawAnsi);
    Separator := Pos(#10, Raw);
    if Separator > 0 then
    begin
      Level := Trim(Copy(Raw, 1, Separator - 1));
      Message := Trim(Copy(Raw, Separator + 1, MaxInt));
    end;
  end;
  DeleteFile(ResultPath);
end;

{ Prueba la conexión de la página. `FromNext`: la llama "Siguiente", que
  deja seguir igual si el técnico lo confirma (el servidor puede no estar
  alcanzable desde este equipo al instalar); el botón solo informa.
  Devuelve si se puede avanzar. }
function TestDbPage(Page: TInputQueryWizardPage; const Kind, Which: String;
  FromNext: Boolean; var LastOk: String): Boolean;
var
  Level, Message, Signature: String;
begin
  Result := False;
  if not ValidateDbPage(Page, Which) then
    Exit;
  Signature := PageSignature(Page, Kind);
  if FromNext and (Signature = LastOk) then
  begin
    Result := True;
    Exit;
  end;

  WizardForm.NextButton.Enabled := False;
  WizardForm.BackButton.Enabled := False;
  try
    RunDbCheck(Page, Kind, Level, Message);
  finally
    WizardForm.NextButton.Enabled := True;
    WizardForm.BackButton.Enabled := True;
  end;

  if Level = 'ok' then
  begin
    LastOk := Signature;
    if not FromNext then
      MsgBox('Conexión correcta con la base de ' + Which + '.' + #13#10#13#10 + Message,
             mbInformation, MB_OK);
    Result := True;
  end
  else if Level = 'aviso' then
  begin
    if FromNext then
      Result := MsgBox(Message + #13#10#13#10 + '¿Continuar con estos datos?',
                       mbConfirmation, MB_YESNO) = IDYES
    else
      MsgBox(Message, mbInformation, MB_OK);
  end
  else
  begin
    if FromNext then
      Result := MsgBox('No se pudo conectar a la base de ' + Which + '.' + #13#10#13#10 +
                       Message + #13#10#13#10 +
                       'SAVI no va a funcionar hasta corregirlo. ¿Continuar igual?',
                       mbError, MB_YESNO or MB_DEFBUTTON2) = IDYES
    else
      MsgBox('No se pudo conectar a la base de ' + Which + '.' + #13#10#13#10 + Message,
             mbError, MB_OK);
  end;
end;

procedure ErpTestButtonClick(Sender: TObject);
begin
  TestDbPage(ErpPage, 'erp', 'el ERP', False, LastOkErp);
end;

procedure AgentTestButtonClick(Sender: TObject);
begin
  TestDbPage(AgentPgPage, 'savi', 'SAVI', False, LastOkAgent);
end;

{ Botón "Probar conexión" en la fila de la contraseña: debajo no entra en
  la página sin que aparezca una barra de desplazamiento. }
function CreateTestButton(Page: TInputQueryWizardPage): TNewButton;
var
  Password: TPasswordEdit;
begin
  Password := Page.Edits[4];
  Result := TNewButton.Create(Page);
  Result.Parent := Page.Surface;
  Result.Caption := 'Probar conexión';
  Result.Width := ScaleX(120);
  Result.Height := Password.Height + ScaleY(2);
  Result.Top := Password.Top - ScaleY(1);
  Result.Left := Password.Left + Password.Width - Result.Width;
  Password.Width := Password.Width - Result.Width - ScaleX(8);
end;

{ Al reconfigurar, las páginas arrancan con lo que ya tiene el .env: quien
  solo quiere cambiar el nombre de una base no tiene por qué conocer de
  nuevo servidores, usuarios ni contraseñas. Un valor vacío deja el
  predeterminado de la página. }
var
  ConfigPrefilled: Boolean;
  PreviousAdminLogins: String;

procedure PrefillValue(Page: TInputQueryWizardPage; Index: Integer; const EnvPath, Key: String);
var
  Value: String;
begin
  Value := ReadEnvValue(EnvPath, Key);
  if Value <> '' then
    Page.Values[Index] := Value;
end;

procedure PrefillFromEnv();
var
  EnvPath: String;
begin
  if ConfigPrefilled then
    Exit;
  ConfigPrefilled := True;
  EnvPath := AddBackslash(WizardDirValue) + '.env';

  PrefillValue(ErpPage, 0, EnvPath, 'ERP_DB_HOST');
  PrefillValue(ErpPage, 1, EnvPath, 'ERP_DB_PORT');
  PrefillValue(ErpPage, 2, EnvPath, 'ERP_DB_NAME');
  PrefillValue(ErpPage, 3, EnvPath, 'ERP_DB_USER');
  PrefillValue(ErpPage, 4, EnvPath, 'ERP_DB_PASSWORD');

  if ReadEnvValue(EnvPath, 'AGENT_DB_ENGINE') = 'sqlite' then
    AgentKindPage.SelectedValueIndex := 0
  else if ReadEnvValue(EnvPath, 'AGENT_DB_ENGINE') = 'postgresql' then
    AgentKindPage.SelectedValueIndex := 1;

  PrefillValue(AgentPgPage, 0, EnvPath, 'AGENT_DB_HOST');
  PrefillValue(AgentPgPage, 1, EnvPath, 'AGENT_DB_PORT');
  PrefillValue(AgentPgPage, 2, EnvPath, 'AGENT_DB_NAME');
  PrefillValue(AgentPgPage, 3, EnvPath, 'AGENT_DB_USER');
  PrefillValue(AgentPgPage, 4, EnvPath, 'AGENT_DB_PASSWORD');

  PrefillValue(ClaudePage, 0, EnvPath, 'CLAUDE_CODE_OAUTH_TOKEN');
  PrefillValue(ClaudePage, 1, EnvPath, 'ANTHROPIC_API_KEY');
  PrefillValue(ClaudePage, 2, EnvPath, 'APP_PORT');
  PreviousAdminLogins := ReadEnvValue(EnvPath, 'SAVI_ADMIN_LOGINS');
end;

{ ── Páginas del asistente ───────────────────────────────────────────── }

procedure InitializeWizard();
begin
  DetectPrerequisites();

  PrereqPage := CreateCustomPage(wpLicense,
    'Requisitos del sistema',
    'Componentes que SAVI necesita para funcionar');
  BuildPrereqPage(PrereqPage);

  ReconfigPage := CreateInputOptionPage(wpSelectDir,
    'Configuración existente',
    'Este equipo ya tiene SAVI configurado',
    'Se detectó un archivo de configuración de una instalación anterior. ' +
    'Puede conservarlo o cambiar solo lo que necesite: las pantallas siguientes ' +
    'traen los datos actuales ya cargados.',
    True, False);
  ReconfigPage.Add('Conservar la configuración actual (recomendado)');
  ReconfigPage.Add('Modificar la configuración: bases de datos, autenticación y puerto');
  ReconfigPage.SelectedValueIndex := 0;

  ErpPage := CreateInputQueryPage(ReconfigPage.ID,
    'Base de datos del ERP',
    'Datos que SAVI va a consultar e interpretar',
    'SAVI abre esta base en modo solo lectura. Es obligatoria: sin ella el ' +
    'asistente no puede responder sobre los datos de la empresa.');
  ErpPage.Add('Servidor:',   False);
  ErpPage.Add('Puerto:',     False);
  ErpPage.Add('Base de datos:', False);
  ErpPage.Add('Usuario:',    False);
  ErpPage.Add('Contraseña:', True);
  ErpPage.Values[1] := '5432';

  AgentKindPage := CreateInputOptionPage(ErpPage.ID,
    'Base de datos de SAVI',
    'Dónde se guardan las conversaciones y los mensajes',
    'Es la base del asistente, no la del ERP: guarda el historial, las sesiones, ' +
    'los proveedores de IA y los documentos de la empresa. Con archivo local SAVI ' +
    'atiende bien a UN usuario a la vez: si varios chatean al mismo tiempo, las ' +
    'respuestas se traban o fallan, y el historial queda solo en este equipo.',
    True, False);
  { El orden de los índices no cambia (0 = archivo local, 1 = PostgreSQL):
    lo usan ShouldSkipPage y WriteEnvFile. }
  AgentKindPage.Add('Archivo local — solo para pruebas o un único usuario en este equipo');
  AgentKindPage.Add('Servidor PostgreSQL (recomendado) — varios usuarios, historial compartido y con respaldo');
  AgentKindPage.SelectedValueIndex := 1;

  AgentPgPage := CreateInputQueryPage(AgentKindPage.ID,
    'PostgreSQL de SAVI',
    'Conexión al servidor donde vive el historial',
    'Si la base no existe, SAVI la crea (el usuario necesita permiso para crear ' +
    'bases). Si ya tiene datos de SAVI, se conservan: nunca se borra nada.');
  AgentPgPage.Add('Servidor:',   False);
  AgentPgPage.Add('Puerto:',     False);
  AgentPgPage.Add('Base de datos:', False);
  AgentPgPage.Add('Usuario:',    False);
  AgentPgPage.Add('Contraseña:', True);
  AgentPgPage.Values[1] := '5432';
  AgentPgPage.Values[2] := 'savi';

  ErpTestButton := CreateTestButton(ErpPage);
  ErpTestButton.OnClick := @ErpTestButtonClick;
  AgentTestButton := CreateTestButton(AgentPgPage);
  AgentTestButton.OnClick := @AgentTestButtonClick;

  ClaudePage := CreateInputQueryPage(AgentPgPage.ID,
    'Cuenta de Claude y puerto',
    'Gemini y OpenAI se configuran después, desde SAVI',
    AuthPageDescription());
  ClaudePage.Add('Token de Claude (opcional; lo genera el cliente con: claude setup-token):', True);
  ClaudePage.Add('Clave de API de Claude (opcional; alternativa al token):', True);
  ClaudePage.Add('Puerto local:', False);
  ClaudePage.Values[2] := '{#DefaultPort}';

  if CloudRequired() then
    CloudPage := CreateInputQueryPage(ClaudePage.ID,
      'Conectar con SAVI Cloud',
      'Obligatorio: esta instalación la administra SEO Group',
      'Pegue el token de vinculación que le entregó SEO Group. Sin él no se ' +
      'puede continuar: así cada equipo queda registrado y SEO Group puede ' +
      'brindarle soporte y administrar su acceso.')
  else
    CloudPage := CreateInputQueryPage(ClaudePage.ID,
      'Conectar con SAVI Cloud',
      'Opcional: vincular esta instalación con SEO Group',
      'Se lo entrega SEO Group. Puede hacerlo después desde Administración.' + #13#10#13#10 +
      'Si tiene el token de vinculación, péguelo aquí. Si lo deja vacío, no se ' +
      'conecta nada ahora.');
  CloudPage.Add('Token de vinculación (empieza con svk_enr_):', True);

  DownloadPage := CreateDownloadPage(
    SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), nil);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  { La página que ofrece reconfigurar solo tiene sentido si ya hay algo
    configurado. }
  if PageID = ReconfigPage.ID then
  begin
    Result := not IsConfigured();
    Exit;
  end;

  { En una actualización no se pregunta nada, salvo que se haya pedido
    rehacer la configuración en la página anterior. }
  if (not MustAskConfig()) and ((PageID = ErpPage.ID) or (PageID = AgentKindPage.ID) or
                                (PageID = AgentPgPage.ID) or (PageID = ClaudePage.ID) or
                                (PageID = CloudPage.ID)) then
  begin
    Result := True;
    Exit;
  end;

  { Los accesos directos ya existen de la instalación previa; volver a
    preguntar por ellos es ruido en lo que debería ser Siguiente-Siguiente. }
  if (PageID = wpSelectTasks) and IsConfigured() then
  begin
    Result := True;
    Exit;
  end;

  { Sin URL de SAVI Cloud en el build no hay a dónde vincular: no se muestra. }
  if (PageID = CloudPage.ID) and (not CloudAvailable()) then
  begin
    Result := True;
    Exit;
  end;

  { La página de PostgreSQL solo aplica si se eligió esa opción. }
  Result := (PageID = AgentPgPage.ID) and (AgentKindPage.SelectedValueIndex = 0);
end;

{ Aviso en la página de confirmación: sin esto, una actualización pasa de
  largo las cuatro páginas de configuración y el usuario no tiene forma de
  saber si su configuración se conserva o se está por perder. }
function UpdateReadyMemo(const Space, NewLine, MemoUserInfoInfo, MemoDirInfo,
  MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := MemoDirInfo;
  if MemoTasksInfo <> '' then
    Result := Result + NewLine + NewLine + MemoTasksInfo;
  if WantsReconfigure() then
    Result := Result + NewLine + NewLine +
      'Reconfiguración:' + NewLine +
      Space + 'Se reemplaza el archivo .env con los datos que se cargaron' + NewLine +
      Space + 'El anterior queda como .env.anterior por si hay que volver' + NewLine +
      Space + 'Se cierran las sesiones abiertas (cambia la clave de firma)' + NewLine +
      Space + 'Se conservan los datos y la clave de cifrado: nada se borra'
  else if IsConfigured() then
    Result := Result + NewLine + NewLine +
      'Actualización:' + NewLine +
      Space + 'Se conserva la configuración actual (archivo .env)' + NewLine +
      Space + 'Se conservan las conversaciones y el historial'
  else
    Result := Result + NewLine + NewLine +
      'Configuración:' + NewLine +
      Space + 'Se va a generar el archivo .env con los datos ingresados';
end;

{ ── Validación ──────────────────────────────────────────────────────── }

function DownloadPrerequisites(): Boolean;
begin
  Result := True;
  if not (NeedsNode or NeedsGit) then
    Exit;

  DownloadPage.Clear;
  if NeedsNode then
    DownloadPage.Add('{#NodeUrl}', 'node-setup.msi', '');
  if NeedsGit then
    DownloadPage.Add('{#GitUrl}', 'git-setup.exe', '');

  DownloadPage.Show;
  try
    try
      DownloadPage.Download;
    except
      MsgBox('No se pudieron descargar los componentes necesarios.' + #13#10#13#10 +
             GetExceptionMessage + #13#10#13#10 +
             'Revise la conexión a internet y vuelva a intentar.', mbCriticalError, MB_OK);
      Result := False;
    end;
  finally
    DownloadPage.Hide;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  if (CurPageID = ReconfigPage.ID) and WantsReconfigure() then
    PrefillFromEnv()

  else if CurPageID = ErpPage.ID then
    Result := TestDbPage(ErpPage, 'erp', 'el ERP', True, LastOkErp)

  else if (CurPageID = AgentKindPage.ID) and (AgentKindPage.SelectedValueIndex = 0) then
    Result := MsgBox('Eligió guardar los datos de SAVI en un archivo local.' + #13#10#13#10 +
                     'Sirve para pruebas o para un único usuario: si varias personas ' +
                     'usan el chat al mismo tiempo, las respuestas se traban o fallan, ' +
                     'y el historial queda solo en este equipo, sin respaldo del servidor.' + #13#10#13#10 +
                     'Para el uso normal en una empresa, elija PostgreSQL.' + #13#10#13#10 +
                     '¿Seguir con archivo local?',
                     mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES

  else if CurPageID = AgentPgPage.ID then
    Result := TestDbPage(AgentPgPage, 'savi', 'SAVI', True, LastOkAgent)

  else if CurPageID = ClaudePage.ID then
  begin
    { Dejar los dos campos vacíos es una opción válida, no un error: el
      caso normal es que el cliente ponga su propia suscripción y la
      autenticación se resuelva al terminar, en el navegador. Se pregunta
      igual porque seguir de largo sin credencial y sin saberlo termina en
      un SAVI instalado que no responde. }
    if (not AlreadyLoggedIn) and (Trim(ClaudePage.Values[0]) = '') and
       (Trim(ClaudePage.Values[1]) = '') then
    begin
      Result := MsgBox('No cargó ningún token ni clave de API.' + #13#10#13#10 +
                       'Al terminar la instalación se le va a ofrecer iniciar ' +
                       'sesión con la cuenta de Claude del cliente, que es la ' +
                       'forma recomendada.' + #13#10#13#10 +
                       '¿Continuar así?', mbConfirmation, MB_YESNO) = IDYES;
    end;

    if Result and (not IsValidPort(Trim(ClaudePage.Values[2]))) then
    begin
      MsgBox('El puerto tiene que ser un número entre 1 y 65535.', mbError, MB_OK);
      Result := False;
    end;
  end

  else if CurPageID = CloudPage.ID then
  begin
    { En el build obligatorio el token no puede faltar. En el resto, vacío es
      válido: se vincula después desde Administración. El mensaje no repite el
      token que se escribió. }
    if CloudRequired() and (Trim(CloudPage.Values[0]) = '') then
    begin
      MsgBox('Este instalador requiere el token de vinculación que le entregó ' +
             'SEO Group. Pídalo a soporte y péguelo para continuar.',
             mbError, MB_OK);
      Result := False;
    end
    else if (Trim(CloudPage.Values[0]) <> '') and
       (not IsValidCloudToken(Trim(CloudPage.Values[0]))) then
    begin
      MsgBox('El token no tiene el formato esperado: tiene que empezar con ' +
             'svk_enr_ y no llevar espacios. Revise que esté completo o deje ' +
             'el campo vacío para hacerlo después desde Administración.',
             mbError, MB_OK);
      Result := False;
    end;
  end

  else if CurPageID = wpReady then
    Result := DownloadPrerequisites();
end;

{ ── Instalación de los prerrequisitos ───────────────────────────────── }

{ Pone el directorio de Node.js en el PATH de ESTE proceso.

  El instalador heredó su entorno de Explorer al arrancar, o sea antes de
  instalar Node: `C:\Program Files\nodejs` no está ahí, y todo proceso
  hijo hereda ese PATH viejo. `npm.cmd` se salva porque encuentra
  `node.exe` al lado suyo con %~dp0, pero el `postinstall` del CLI corre
  `cmd /c node install.cjs`, y ahí `node` se resuelve por PATH: muere con
  "'node' no se reconoce como un comando", npm corta con código 1 y el
  paquete queda a medio instalar — con el shim creado y sin el binario.

  Por eso la instalación fallaba SIEMPRE en un equipo limpio y nunca en
  uno que ya tenía Node. }
procedure PutNodeOnPath();
var
  NodeDir: String;
begin
  NodeDir := ExtractFileDir(NodeExePath());
  if (NodeDir <> '') and (Pos(Lowercase(NodeDir), Lowercase(GetEnv('PATH'))) = 0) then
    SetEnvVar('PATH', NodeDir + ';' + GetEnv('PATH'));
end;

{ Corre `npm install -g` del CLI de Claude Code.

  Va por cmd.exe y no por Exec directo: npm.cmd es un archivo por lotes y
  CreateProcess —lo que usa Exec— no puede ejecutarlo, falla con "no es
  una aplicación Win32 válida" antes de que npm llegue a correr. El
  síntoma es que la instalación del CLI falla siempre, haya Node o no.

  La salida va a un log porque "falló con código N" no alcanza para
  diagnosticar nada en el equipo de un cliente. }
function RunNpmInstall(const NpmCmd, LogPath: String; var ResultCode: Integer): Boolean;
var
  CommandLine: String;
begin
  { Comillas dobles alrededor de todo: cmd /C descarta el primer y el
    último par, y adentro hacen falta las de cada ruta con espacios. }
  CommandLine := '/C ""' + NpmCmd + '" install -g --prefix "' + NpmGlobalPrefix() +
                 '" @anthropic-ai/claude-code > "' + LogPath + '" 2>&1"';
  Result := Exec(ExpandConstant('{cmd}'), CommandLine, '', SW_HIDE,
                 ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

procedure InstallPrerequisites();
var
  ResultCode: Integer;
  NpmCmd, LogPath: String;
begin
  if NeedsNode then
  begin
    WizardForm.StatusLabel.Caption := 'Instalando Node.js...';
    if not Exec('msiexec.exe',
                '/i "' + ExpandConstant('{tmp}\node-setup.msi') + '" /qn /norestart',
                '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      MsgBox('La instalación de Node.js falló (código ' + IntToStr(ResultCode) + ').' + #13#10 +
             'SAVI se va a instalar igual, pero no va a poder responder hasta que ' +
             'Node.js esté disponible.', mbError, MB_OK);
  end;

  if NeedsGit then
  begin
    WizardForm.StatusLabel.Caption := 'Instalando Git for Windows...';
    if not Exec(ExpandConstant('{tmp}\git-setup.exe'),
                '/VERYSILENT /NORESTART /NOCANCEL /SP-', '', SW_HIDE,
                ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      MsgBox('La instalación de Git for Windows falló (código ' + IntToStr(ResultCode) + ').' + #13#10 +
             'SAVI necesita su bash.exe para funcionar.', mbError, MB_OK);
  end;

  { Solo si falta de verdad: `NeedsCli` ya contempla el PATH y las rutas
    del instalador nativo, así que no hace falta reinstalarlo por las
    dudas cuando se acaba de poner Node. }
  if NeedsCli then
  begin
    WizardForm.StatusLabel.Caption := 'Instalando el componente de Claude...';
    PutNodeOnPath();
    { Por ruta completa y no por nombre: si Node acaba de instalarse, el
      PATH de este proceso todavía no lo incluye. }
    NpmCmd := NpmCmdPath();
    LogPath := ExpandConstant('{app}\npm-claude-cli.log');
    if NpmCmd = '' then
      MsgBox('No se encontró npm después de instalar Node.js. ' +
             'Instale el CLI a mano con: npm install -g @anthropic-ai/claude-code',
             mbError, MB_OK)
    else
    begin
      { De cero y no encima. npm vuelve a correr el postinstall aunque
        el paquete ya esté —comprobado—, así que esto no es lo que
        destraba la reinstalación; es el cinturón: un intento anterior
        pudo dejar el árbol a medio extraer, y arrancar limpio saca de la
        ecuación esa familia de estados raros. Acá sólo se llega si no hay
        ningún CLI que ande, así que no hay nada bueno que borrar. }
      DelTree(NpmGlobalPrefix() + '\node_modules\@anthropic-ai\claude-code',
              True, True, True);
      if not RunNpmInstall(NpmCmd, LogPath, ResultCode) then
        MsgBox('La instalación del CLI de Claude Code falló (código ' + IntToStr(ResultCode) + ').' + #13#10 +
               'Detalle en: ' + LogPath + #13#10#13#10 +
               'Instálelo a mano con: npm install -g @anthropic-ai/claude-code',
               mbError, MB_OK);
    end;
  end;
end;

{ ── Generación del .env ─────────────────────────────────────────────── }

{ El JWT_SECRET firma las sesiones, así que no puede salir del generador
  pseudoaleatorio de Inno. Primero se usa el CSPRNG de Windows directo
  (RandomBase64Url, sin depender de PowerShell); solo si eso falla se
  delega en el RNG criptográfico de .NET, que se lee por archivo temporal
  porque Exec no captura la salida estándar. }
function GenerateJwtSecret(): String;
var
  ScriptPath, OutputPath: String;
  Script, Output: TArrayOfString;
  ResultCode: Integer;
begin
  Result := RandomBase64Url(48);
  if Result <> '' then
    Exit;

  OutputPath := ExpandConstant('{tmp}\jwt.txt');
  ScriptPath := ExpandConstant('{tmp}\jwt.ps1');

  SetArrayLength(Script, 4);
  Script[0] := '$bytes = New-Object byte[] 48';
  Script[1] := '$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()';
  Script[2] := '$rng.GetBytes($bytes)';
  Script[3] := '[Convert]::ToBase64String($bytes) | Out-File -FilePath "' +
               OutputPath + '" -Encoding ascii -NoNewline';

  if not SaveStringsToFile(ScriptPath, Script, False) then
    Exit;

  if Exec('powershell.exe',
          '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '"',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0) then
    if LoadStringsFromFile(OutputPath, Output) and (GetArrayLength(Output) > 0) then
      Result := Trim(Output[0]);

  DeleteFile(ScriptPath);
  DeleteFile(OutputPath);
end;

{ La clave de cifrado de las credenciales del ERP (ERP_CREDENTIALS_KEY)
  es una clave Fernet: 32 bytes en base64 URL-SAFE (con '-' y '_' en vez
  de '+' y '/'), a diferencia del JWT_SECRET que usa base64 estándar.
  Fernet valida el alfabeto, así que la diferencia no es cosmética.

  Perderla o cambiarla deja ilegibles TODAS las contraseñas de conexión
  guardadas; por eso se genera una sola vez por instalación, igual que el
  JWT_SECRET, y hay que preservarla en una reinstalación. }
function GenerateFernetKey(): String;
var
  ScriptPath, OutputPath: String;
  Script, Output: TArrayOfString;
  ResultCode: Integer;
begin
  { Mismo orden que el JWT: API de Windows primero, PowerShell de respaldo.
    Con 32 bytes RandomBase64Url da justo 44 caracteres con '=' final. }
  Result := RandomBase64Url(32);
  if IsValidFernetKey(Result) then
    Exit;

  Result := '';
  OutputPath := ExpandConstant('{tmp}\fernet.txt');
  ScriptPath := ExpandConstant('{tmp}\fernet.ps1');

  SetArrayLength(Script, 5);
  Script[0] := '$bytes = New-Object byte[] 32';
  Script[1] := '$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()';
  Script[2] := '$rng.GetBytes($bytes)';
  Script[3] := '$b64 = [Convert]::ToBase64String($bytes).Replace(''+'',''-'').Replace(''/'',''_'')';
  Script[4] := '$b64 | Out-File -FilePath "' + OutputPath + '" -Encoding ascii -NoNewline';

  if not SaveStringsToFile(ScriptPath, Script, False) then
    Exit;

  if Exec('powershell.exe',
          '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '"',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0) then
    if LoadStringsFromFile(OutputPath, Output) and (GetArrayLength(Output) > 0) then
      Result := Trim(Output[0]);

  DeleteFile(ScriptPath);
  DeleteFile(OutputPath);
end;

{ Reemplaza un marcador en todas las líneas de la plantilla. Se trabaja
  por líneas porque Inno no expone un cargador de archivo completo que
  respete Unicode; ningún marcador cruza saltos de línea. }
procedure ReplaceToken(var Lines: TArrayOfString; const Token, Value: String);
var
  I: Integer;
begin
  for I := 0 to GetArrayLength(Lines) - 1 do
    StringChangeEx(Lines[I], Token, Value, True);
end;

{ Igual que ReplaceToken pero para valores que escribe el usuario o que
  genera el instalador: los deja entre comillas simples con EnvQuote, para
  que el .env se lea de vuelta EXACTAMENTE igual (ver EnvQuote). Los
  marcadores de la plantilla van sin comillas, no las lleva el template. }
procedure ReplaceEnvToken(var Lines: TArrayOfString; const Token, Value: String);
begin
  ReplaceToken(Lines, Token, EnvQuote(Value));
end;

procedure WriteEnvFile();
var
  TemplatePath, EnvPath, Secret, FernetKey, PreviousKey: String;
  Lines: TArrayOfString;
  UseSqlite: Boolean;
begin
  TemplatePath := ExpandConstant('{app}\env.template');
  EnvPath      := ExpandConstant('{app}\.env');

  { Actualización: el .env es del cliente, no del instalador. Reescribirlo
    perdería los ajustes hechos a mano y regeneraría el JWT_SECRET, lo que
    invalida todas las sesiones abiertas.

    Contrapartida a tener presente en cada release: una clave nueva de
    env.template NO llega a las instalaciones existentes. Toda variable
    que se agregue tiene que tener default en Settings, o la actualización
    rompe el arranque en el equipo del cliente. }
  if FileExists(EnvPath) and (not WantsReconfigure()) then
    Exit;

  { Se pidió reconfigurar: copia de seguridad antes de pisar. Si el dato
    nuevo está mal, el anterior —que funcionaba— sigue a mano en vez de
    haberse perdido para siempre. }
  PreviousKey := ExistingCredentialsKey();
  if FileExists(EnvPath) then
    RenameFile(EnvPath, EnvPath + '.anterior');

  if not LoadStringsFromFile(TemplatePath, Lines) then
  begin
    MsgBox('No se pudo leer env.template. La instalación quedó incompleta: ' +
           'falta generar el archivo .env.', mbCriticalError, MB_OK);
    Exit;
  end;

  UseSqlite := AgentKindPage.SelectedValueIndex = 0;

  ReplaceEnvToken(Lines, '{{APP_PORT}}', Trim(ClaudePage.Values[2]));

  if UseSqlite then
  begin
    ReplaceEnvToken(Lines, '{{AGENT_DB_ENGINE}}', 'sqlite');
    { Vacío a propósito: la ruta se resuelve en runtime contra el
      %LOCALAPPDATA% de quien usa la aplicación, que no tiene por qué ser
      la cuenta con la que se instaló. }
    ReplaceEnvToken(Lines, '{{AGENT_DB_PATH}}',     '');
    ReplaceEnvToken(Lines, '{{AGENT_DB_HOST}}',     '');
    ReplaceEnvToken(Lines, '{{AGENT_DB_PORT}}',     '5432');
    ReplaceEnvToken(Lines, '{{AGENT_DB_USER}}',     '');
    ReplaceEnvToken(Lines, '{{AGENT_DB_PASSWORD}}', '');
    ReplaceEnvToken(Lines, '{{AGENT_DB_NAME}}',     '');
  end
  else
  begin
    ReplaceEnvToken(Lines, '{{AGENT_DB_ENGINE}}',   'postgresql');
    ReplaceEnvToken(Lines, '{{AGENT_DB_PATH}}',     '');
    ReplaceEnvToken(Lines, '{{AGENT_DB_HOST}}',     Trim(AgentPgPage.Values[0]));
    ReplaceEnvToken(Lines, '{{AGENT_DB_PORT}}',     Trim(AgentPgPage.Values[1]));
    ReplaceEnvToken(Lines, '{{AGENT_DB_NAME}}',     Trim(AgentPgPage.Values[2]));
    ReplaceEnvToken(Lines, '{{AGENT_DB_USER}}',     Trim(AgentPgPage.Values[3]));
    ReplaceEnvToken(Lines, '{{AGENT_DB_PASSWORD}}', AgentPgPage.Values[4]);
  end;

  ReplaceEnvToken(Lines, '{{ERP_DB_HOST}}',     Trim(ErpPage.Values[0]));
  ReplaceEnvToken(Lines, '{{ERP_DB_PORT}}',     Trim(ErpPage.Values[1]));
  ReplaceEnvToken(Lines, '{{ERP_DB_NAME}}',     Trim(ErpPage.Values[2]));
  ReplaceEnvToken(Lines, '{{ERP_DB_USER}}',     Trim(ErpPage.Values[3]));
  ReplaceEnvToken(Lines, '{{ERP_DB_PASSWORD}}', ErpPage.Values[4]);

  { Marca de tiempo nueva en cada instalación o reconfiguración. SAVI la
    compara con la guardada en la base default: si cambió, actualiza esa
    base con los ERP_DB_* de arriba; si no, no pisa lo que el administrador
    editó desde la aplicación. Una actualización que conserva el .env no
    llega hasta acá, así que la revisión tampoco cambia. }
  ReplaceEnvToken(Lines, '{{ERP_SEED_REVISION}}',
    GetDateTimeString('yyyymmddhhnnss', #0, #0));

  ReplaceEnvToken(Lines, '{{CLAUDE_CODE_OAUTH_TOKEN}}', Trim(ClaudePage.Values[0]));
  ReplaceEnvToken(Lines, '{{ANTHROPIC_API_KEY}}',        Trim(ClaudePage.Values[1]));
  ReplaceEnvToken(Lines, '{{GIT_BASH_PATH}}',            GitBashPath());

  Secret := GenerateJwtSecret();
  if Secret = '' then
  begin
    MsgBox('No se pudo generar la clave de firma de sesiones.' + #13#10 +
           'Edite JWT_SECRET en el archivo .env antes de usar SAVI.',
           mbError, MB_OK);
    Secret := 'CAMBIAR-ESTE-VALOR';
  end;
  ReplaceEnvToken(Lines, '{{JWT_SECRET}}', Secret);

  if PreviousKey <> '' then
    FernetKey := PreviousKey
  else
    FernetKey := GenerateFernetKey();
  if FernetKey = '' then
  begin
    MsgBox('No se pudo generar la clave de cifrado de credenciales del ERP.' + #13#10 +
           'Edite ERP_CREDENTIALS_KEY en el archivo .env antes de usar SAVI: genere una con ' + #13#10 +
           'python -c "from cryptography.fernet import Fernet; ' +
           'print(Fernet.generate_key().decode())"',
           mbError, MB_OK);
    FernetKey := 'CAMBIAR-ESTE-VALOR';
  end;
  ReplaceEnvToken(Lines, '{{ERP_CREDENTIALS_KEY}}', FernetKey);

  { Vacío en una instalación nueva; al reconfigurar se conserva el valor
    que se había completado a mano. Un administrador del ERP ya queda habilitado para
    la sección de administración por su propio flag. Este campo es el
    escape para dar acceso a un usuario que NO es admin en el ERP, y su
    valor es un `codigo` de Seguridad.Usuario — no el usuario de conexión
    a Postgres que se cargó en el asistente. Se completa a mano en el
    .env cuando hace falta. }
  ReplaceEnvToken(Lines, '{{SAVI_ADMIN_LOGINS}}', PreviousAdminLogins);

  { SAVI Cloud: solo si hay URL de build Y token. Campo vacío = no se
    escribe nada. Al arrancar, SAVI canjea el token y vacía la variable. }
  if CloudAvailable() and (Trim(CloudPage.Values[0]) <> '') then
  begin
    SetArrayLength(Lines, GetArrayLength(Lines) + 3);
    Lines[GetArrayLength(Lines) - 3] := '';
    Lines[GetArrayLength(Lines) - 2] := 'SAVI_CLOUD_URL=' + EnvQuote(CloudUrl());
    Lines[GetArrayLength(Lines) - 1] :=
      'SAVI_CLOUD_ENROLLMENT_TOKEN=' + EnvQuote(Trim(CloudPage.Values[0]));
  end;

  { Sin BOM: pydantic-settings lee el .env como UTF-8 y un BOM le
    convertiria la primera clave en "﻿APP_NAME". }
  if not SaveStringsToUTF8FileWithoutBOM(EnvPath, Lines, False) then
    MsgBox('No se pudo escribir ' + EnvPath, mbCriticalError, MB_OK);
end;

{ Corre el diagnóstico y avisa si algo quedó mal.

  Sin esto la instalación "termina bien" aunque el servidor del ERP esté
  mal escrito, y el error recién aparece cuando el cliente intenta entrar
  y recibe un 500 sin explicación. Verificarlo acá lo pone delante del
  técnico mientras todavía está sentado en el equipo y puede corregirlo.

  Con SW_HIDE y --report-file: el diagnóstico no abre el navegador; el
  instalador muestra el reporte en su propia ventana (ShowDiagnosticReport). }
function DiagnosticReportPath(): String;
begin
  Result := ExpandConstant('{commonappdata}\SAVI\diagnostico-instalacion.txt');
end;

{ Muestra el reporte del diagnóstico en una ventana del propio instalador.

  Antes el detalle quedaba solo en una página que se abría en el navegador:
  en un equipo de soporte con la asociación de .html rota, Windows mostraba
  "¿Cómo quieres abrir este archivo?", se cerraba sola, y el técnico se
  quedaba con un "hubo un error" sin saber cuál. Acá se lee siempre. }
procedure ShowDiagnosticReport(const Intro: String);
var
  Form: TSetupForm;
  Info: TNewStaticText;
  Memo: TNewMemo;
  CloseButton: TNewButton;
  RawAnsi: AnsiString;
  Text: String;
begin
  if LoadStringFromFile(DiagnosticReportPath(), RawAnsi) then
    Text := String(RawAnsi)
  else
    Text := 'No se encontró el reporte del diagnóstico. Abra el acceso directo ' +
            '"Diagnosticar SAVI" desde el menú Inicio para verlo.';

  Form := CreateCustomForm(ScaleX(620), ScaleY(420), False, False);
  try
    Form.Caption := 'Resultado de la verificación de SAVI';

    Info := TNewStaticText.Create(Form);
    Info.Parent := Form;
    Info.Left := ScaleX(12);
    Info.Top := ScaleY(12);
    Info.Width := Form.ClientWidth - ScaleX(24);
    Info.AutoSize := False;
    Info.WordWrap := True;
    Info.Height := ScaleY(48);
    Info.Caption := Intro;

    Memo := TNewMemo.Create(Form);
    Memo.Parent := Form;
    Memo.Left := ScaleX(12);
    Memo.Top := Info.Top + Info.Height + ScaleY(6);
    Memo.Width := Form.ClientWidth - ScaleX(24);
    Memo.Height := Form.ClientHeight - Memo.Top - ScaleY(23 + 24);
    Memo.ReadOnly := True;
    Memo.ScrollBars := ssVertical;
    Memo.WordWrap := True;
    Memo.Text := Text;

    CloseButton := TNewButton.Create(Form);
    CloseButton.Parent := Form;
    CloseButton.Caption := 'Cerrar';
    CloseButton.Width := ScaleX(90);
    CloseButton.Height := ScaleY(23);
    CloseButton.Left := Form.ClientWidth - CloseButton.Width - ScaleX(12);
    CloseButton.Top := Form.ClientHeight - ScaleY(23 + 12);
    CloseButton.ModalResult := mrOk;
    CloseButton.Default := True;
    CloseButton.Cancel := True;

    Form.ActiveControl := CloseButton;
    Form.FlipAndCenterIfNeeded(True, WizardForm, False);
    Form.ShowModal();
  finally
    Form.Free();
  end;
end;

procedure VerifyInstallation();
var
  ResultCode: Integer;
begin
  WizardForm.StatusLabel.Caption := 'Verificando la configuración...';
  { Como el usuario que lanzó el instalador (ExecAsOriginalUser) y no como
    el administrador que elevó: el diagnóstico mira ~/.claude y el perfil de
    quien ejecuta, y si TI elevó con otra cuenta revisaba el perfil de ese
    administrador mientras el usuario final no tenía nada. --no-pause porque
    corre oculto y esperando: sin él, un equipo sin navegador dejaba el
    instalador colgado en un "Enter para cerrar" que nadie veía. }
  if not ExecAsOriginalUser(ExpandConstant('{app}\{#AppExe}'),
              '--check-config --no-pause --report-file="' + DiagnosticReportPath() + '"', '', SW_HIDE,
              ewWaitUntilTerminated, ResultCode) then
  begin
    MsgBox('No se pudo ejecutar la verificación de la configuración.' + #13#10 +
           'Puede correrla después desde el acceso directo "Diagnosticar SAVI".',
           mbError, MB_OK);
    Exit;
  end;

  { Codigo 2 = problema de credencial. Se separa del resto porque el
    remedio es OTRO: reconfigurar el .env no renueva un token vencido, y
    mandar a reconfigurar cuando lo que hay que hacer es iniciar sesion
    hace perder el tiempo y desconfiar del reporte. }
  { Codigo 3 = fallan las dos cosas. Se prende la bandera igual que en el
    caso 2, y despues cae al mensaje de configuracion de abajo: sin esto
    el tecnico corregia el .env, reinstalaba, y recien en la segunda
    pasada descubria que tambien faltaba la credencial. }
  if ResultCode = 3 then
    AuthNeedsAttention := True;

  if ResultCode = 2 then
  begin
    AuthNeedsAttention := True;
    MsgBox('Falta renovar la credencial de Claude.' + #13#10#13#10 +
           'Todo lo demás quedó bien: las dos bases de datos responden. Lo único ' +
           'pendiente es iniciar sesión con la cuenta de Claude, o renovarla si ' +
           'venció.' + #13#10#13#10 +
           'Al terminar la instalación queda marcada la casilla para hacerlo. ' +
           'También puede hacerlo cuando quiera desde el acceso directo ' +
           '"Iniciar sesión en Claude".',
           mbInformation, MB_OK);
    Exit;
  end;

  if ResultCode <> 0 then
    ShowDiagnosticReport('SAVI quedó instalado, pero la verificación encontró problemas y ' +
                         'no va a funcionar hasta corregirlos. Abajo está qué falló y qué ' +
                         'hacer (las líneas [FALLA]). Para corregir los datos, vuelva a ' +
                         'ejecutar este instalador y elija "Modificar la configuración".');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    InstallPrerequisites();
    WriteEnvFile();
    VerifyInstallation();
  end;
end;
