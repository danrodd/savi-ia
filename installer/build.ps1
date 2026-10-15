<#
.SYNOPSIS
    Construye el instalador de escritorio de SAVI.

.DESCRIPTION
    Encadena los cuatro pasos del empaquetado:
      1. Compila el frontend Vue apuntando al mismo origen que el API.
      2. Lo deja en backend/frontend, que es de donde lo lee FastAPI.
      3. Empaqueta el backend con PyInstaller (modo onedir).
      4. Compila el instalador con Inno Setup.

    El resultado es installer/output/SAVI-Setup-<version>.exe

.PARAMETER SkipFrontend
    Reutiliza el build de Vue existente. Útil al iterar sobre el .iss.

.PARAMETER SkipInstaller
    Se detiene después de PyInstaller, sin compilar el .exe del instalador.

.PARAMETER SaviCloudUrl
    URL base de SAVI Cloud que el instalador escribe en el .env cuando el
    técnico carga un token de vinculación (se pasa a Inno como
    /DSaviCloudUrl). Vacía por defecto: sin URL, el asistente no muestra la
    página "Conectar con SAVI Cloud" y no escribe nada de Cloud.

.PARAMETER SaviCloudRequired
    Hace OBLIGATORIA la vinculación con SAVI Cloud: el asistente no avanza sin
    un token válido. Es el build de la organización interna (SAVI Master), donde
    cada equipo tiene que quedar registrado. Requiere -SaviCloudUrl.

.PARAMETER AllowDirty
    Permite construir con cambios sin commitear. La versión queda marcada
    con "-sucio". Solo para pruebas locales: un instalador que se entrega
    tiene que corresponder a un commit exacto.

.EXAMPLE
    .\installer\build.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipFrontend,
    [switch]$SkipInstaller,
    [switch]$AllowDirty,
    [string]$SaviCloudUrl = '',
    [switch]$SaviCloudRequired
)

$ErrorActionPreference = 'Stop'

$InstallerDir = $PSScriptRoot
$Root         = Split-Path -Parent $InstallerDir
$Backend      = Join-Path $Root 'backend'
$Frontend     = Join-Path $Root 'frontend'
$Staging      = Join-Path $Backend 'frontend'

function Write-Step([string]$Message) {
    Write-Host "`n=== $Message ===" -ForegroundColor Cyan
}

# La versión es el tag de git y `scripts/version.py` es la única fuente
# (ver installer/README.md#versionado). Se resuelve UNA vez por build y de
# acá sale para el frontend, el backend y el instalador: si alguna vez se
# contradicen, alguien construyó a mano.
function Get-BuildVersion {
    $json = uv run --no-project python (Join-Path $Root 'scripts\version.py') --json
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo calcular la versión con scripts/version.py.' }
    return $json | ConvertFrom-Json
}

function Assert-Command([string]$Name, [string]$HowToInstall) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "No se encontró '$Name' en el PATH. $HowToInstall"
    }
}

# ── Verificación de herramientas ──────────────────────────────────────
Write-Step 'Verificando herramientas de build'

# uv no siempre queda en el PATH tras instalarse.
$UvLocal = Join-Path $env:USERPROFILE '.local\bin'
if ((Test-Path (Join-Path $UvLocal 'uv.exe')) -and ($env:Path -notlike "*$UvLocal*")) {
    $env:Path = "$UvLocal;$env:Path"
}
Assert-Command 'uv'   'Instalalo desde https://docs.astral.sh/uv/'
Assert-Command 'npm'  'Instalá Node.js 22 o superior desde https://nodejs.org/'
Assert-Command 'git'  'Instalá Git desde https://git-scm.com/'

$Build = Get-BuildVersion
if ($Build.sucio -and -not $AllowDirty) {
    throw @"
Hay cambios sin commitear. Un instalador que se entrega tiene que
corresponder a un commit exacto: commiteá o descartá los cambios.
Para una prueba local, repetí con -AllowDirty (la versión dirá "-sucio").
"@
}
Write-Host "Versión: $($Build.version)  (commit $($Build.commit))"

$Iscc = $null
if (-not $SkipInstaller) {
    # winget instala Inno Setup en scope de usuario salvo que se pida lo
    # contrario, así que %LOCALAPPDATA%\Programs va en la lista.
    # El @() alrededor del pipeline no es decorativo: Where-Object devuelve un
    # escalar cuando pasa un solo elemento, y ahí [0] indexa el *string* y
    # devuelve su primera letra ("C"). El síntoma era un build que empaquetaba
    # todo bien y moría al final con "el término 'C' no se reconoce".
    $IsccCandidates = @(
        @(
            (Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue).Source,
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
        ) | Where-Object { $_ -and (Test-Path $_) }
    )

    if (-not $IsccCandidates) {
        throw 'No se encontró ISCC.exe. Instalá Inno Setup 6 desde https://jrsoftware.org/isdl.php'
    }
    $Iscc = $IsccCandidates[0]
    Write-Host "Inno Setup: $Iscc"
}

# ── Recurso obligatorio que no vive en el repo ────────────────────────
$KnowledgeData = Join-Path $Backend 'app\modules\knowledge\data'
if (-not (Test-Path $KnowledgeData)) {
    throw @"
Falta el catálogo de conocimiento: $KnowledgeData

SAVI lo carga al arrancar y sin él el backend no levanta. No está
versionado en el repositorio, así que hay que copiarlo desde el equipo
donde se mantiene. Estructura esperada:
  data/modules/<dossier>/overview.json
  data/modules/<dossier>/{forms,workflows,faqs}/*.json
  data/shared/glossary.json
"@
}

# ── 1. Frontend ───────────────────────────────────────────────────────
if (-not $SkipFrontend) {
    Write-Step 'Compilando el frontend'
    # npm workspaces: las dependencias se instalan una sola vez en la raíz del monorepo
    # (lock único, `node_modules` compartido con el paquete de UI y la consola de Cloud).
    if (-not (Test-Path (Join-Path $Root 'node_modules'))) {
        Push-Location $Root
        try {
            npm install
            if ($LASTEXITCODE -ne 0) { throw 'npm install falló.' }
        }
        finally {
            Pop-Location
        }
    }
    Push-Location $Frontend
    try {
        # Base relativa: el backend sirve la SPA desde su mismo origen, así
        # que las llamadas al API no llevan host. Los dos consumidores
        # (HttpClient y authService) recortan la barra final.
        $env:VITE_API_BASE_URL = '/'
        # Queda incrustada en el bundle: es lo que muestra el pie del sidebar.
        $env:VITE_APP_VERSION = $Build.version
        # La landing comercial es del sitio público, no de la app de
        # escritorio: con el `.env` de desarrollo (VITE_LANDING_ENABLED=true)
        # el equipo del cliente abría "Solicitar demo" en vez del login. La
        # variable de entorno le gana al `.env` en Vite.
        $env:VITE_LANDING_ENABLED = 'false'
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'El build del frontend falló.' }
    }
    finally {
        Pop-Location
    }

    Write-Step 'Preparando el build de Vue para el backend'
    if (Test-Path $Staging) { Remove-Item $Staging -Recurse -Force }
    Copy-Item (Join-Path $Frontend 'dist') $Staging -Recurse
}

if (-not (Test-Path (Join-Path $Staging 'index.html'))) {
    throw "No hay build del frontend en $Staging. Corré sin -SkipFrontend."
}
if ($SkipFrontend) {
    Write-Warning "Se reutiliza un build de Vue anterior: la versión que muestra la interfaz puede no ser $($Build.version)."
}

# ── 2. Backend ────────────────────────────────────────────────────────
Write-Step 'Empaquetando el backend con PyInstaller'
# El equipo del cliente no tiene `.git`: la versión viaja incrustada en este
# módulo, que `app/_version.py` lee primero. Se borra al terminar —está
# gitignorado, pero si quedara en disco el backend de desarrollo seguiría
# reportando la versión de este build en lugar de la de git.
$BuildVersionFile = Join-Path $Backend 'app\_build_version.py'
$BuiltAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$BuildVersionContent = @"
# Generado por installer/build.ps1. No editar ni commitear.
VERSION = "$($Build.version)"
COMMIT = "$($Build.commit)"
BUILT_AT = "$BuiltAt"
"@
[System.IO.File]::WriteAllText($BuildVersionFile, $BuildVersionContent + "`n", (New-Object System.Text.UTF8Encoding $false))
Push-Location $Backend
try {
    uv sync
    if ($LASTEXITCODE -ne 0) { throw 'uv sync falló.' }

    # Modelo de embeddings de documentos de la empresa: viaja en el bundle y
    # SAVI no descarga en runtime. Idempotente: si ya está, solo lo verifica.
    uv run download-embedding-model
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar el modelo de embeddings.' }

    uv run pyinstaller `
        --noconfirm `
        --distpath (Join-Path $InstallerDir 'build\dist') `
        --workpath (Join-Path $InstallerDir 'build\work') `
        (Join-Path $InstallerDir 'savi.spec')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller falló.' }

    # Chequeo de conexión del asistente: lo usa el instalador antes de copiar SAVI.
    uv run pyinstaller `
        --noconfirm `
        --distpath (Join-Path $InstallerDir 'build\dbcheck') `
        --workpath (Join-Path $InstallerDir 'build\work-dbcheck') `
        (Join-Path $InstallerDir 'dbcheck.spec')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller falló al empaquetar savi-dbcheck.' }
}
finally {
    Pop-Location
    Remove-Item $BuildVersionFile -ErrorAction SilentlyContinue
}

$AppDir = Join-Path $InstallerDir 'build\dist\SAVI'
if (-not (Test-Path (Join-Path $AppDir 'SAVI.exe'))) {
    throw "PyInstaller no generó SAVI.exe en $AppDir"
}
Write-Host "Aplicación empaquetada en: $AppDir"

# ── 3. Instalador ─────────────────────────────────────────────────────
if ($SkipInstaller) {
    Write-Step 'Listo (se omitió el instalador)'
    return
}

Write-Step "Compilando el instalador con Inno Setup (versión $($Build.version))"
# AppVersion admite texto (v1.4.0-14-gbf8eee7); VersionInfoVersion, el recurso
# de versión del .exe, exige un número puro: sale del último tag.
# La URL de SAVI Cloud es opcional: vacía, el instalador omite la página de
# vinculación. Se valida acá para fallar en el build y no en el equipo del cliente.
$IsccArgs = @("/DAppVersion=$($Build.version)", "/DAppVersionNumber=$($Build.numero)")
if ($SaviCloudUrl) {
    if ($SaviCloudUrl -notmatch '^https://[^\s"]+$') {
        throw "-SaviCloudUrl tiene que ser una URL https sin espacios ni comillas: '$SaviCloudUrl'"
    }
    $IsccArgs += "/DSaviCloudUrl=$SaviCloudUrl"
}
if ($SaviCloudRequired) {
    # Sin URL no hay a dónde vincular: un build "obligatorio" sin Cloud dejaría al equipo
    # sin poder terminar la instalación.
    if (-not $SaviCloudUrl) {
        throw '-SaviCloudRequired necesita -SaviCloudUrl: sin URL no hay a dónde vincular.'
    }
    $IsccArgs += '/DSaviCloudRequired=1'
}
& $Iscc @IsccArgs (Join-Path $InstallerDir 'savi.iss')
if ($LASTEXITCODE -ne 0) { throw 'La compilación de Inno Setup falló.' }

Write-Step 'Listo'
Get-ChildItem (Join-Path $InstallerDir 'output') -Filter '*.exe' |
    ForEach-Object { Write-Host "  $($_.FullName)  ($([math]::Round($_.Length / 1MB)) MB)" -ForegroundColor Green }
