' Runs Luga Assist background daemon on Windows with ZERO command prompt windows visible
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.Run "pythonw.exe -m app.main", 0, False
