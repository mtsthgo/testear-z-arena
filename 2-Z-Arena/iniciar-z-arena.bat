@echo off
setlocal
cd /d "%~dp0"

rem Busca una instalacion normal de Python aunque el comando "py" no exista.
set "PYTHON_EXE="
for /d %%D in ("%USERPROFILE%\AppData\Local\Programs\Python\Python*") do (
  if exist "%%~fD\python.exe" set "PYTHON_EXE=%%~fD\python.exe"
)

if not defined PYTHON_EXE (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    if not defined PYTHON_EXE if /i not "%%P"=="%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe" set "PYTHON_EXE=%%P"
  )
)

if not defined PYTHON_EXE (
  echo No se encontro Python 3. Instala Python desde python.org y vuelve a abrir este archivo.
  pause
  exit /b 1
)

"%PYTHON_EXE%" "%~dp0z-arena-server.py"
if errorlevel 1 (
  echo.
  echo Z-Arena termino con un error. Revisa el mensaje anterior.
  pause
)
