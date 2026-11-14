' Open the configured virtual environment without a command window.
Option Explicit
Dim files, folder, python, launcher, shell
Set files = CreateObject("Scripting.FileSystemObject")
folder = files.GetParentFolderName(WScript.ScriptFullName)
python = files.BuildPath(folder, ".venv\Scripts\pythonw.exe")
launcher = files.BuildPath(folder, "launch.pyw")
If Not files.FileExists(python) Then
  MsgBox "Complete the Python environment setup first. See README.md in this folder.", 48, "SignalSpeak setup needed"
  WScript.Quit 1
End If
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = folder
shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & launcher & Chr(34), 0, False
