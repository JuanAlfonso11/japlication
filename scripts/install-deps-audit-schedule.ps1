# Programa check-deps.ps1 una vez por semana con el Programador de tareas de
# Windows. Mismo patron que install-tls-cert-schedule.ps1: solo con la sesion
# iniciada, y si el PC estaba apagado corre en cuanto pueda.
#
# Semanal: los avisos de seguridad graves salen unas pocas veces al mes; una
# semana de margen es razonable para una app personal, y diario solo haria
# ruido en el Estado del sistema.

$ErrorActionPreference = "Stop"

$repoDir = Split-Path -Parent $PSScriptRoot
$checkScript = Join-Path $repoDir "scripts\check-deps.ps1"
$taskName = "JobPilot Dependency Audit"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$checkScript`""

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "10:15AM"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Auditoria semanal de dependencias de JobPilot (scripts\check-deps.ps1)." | Out-Null

Write-Host "Instalado: tarea '$taskName', corre los domingos a las 10:15 AM."
Write-Host "Para deshacer: Unregister-ScheduledTask -TaskName '$taskName'"
