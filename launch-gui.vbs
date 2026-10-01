Option Explicit

Dim shell, fileSystem, command, argument, errorNumber, errorDescription
Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")
shell.CurrentDirectory = fileSystem.GetParentFolderName(WScript.ScriptFullName)

command = "pythonw.exe -m gui.background_launcher"
For Each argument In WScript.Arguments
  command = command & " """ & argument & """"
Next

On Error Resume Next
shell.Run command, 0, False
errorNumber = Err.Number
errorDescription = Err.Description
Err.Clear

If errorNumber <> 0 Then
  command = "pyw.exe -3 -m gui.background_launcher"
  For Each argument In WScript.Arguments
    command = command & " """ & argument & """"
  Next
  shell.Run command, 0, False
  errorNumber = Err.Number
  errorDescription = Err.Description
End If
On Error GoTo 0

If errorNumber <> 0 Then
  MsgBox "找不到可用的 Python 背景執行程式" & vbCrLf & _
    "請確認 Python 3.10 以上版本已安裝, 或使用 launch-gui.cmd 查看詳細錯誤" & vbCrLf & _
    errorDescription, vbCritical, "My Py Tools"
End If
