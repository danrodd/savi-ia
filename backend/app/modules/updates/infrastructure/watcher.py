"""Vigilante de la instalación: un proceso aparte que sobrevive al cierre de SAVI.

Al actualizar, SAVI lanza el instalador y el instalador cierra SAVI. Si algo
sale mal (el permiso de administrador se cancela, el instalador falla, el equipo
se queda sin espacio), nadie vuelve a abrir SAVI y la persona queda frente a una
pantalla que espera para siempre. El vigilante cubre ese hueco:

1. Lanza el instalador (con el permiso de administrador si hace falta) y espera.
2. Anota en `last-install.json` cómo terminó.
3. Si SAVI no volvió a abrir, lo abre con la versión que haya quedado instalada.

Es PowerShell, que viene en todo Windows 10 y 11. El texto es solo ASCII para
no depender de la codificación del archivo. No habla con el usuario: los
mensajes en usted los arma SAVI a partir del resultado.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SCRIPT_FILENAME = "watch-install.ps1"

# `Bypass` solo vale para este proceso. Si una política de grupo lo impide,
# PowerShell sale con error y el lanzador vuelve al método directo.
POWERSHELL_FLAGS = (
    "-NoProfile",
    "-NonInteractive",
    "-ExecutionPolicy",
    "Bypass",
    "-WindowStyle",
    "Hidden",
)

WATCHER_SCRIPT = r"""param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [Parameter(Mandatory = $true)][string]$InstallerFlags,
    [Parameter(Mandatory = $true)][string]$LogPath,
    [Parameter(Mandatory = $true)][string]$AppExe,
    [Parameter(Mandatory = $true)][string]$ResultPath,
    [Parameter(Mandatory = $true)][string]$AttemptId,
    [Parameter(Mandatory = $true)][string]$FromVersion,
    [Parameter(Mandatory = $true)][string]$ToVersion,
    [Parameter(Mandatory = $true)][string]$HealthHost,
    [Parameter(Mandatory = $true)][int]$PortFrom,
    [Parameter(Mandatory = $true)][int]$PortCount,
    [switch]$Elevate,
    [int]$InstallTimeoutSeconds = 1800,
    [int]$HealthTimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'

function Get-Now { return [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ') }

$StartedAt = Get-Now
$state = @{
    step = 'started'
    exit_code = $null
    finished_at = $null
    relaunched = $false
    running_version = $null
}

# Se escribe a un archivo temporal y se renombra: SAVI nunca lee un JSON a medias.
# Se reintenta porque SAVI puede tener el archivo abierto justo en ese momento.
function Save-Result {
    $payload = [ordered]@{
        attempt_id      = $AttemptId
        from_version    = $FromVersion
        to_version      = $ToVersion
        started_at      = $StartedAt
        step            = $state.step
        exit_code       = $state.exit_code
        finished_at     = $state.finished_at
        relaunched      = $state.relaunched
        running_version = $state.running_version
    }
    $json = $payload | ConvertTo-Json -Compress
    $temporary = "$ResultPath.tmp"
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    for ($i = 0; $i -lt 15; $i++) {
        try {
            [System.IO.File]::WriteAllText($temporary, $json, $utf8)
            Move-Item -LiteralPath $temporary -Destination $ResultPath -Force
            return
        } catch {
            Start-Sleep -Milliseconds 200
        }
    }
}

# Version con la que responde SAVI en alguno de sus puertos, o $null si no responde.
# SAVI usa el puerto configurado y, si esta ocupado, uno de los siguientes.
function Get-SaviVersion {
    for ($port = $PortFrom; $port -lt ($PortFrom + $PortCount); $port++) {
        try {
            $request = [System.Net.WebRequest]::Create("http://${HealthHost}:$port/health")
            $request.Timeout = 2000
            $request.Proxy = $null
            $response = $request.GetResponse()
            $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
            $body = $reader.ReadToEnd()
            $reader.Close()
            $response.Close()
            if ($body -match '"status"') {
                $version = ''
                try { $version = [string](ConvertFrom-Json $body).version } catch { }
                if ([string]::IsNullOrEmpty($version)) { return '?' }
                return $version
            }
        } catch {
        }
    }
    return $null
}

# Espera a que SAVI responda; si pasa $GraceSeconds sin que responda, lo abre.
function Wait-Savi([int]$GraceSeconds) {
    $deadline = [DateTime]::UtcNow.AddSeconds($GraceSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $version = Get-SaviVersion
        if ($version) { return $version }
        Start-Sleep -Seconds 3
    }
    try {
        $folder = Split-Path -Parent $AppExe
        Start-Process -FilePath $AppExe -ArgumentList '--no-browser' -WorkingDirectory $folder
    } catch {
        return $null
    }
    $state.relaunched = $true
    $deadline = [DateTime]::UtcNow.AddSeconds($HealthTimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $version = Get-SaviVersion
        if ($version) { return $version }
        Start-Sleep -Seconds 3
    }
    return $null
}

try {
    Save-Result
    $arguments = "$InstallerFlags /LOG=`"$LogPath`""
    $process = $null
    try {
        # Process.Start y no Start-Process: cuando se cancela el cartel del
        # permiso, Start-Process lanza un error sin codigo y con el texto en el
        # idioma de Windows; Process.Start deja el codigo 1223 en la excepcion.
        $info = New-Object System.Diagnostics.ProcessStartInfo
        $info.FileName = $Installer
        $info.Arguments = $arguments
        $info.UseShellExecute = $true
        $info.WorkingDirectory = Split-Path -Parent $Installer
        if ($Elevate) { $info.Verb = 'runas' }
        $process = [System.Diagnostics.Process]::Start($info)
        if ($null -eq $process) { throw 'El instalador no devolvio un proceso.' }
    } catch {
        # 1223: la persona cancelo el cartel del permiso de administrador.
        $native = 0
        $problem = $_.Exception
        while ($problem) {
            if ($problem -is [System.ComponentModel.Win32Exception]) {
                $native = $problem.NativeErrorCode
                break
            }
            $problem = $problem.InnerException
        }
        $state.step = if ($native -eq 1223) { 'cancelled' } else { 'failed' }
        $state.finished_at = Get-Now
        Save-Result
        # SAVI nunca se cerro: solo se comprueba que siga abierto.
        $state.running_version = Wait-Savi 5
        Save-Result
        exit 0
    }

    if (-not $process.WaitForExit($InstallTimeoutSeconds * 1000)) {
        $state.step = 'timeout'
        $state.finished_at = Get-Now
        Save-Result
        $state.running_version = Wait-Savi 5
        Save-Result
        exit 0
    }

    # Sin codigo legible (puede pasar con un proceso elevado) cuenta como
    # terminado: SAVI decide por la version que quede corriendo.
    $code = $null
    try { $code = $process.ExitCode } catch { }
    $state.exit_code = $code
    $state.finished_at = Get-Now
    $state.step = if ($null -eq $code -or $code -eq 0) { 'finished' } else { 'failed' }
    Save-Result

    # Con exito, el instalador mismo vuelve a abrir SAVI: se le da tiempo.
    # Si fallo, esa entrada no corrio y SAVI hay que abrirlo ya.
    $grace = if ($state.step -eq 'finished') { $HealthTimeoutSeconds } else { 5 }
    $state.running_version = Wait-Savi $grace
    Save-Result
} catch {
    $state.step = 'failed'
    $state.finished_at = Get-Now
    Save-Result
    try {
        $state.running_version = Wait-Savi 5
        Save-Result
    } catch { }
}
exit 0
"""


@dataclass(frozen=True)
class WatcherJob:
    installer: Path
    # Banderas del instalador sin el `/LOG`, que el vigilante arma con `log_path`.
    installer_flags: str
    log_path: Path
    app_exe: Path
    result_path: Path
    attempt_id: str
    from_version: str
    to_version: str
    health_host: str
    port_from: int
    port_count: int
    elevate: bool
    install_timeout_seconds: int = 1800
    health_timeout_seconds: int = 120


def powershell_path() -> Path:
    """PowerShell del sistema, por ruta absoluta y no por el PATH."""
    root = os.environ.get("SYSTEMROOT") or r"C:\Windows"
    return Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


def write_script(updates_dir: Path) -> Path:
    """Deja el script junto a la descarga, fuera de `{app}`: la instalación reemplaza `{app}`."""
    updates_dir.mkdir(parents=True, exist_ok=True)
    path = updates_dir / SCRIPT_FILENAME
    path.write_text(WATCHER_SCRIPT, encoding="utf-8", newline="\r\n")
    return path


def watcher_command(script: Path, job: WatcherJob) -> list[str]:
    command = [
        str(powershell_path()),
        *POWERSHELL_FLAGS,
        "-File",
        str(script),
        "-Installer",
        str(job.installer),
        "-InstallerFlags",
        job.installer_flags,
        "-LogPath",
        str(job.log_path),
        "-AppExe",
        str(job.app_exe),
        "-ResultPath",
        str(job.result_path),
        "-AttemptId",
        job.attempt_id,
        "-FromVersion",
        job.from_version,
        "-ToVersion",
        job.to_version,
        "-HealthHost",
        job.health_host,
        "-PortFrom",
        str(job.port_from),
        "-PortCount",
        str(job.port_count),
        "-InstallTimeoutSeconds",
        str(job.install_timeout_seconds),
        "-HealthTimeoutSeconds",
        str(job.health_timeout_seconds),
    ]
    if job.elevate:
        command.append("-Elevate")
    return command
