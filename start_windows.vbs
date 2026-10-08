' Luga Assist - Zero-Console Silent Windows Launcher
' Launches Luga Assist in the background without any CMD / terminal window popping up.
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)

Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = strPath

' 1. Check if Luga Assist is already running on port 8000
On Error Resume Next
Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
http.setTimeouts 500, 500, 500, 500
http.Open "GET", "http://127.0.0.1:8000/api/status", False
http.Send

If Err.Number = 0 And http.Status = 200 Then
    ' Trigger Spotlight window to appear
    http.Open "POST", "http://127.0.0.1:8000/api/spotlight/show", False
    http.Send
Else
    ' 2. Launch standalone executable if present, else fallback to pythonw
    exePath = strPath & "\dist\Luga Assist\Luga Assist.exe"
    If fso.FileExists(exePath) Then
        WshShell.Run """" & exePath & """", 0, False
    Else
        cmd = "cmd.exe /c set PYTHONPATH=" & strPath & " && pythonw -m app.main"
        WshShell.Run cmd, 0, False
    End If
End If
