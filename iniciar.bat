@echo off
title Servidor RAG SAP (MCP)
cd /d "%~dp0"

echo ===================================================
echo        Iniciando Servidor RAG SAP (MCP)
echo ===================================================

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creando entorno virtual...
    python -m venv .venv
    echo [2/3] Instalando dependencias...
    .\.venv\Scripts\pip install -r requirements.txt
)

echo [3/3] Arrancando servidor MCP...
echo Seleccione el modo de ejecucion:
echo   1. Modo Web / SSE / Streamable HTTP (Puerto 8000 para Claude Web / ChatGPT)
echo   2. Modo STDIO (Para Antigravity / Claude Desktop)
set /p modo="Elija una opcion (1 o 2, por defecto 1): "

if "%modo%"=="2" (
    echo Iniciando en modo STDIO...
    .\.venv\Scripts\python.exe server.py
) else (
    echo Iniciando en modo Web en http://localhost:8000 ...
    .\.venv\Scripts\python.exe server.py --web
)

pause
