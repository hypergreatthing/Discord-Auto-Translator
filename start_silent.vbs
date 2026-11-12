Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get directory of this script
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir

venvPython = scriptDir & "\.venv\Scripts\python.exe"
venvPythonw = scriptDir & "\.venv\Scripts\pythonw.exe"

' Verify .venv exists and has uvicorn installed; if not, run start_translator.bat visibly to self-heal
If fso.FileExists(venvPython) Then
    checkCode = WshShell.Run("""" & venvPython & """ -c ""import uvicorn, fastapi""", 0, True)
Else
    checkCode = 1
End If

If checkCode = 0 And fso.FileExists(venvPythonw) Then
    cmd = """" & venvPythonw & """ -m backend.main"
    WshShell.Run cmd, 0, False
Else
    ' Run the console launcher so it automatically installs missing dependencies
    WshShell.Run """" & scriptDir & "\start_translator.bat""", 1, False
End If
