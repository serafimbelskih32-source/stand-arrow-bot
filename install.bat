@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
for %%V in (3.13 3.12 3.11 3.10) do call :try py -%%V
for %%V in (313 312 311 310) do call :try "%LocalAppData%\Programs\Python\Python%%V\python.exe"
call :try python
if not defined PY (
  echo Не нашёл подходящий Python с pip. Поставь Python 3.12 или 3.13 с python.org, при установке отметь Add Python to PATH, и запусти этот файл снова.
  pause
  exit /b 1
)
echo Использую: %PY%
echo Устанавливаю библиотеки, это несколько минут...
%PY% -m pip install mss pyautogui keyboard rapidocr-onnxruntime opencv-python numpy
if errorlevel 1 (
  echo Не получилось установить библиотеки. Скопируй текст выше и пришли тому, кто дал тебе программу.
  pause
  exit /b 1
)
%PY% -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" > "%TEMP%\arrowbot_pyw.txt"
set /p PYW=<"%TEMP%\arrowbot_pyw.txt"
del "%TEMP%\arrowbot_pyw.txt" >nul 2>nul
if not exist "%PYW%" (
  echo Не нашёл pythonw.exe, ярлык не создан. Запускай arrow_gui.pyw двойным кликом.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Arrow Bot.lnk'); $s.TargetPath='%PYW%'; $s.Arguments='\"%~dp0arrow_gui.pyw\"'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%PYW%,0'; $s.Save()"
echo.
echo Готово. На рабочем столе появился ярлык Arrow Bot, запускай им, терминал больше не нужен.
pause
exit /b 0

:try
if defined PY exit /b
%* -c "import tkinter, pip" >nul 2>nul
if not errorlevel 1 set "PY=%*"
exit /b
