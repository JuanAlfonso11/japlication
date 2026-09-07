' Generic silent launcher for the scheduled JobPilot scripts.
'
' Task Scheduler running `powershell.exe` directly pops a console window
' every time it fires, even with -WindowStyle Hidden: the window is created
' and only then hidden, which on this machine means a visible flash that
' steals focus. With the watchdog firing every 15 minutes, that's an
' interruption several times an hour while the user is doing something else.
'
' wscript has no console of its own, so launching PowerShell from here with
' the window style set to 0 means no window is ever created. Same trick
' JobPilot.vbs already uses for the desktop shortcut, generalised to take
' the target script as an argument.
'
' Usage:  wscript.exe run-hidden.vbs "C:\path\to\script.ps1"

Option Explicit

Dim objShell, args, target, i, extraArgs

Set objShell = CreateObject("WScript.Shell")
Set args = WScript.Arguments

If args.Count < 1 Then
    WScript.Quit 1
End If

target = args(0)

' Anything after the script path is forwarded to the script itself, so this
' also works for the tasks that take parameters.
extraArgs = ""
For i = 1 To args.Count - 1
    extraArgs = extraArgs & " """ & args(i) & """"
Next

' 0 = hidden window, False = don't block waiting for it to finish.
objShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & target & """" & extraArgs, 0, False
