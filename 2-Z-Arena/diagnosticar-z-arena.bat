@echo off
setlocal
echo === Diagnostico de Z-Arena ===
echo Deja abierta la ventana del servidor mientras corre este archivo.
echo.
echo 1. Proceso que escucha en el puerto 8765:
powershell -NoProfile -Command "$c=Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue; if ($c) {$c | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize} else {Write-Output 'NO HAY PROCESO ESCUCHANDO EN 8765'}"
echo.
echo 2. Peticion HTTP directa sin proxy:
curl.exe --noproxy "*" --max-time 5 -sS -o NUL -w "HTTP %%{http_code}\n" http://127.0.0.1:8765/
echo.
echo Si aparece HTTP 200, el servidor responde; el problema queda en el navegador/proxy.
echo Si aparece HTTP 000 o no hay proceso escuchando, el servidor no esta activo en esta PC.
echo Copia el resultado completo y pegalo en el chat.
pause
