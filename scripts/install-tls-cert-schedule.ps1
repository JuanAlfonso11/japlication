# Programa check-tls-cert.ps1 una vez por semana con el Programador de tareas
# de Windows.
#
# Por que semanal y no diario: el certificado dura 90 dias y el aviso salta a
# los 21 que quedan, asi que aunque se pierda una semana entera quedan dos
# para reaccionar. Un chequeo diario solo llenaria de ruido el Estado del
# sistema sin ganar nada.
#
# Corre solo con la sesion iniciada (igual que el sweep y el chequeo de
# postulaciones): si el PC estaba apagado el domingo, StartWhenAvailable hace
# que se ejecute en cuanto Windows tenga oportunidad.

$ErrorActionPreference = "Stop"

$repoDir = Split-Path -Parent $PSScriptRoot
$checkScript = Join-Path $repoDir "scripts\check-tls-cert.ps1"
$taskName = "JobPilot TLS Cert Check"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$checkScript`""

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "10:00AM"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Chequeo semanal del certificado TLS de Tailscale (scripts\check-tls-cert.ps1)." | Out-Null

Write-Host "Instalado: tarea '$taskName', corre los domingos a las 10:00 AM."
Write-Host "Para deshacer: Unregister-ScheduledTask -TaskName '$taskName'"
