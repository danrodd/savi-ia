<#
    Deja un equipo de pruebas como si SAVI nunca se hubiera instalado.

    Desinstala SAVI, Node.js y Git for Windows, borra el prefijo global de
    npm donde vive el CLI de Claude, la sesión del CLI, y saca del PATH del
    sistema la entrada que agrega el instalador y que no se remueve sola.

    Uso (PowerShell COMO ADMINISTRADOR):
        powershell -ExecutionPolicy Bypass -File .\limpiar-prerequisitos.ps1

    OJO: pensado para el equipo de pruebas del cliente, NO para una máquina
    de desarrollo. Borra %USERPROFILE%\.claude entero.
#>

#Requires -RunAsAdministrator

$ErrorActionPreference = 'Continue'

function Write-Paso($texto) {
    Write-Host "`n== $texto" -ForegroundColor Cyan
}

# Snapshot del registro ANTES de desinstalar nada.
$clavesUninstall = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
$instalados = Get-ItemProperty $clavesUninstall -ErrorAction SilentlyContinue

function Get-Entrada($patron) {
    $instalados | Where-Object { $_.DisplayName -like $patron }
}

# ── 1. SAVI ──────────────────────────────────────────────────────────────
Write-Paso 'Desinstalando SAVI'
$savi = Get-Entrada 'SAVI*'
if ($savi) {
    foreach ($item in $savi) {
        $exe = $item.UninstallString -replace '"', ''
        Write-Host "   $($item.DisplayName)"
        Start-Process $exe '/SILENT /NORESTART' -Wait
    }
} else {
    Write-Host '   no estaba instalado' -ForegroundColor DarkGray
}

# ── 2. Node.js (MSI) ─────────────────────────────────────────────────────
Write-Paso 'Desinstalando Node.js'
$node = Get-Entrada 'Node.js*'
if ($node) {
    foreach ($item in $node) {
        Write-Host "   $($item.DisplayName) $($item.DisplayVersion)"
        Start-Process 'msiexec.exe' "/x $($item.PSChildName) /qn /norestart" -Wait
    }
} else {
    Write-Host '   no estaba instalado' -ForegroundColor DarkGray
}

# ── 3. Git for Windows ───────────────────────────────────────────────────
Write-Paso 'Desinstalando Git for Windows'
$git = Get-Entrada 'Git version*'
if (-not $git) { $git = Get-Entrada 'Git*' | Where-Object { $_.Publisher -like '*Git*' } }
if ($git) {
    foreach ($item in $git) {
        $exe = $item.UninstallString -replace '"', ''
        Write-Host "   $($item.DisplayName)"
        Start-Process $exe '/VERYSILENT /NORESTART /SUPPRESSMSGBOXES' -Wait
    }
} else {
    Write-Host '   no estaba instalado' -ForegroundColor DarkGray
}

# ── 4. Restos en disco ───────────────────────────────────────────────────
# El CLI de Claude puede estar de dos formas y hay que cubrir las dos, igual
# que hace ClaudeCliInstalled() en savi.iss:
#   - puesto por el instalador: `npm install -g --prefix C:\ProgramData\npm`
#   - preexistente en el equipo: instalador nativo en %USERPROFILE%\.local\bin
# Antes de borrar, matar lo que pueda tener archivos tomados.
Write-Paso 'Borrando restos en disco'
Get-Process SAVI, claude, node -ErrorAction SilentlyContinue | Stop-Process -Force
$restos = @(
    'C:\Program Files\SAVI'
    'C:\Program Files\nodejs'
    'C:\ProgramData\npm'
    "$env:APPDATA\npm"
    "$env:APPDATA\npm-cache"
    "$env:LOCALAPPDATA\npm-cache"
    "$env:USERPROFILE\.local\bin\claude.exe"   # CLI nativo (no npm)
    "$env:USERPROFILE\.claude"       # sesión del CLI (.credentials.json)
    "$env:USERPROFILE\.claude.json"
)
foreach ($ruta in $restos) {
    if (Test-Path $ruta) {
        Remove-Item $ruta -Recurse -Force -ErrorAction SilentlyContinue
        $estado = if (Test-Path $ruta) { 'NO SE PUDO BORRAR' } else { 'borrado' }
        Write-Host "   $ruta -> $estado"
    }
}

# ── 5. PATH del sistema ──────────────────────────────────────────────────
# savi.iss agrega C:\ProgramData\npm al PATH de la máquina y no lo quita al
# desinstalar. Sin sacarlo, NeedsPathEntry() devuelve False en la próxima
# instalación y ese camino nunca se prueba.
Write-Paso 'Limpiando el PATH del sistema'
$partes = [Environment]::GetEnvironmentVariable('Path', 'Machine') -split ';'
$limpio = $partes | Where-Object { $_ -and $_ -notmatch 'npm|nodejs' }
if ($partes.Count -ne $limpio.Count) {
    [Environment]::SetEnvironmentVariable('Path', ($limpio -join ';'), 'Machine')
    Write-Host "   quitadas $($partes.Count - $limpio.Count) entrada(s)"
} else {
    Write-Host '   ya estaba limpio' -ForegroundColor DarkGray
}

# ── 6. Verificación ──────────────────────────────────────────────────────
Write-Paso 'Verificación'
$ok = $true
foreach ($ruta in 'C:\Program Files\SAVI', 'C:\ProgramData\npm', "$env:USERPROFILE\.claude") {
    if (Test-Path $ruta) { Write-Host "   QUEDA: $ruta" -ForegroundColor Red; $ok = $false }
}
foreach ($bin in 'claude', 'node', 'git') {
    $encontrado = Get-Command $bin -ErrorAction SilentlyContinue
    if ($encontrado) { Write-Host "   QUEDA: $($encontrado.Source)" -ForegroundColor Red; $ok = $false }
}

if ($ok) {
    Write-Host "`nEquipo limpio. REINICIA antes de volver a instalar SAVI." -ForegroundColor Green
} else {
    Write-Host "`nQuedaron restos (ver arriba). Suele ser un archivo en uso:" -ForegroundColor Yellow
    Write-Host 'cerra SAVI y las consolas abiertas, reinicia y corre el script de nuevo.' -ForegroundColor Yellow
}
