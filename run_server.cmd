@echo off
setlocal
cd /d "%~dp0"

REM 1. Si no existe el entorno virtual, crearlo e instalar dependencias silenciosamente
if not exist ".venv\Scripts\python.exe" (
    echo [Inicializando Servidor RAG SAP por primera vez...] >&2
    python -m venv .venv >&2
    .\.venv\Scripts\pip install -q -r requirements.txt >&2
)

REM 2. Ejecutar el servidor MCP en modo stdio pasando la entrada y salida estándar directamente
.\.venv\Scripts\python.exe server.py
