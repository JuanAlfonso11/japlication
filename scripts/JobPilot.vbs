' Silent launcher for jobpilot-control.ps1 - runs it without flashing a
' console/terminal window. This is the file the desktop shortcut points to.
Dim objShell, fso, scriptDir
Set objShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
objShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & scriptDir & "\jobpilot-control.ps1""", 0, False
