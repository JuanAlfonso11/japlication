' Silent launcher for serve-offline.ps1 - runs it without flashing a
' console/terminal window. Used by the Startup-folder autostart entry.
Dim objShell, fso, scriptDir
Set objShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
objShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & scriptDir & "\serve-offline.ps1""", 0, False
