' Luga Assist - Zero-Console Silent Windows Launcher
' Launches Luga Assist in the background without any CMD / terminal window popping up.
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)

Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = strPath

' Try pythonw.exe first (native windowless python), fallback to python.exe hidden
cmd = "cmd.exe /c set PYTHONPATH=" & strPath & " && pythonw -m app.main"

' WindowStyle 0 = Hidden, bWaitOnReturn = False
WshShell.Run cmd, 0, False
