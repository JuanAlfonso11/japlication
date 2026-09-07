# Repoints every scheduled JobPilot task at run-hidden.vbs so it stops
# popping a PowerShell console window when it fires.
#
# The tasks were registered to run `powershell.exe -File ...` directly.
# Task Scheduler creates a console for that even with -WindowStyle Hidden
# (the window exists first and is hidden after), which shows up as a flash
# that can steal focus - several times an hour, since the watchdog runs
# every 15 minutes. Launching via wscript instead means no console is ever
# created. See scripts/run-hidden.vbs.
#
# NOTE: kept deliberately ASCII-only. These .ps1 files are saved as UTF-8
# without a BOM, and Windows PowerShell 5.1 decodes them as ANSI, so an
# em-dash inside a *string literal* turns into bytes containing a smart
# quote, which PowerShell honours as a string delimiter and the parse
# breaks. In comments it is survivable; in strings it is not.
#
# Safe to re-run: tasks already pointing at the launcher are left alone.
#
# Usage:  .\scripts\fix-task-windows.ps1

$ErrorActionPreference = "Stop"
$repoDir = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $repoDir "scripts\run-hidden.vbs"

if (-not (Test-Path $launcher)) {
    throw "No se encontro el lanzador: $launcher"
}

$tasks = Get-ScheduledTask | Where-Object { $_.TaskName -like "JobPilot*" }
if (-not $tasks) {
    Write-Host "No hay tareas JobPilot* registradas."
    return
}

foreach ($task in $tasks) {
    $action = $task.Actions[0]

    if ($action.Execute -match "wscript") {
        Write-Host "[skip] $($task.TaskName) - ya usa el lanzador silencioso."
        continue
    }

    # Pull the -File target out of the existing arguments so the task keeps
    # pointing at the same script.
    if ($action.Arguments -match '-File\s+"([^"]+)"') {
        $targetScript = $Matches[1]
    } else {
        Write-Warning "[skip] $($task.TaskName) - no se pudo determinar el script destino."
        continue
    }

    $newAction = New-ScheduledTaskAction -Execute "wscript.exe" `
        -Argument ("`"$launcher`" `"$targetScript`"")

    Set-ScheduledTask -TaskName $task.TaskName -Action $newAction | Out-Null
    Write-Host "[ok]   $($task.TaskName) -> wscript run-hidden.vbs"
}

Write-Host ""
Write-Host "Listo. Las tareas ya no abriran ventanas de PowerShell."
