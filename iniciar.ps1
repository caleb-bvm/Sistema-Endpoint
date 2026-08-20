[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Error "No se encontró el entorno virtual. Ejecute primero: python -m venv .venv"
    exit 1
}

function Get-PreferredLanAddress {
    $candidates = foreach ($networkInterface in [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()) {
        if ($networkInterface.OperationalStatus -ne [System.Net.NetworkInformation.OperationalStatus]::Up) {
            continue
        }

        if ($networkInterface.NetworkInterfaceType -in @(
                [System.Net.NetworkInformation.NetworkInterfaceType]::Loopback,
                [System.Net.NetworkInformation.NetworkInterfaceType]::Tunnel
            )) {
            continue
        }

        $properties = $networkInterface.GetIPProperties()
        $hasIpv4Gateway = $properties.GatewayAddresses | Where-Object {
            $_.Address.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and
            $_.Address.ToString() -ne "0.0.0.0"
        }

        foreach ($unicastAddress in $properties.UnicastAddresses) {
            $address = $unicastAddress.Address
            if ($address.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
                continue
            }

            $addressText = $address.ToString()
            if ($addressText -eq "127.0.0.1" -or $addressText.StartsWith("169.254.")) {
                continue
            }

            [pscustomobject]@{
                Address = $addressText
                HasGateway = [bool]$hasIpv4Gateway
                IsWireless = $networkInterface.NetworkInterfaceType -eq [System.Net.NetworkInformation.NetworkInterfaceType]::Wireless80211
                Speed = $networkInterface.Speed
            }
        }
    }

    $preferred = $candidates | Sort-Object -Property @(
        @{ Expression = { $_.HasGateway }; Descending = $true },
        @{ Expression = { $_.IsWireless }; Descending = $true },
        @{ Expression = { $_.Speed }; Descending = $true }
    ) | Select-Object -First 1

    return $preferred.Address
}

$activeListeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
if ($activeListeners.Port -contains $Port) {
    Write-Error "El puerto $Port ya está ocupado. Detenga el servidor anterior con Ctrl+C y vuelva a ejecutar este comando."
    exit 1
}

$lanAddress = Get-PreferredLanAddress
if ($lanAddress) {
    $env:DJANGO_ALLOWED_HOSTS = $lanAddress
} else {
    $env:DJANGO_ALLOWED_HOSTS = ""
}

Set-Location -LiteralPath $projectRoot

Write-Host "Preparando la base de datos..." -ForegroundColor Cyan
& $pythonPath manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Sistema listo" -ForegroundColor Green
Write-Host "PC:      http://127.0.0.1:$Port"
if ($lanAddress) {
    Write-Host "Android: http://${lanAddress}:$Port" -ForegroundColor Yellow
    Write-Host "Mantenga la PC y el dispositivo movil conectados a la misma red o hotspot."
} else {
    Write-Warning "No se detectó una red activa. El sistema estará disponible únicamente en esta PC."
}
Write-Host "Presione Ctrl+C para detener el servidor."
Write-Host ""

& $pythonPath manage.py runserver "0.0.0.0:$Port"
exit $LASTEXITCODE
