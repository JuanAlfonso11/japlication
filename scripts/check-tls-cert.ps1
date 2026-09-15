# Vigila el certificado TLS que Tailscale sirve para JobPilot.
#
# Por que existe:
#   Todo el acceso remoto -- el telefono, la app de Android, el panel desde
#   otra maquina -- entra por https://<host>.ts.net. Tailscale pide y renueva
#   ese certificado de Let's Encrypt automaticamente, y casi siempre funciona.
#   El problema es que cuando NO funciona no avisa nadie: el certificado vence
#   en silencio y un dia la app simplemente deja de cargar en el telefono, con
#   un error de TLS que no dice de donde viene.
#
#   Let's Encrypt emite a 90 dias y Tailscale renueva alrededor de los 30 que
#   quedan. Si a los 21 todavia no se renovo, algo esta atascado y aun hay
#   tres semanas para arreglarlo con calma.
#
# Reporta por el mismo heartbeat que los demas trabajos programados, asi que
# el resultado aparece en Perfil -> Estado del sistema junto al resto.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\check-tls-cert.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\check-tls-cert.ps1 -Verbose

[CmdletBinding()]
param(
    [string]$HostName = "",
    [int[]]$Ports = @(443, 8443),
    [int]$WarnDays = 21,
    [int]$CriticalDays = 7
)

$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "Send-Heartbeat.ps1")

# El host sale de FRONTEND_ORIGIN en .env, para no repetirlo aqui: si algun dia
# cambia el nombre en la tailnet, este script lo sigue solo.
if (-not $HostName) {
    $envPath = Join-Path (Split-Path -Parent $PSScriptRoot) ".env"
    if (Test-Path $envPath) {
        $line = Get-Content $envPath | Where-Object { $_ -match '^\s*FRONTEND_ORIGIN\s*=' } | Select-Object -First 1
        if ($line) {
            $value = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'")
            try { $HostName = ([uri]$value).Host } catch { }
        }
    }
}
if (-not $HostName) {
    Send-Heartbeat -JobName "tls_cert" -Status "error" -Detail "No se pudo determinar el host (FRONTEND_ORIGIN)"
    Write-Error "[tls] No se pudo determinar el host desde .env; pasa -HostName."
    exit 1
}

function Get-CertInfo([string]$h, [int]$p) {
    $tcp = $null; $ssl = $null
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        # Sin timeout explicito, un host caido cuelga el trabajo programado.
        if (-not $tcp.ConnectAsync($h, $p).Wait(10000)) { throw "timeout de conexion" }
        $ssl = New-Object System.Net.Security.SslStream($tcp.GetStream(), $false, ({ $true }))
        $ssl.AuthenticateAsClient($h)
        $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($ssl.RemoteCertificate)
        return [pscustomobject]@{
            Port     = $p
            NotAfter = $cert.NotAfter
            Days     = [math]::Round(($cert.NotAfter - (Get-Date)).TotalDays, 1)
            Issuer   = ($cert.Issuer -split ',')[0]
            Subject  = ($cert.Subject -split ',')[0]
            Error    = $null
        }
    } catch {
        return [pscustomobject]@{ Port = $p; NotAfter = $null; Days = $null; Issuer = $null; Subject = $null; Error = $_.Exception.Message }
    } finally {
        if ($ssl) { $ssl.Dispose() }
        if ($tcp) { $tcp.Close() }
    }
}

$results = foreach ($p in $Ports) { Get-CertInfo $HostName $p }

foreach ($r in $results) {
    if ($r.Error) { Write-Verbose "[tls] $HostName`:$($r.Port) -> ERROR $($r.Error)" }
    else { Write-Verbose "[tls] $HostName`:$($r.Port) -> vence $($r.NotAfter) ($($r.Days) dias), $($r.Issuer)" }
}

$failed = @($results | Where-Object { $_.Error })
$ok = @($results | Where-Object { -not $_.Error })

if ($failed.Count -gt 0 -and $ok.Count -eq 0) {
    $detail = "No se pudo leer el certificado en ningun puerto: " + (($failed | ForEach-Object { "$($_.Port): $($_.Error)" }) -join "; ")
    Send-Heartbeat -JobName "tls_cert" -Status "error" -Detail $detail
    Write-Error "[tls] $detail"
    exit 1
}

$min = ($ok | Measure-Object -Property Days -Minimum).Minimum
$worst = $ok | Where-Object { $_.Days -eq $min } | Select-Object -First 1
$puertos = ($ok | ForEach-Object { $_.Port }) -join ", "

if ($failed.Count -gt 0) {
    $detail = "Puertos $puertos OK ($min dias), pero fallaron: " + (($failed | ForEach-Object { $_.Port }) -join ", ")
    Send-Heartbeat -JobName "tls_cert" -Status "error" -Detail $detail
    Write-Warning "[tls] $detail"
    exit 1
}

if ($min -le $CriticalDays) {
    $detail = "CRITICO: el certificado vence en $min dias ($($worst.NotAfter)). Tailscale no lo renovo. Revisa: tailscale cert $HostName"
    Send-Heartbeat -JobName "tls_cert" -Status "error" -Detail $detail
    Write-Error "[tls] $detail"
    exit 1
}

if ($min -le $WarnDays) {
    $detail = "El certificado vence en $min dias y Tailscale aun no lo renovo (normalmente lo hace a los 30). Revisa: tailscale cert $HostName"
    Send-Heartbeat -JobName "tls_cert" -Status "error" -Detail $detail
    Write-Warning "[tls] $detail"
    exit 1
}

$detail = "$min dias restantes ($($worst.Issuer)), puertos $puertos"
Send-Heartbeat -JobName "tls_cert" -Status "ok" -Detail $detail
Write-Host "[tls] OK - $detail"
exit 0
