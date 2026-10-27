Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get directory of this script
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Check if virtualenv pythonw exists, else fallback to system pythonw
venvPythonw = scriptDir & "\.venv\Scripts\pythonw.exe"
If fso.FileExists(venvPythonw) Then
    cmd = """" & venvPythonw & """ -m backend.main"
Else
    cmd = "pythonw.exe -m backend.main"
End If

WshShell.CurrentDirectory = scriptDir
WshShell.Run cmd, 0, False
