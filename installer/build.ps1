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

.EXAMPLE
    .\installer\build.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipFrontend,
    [switch]$SkipInstaller
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
    Push-Location $Frontend
    try {
        if (-not (Test-Path 'node_modules')) {
            npm install
            if ($LASTEXITCODE -ne 0) { throw 'npm install falló.' }
        }
        # Base relativa: el backend sirve la SPA desde su mismo origen, así
        # que las llamadas al API no llevan host. Los dos consumidores
        # (HttpClient y authService) recortan la barra final.
        $env:VITE_API_BASE_URL = '/'
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

# ── 2. Backend ────────────────────────────────────────────────────────
Write-Step 'Empaquetando el backend con PyInstaller'
Push-Location $Backend
try {
    uv sync
    if ($LASTEXITCODE -ne 0) { throw 'uv sync falló.' }

    uv run pyinstaller `
        --noconfirm `
        --distpath (Join-Path $InstallerDir 'build\dist') `
        --workpath (Join-Path $InstallerDir 'build\work') `
        (Join-Path $InstallerDir 'savi.spec')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller falló.' }
}
finally {
    Pop-Location
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

Write-Step 'Compilando el instalador con Inno Setup'
& $Iscc (Join-Path $InstallerDir 'savi.iss')
if ($LASTEXITCODE -ne 0) { throw 'La compilación de Inno Setup falló.' }

Write-Step 'Listo'
Get-ChildItem (Join-Path $InstallerDir 'output') -Filter '*.exe' |
    ForEach-Object { Write-Host "  $($_.FullName)  ($([math]::Round($_.Length / 1MB)) MB)" -ForegroundColor Green }
