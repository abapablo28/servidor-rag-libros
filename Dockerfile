# Usamos una versión ligera de Python 3.11
FROM python:3.11-slim

# Evitar que Python escriba archivos .pyc en disco y enviar logs directamente
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Instalamos dependencias del sistema necesarias para compilar librerías de IA
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Establecemos el directorio de trabajo
WORKDIR /app

# Copiamos solo los archivos de dependencias primero para optimizar la caché de Docker
COPY pyproject.toml requirements.txt ./

# Instalamos el proyecto
RUN pip install --no-cache-dir .

# Copiamos el resto de los archivos (excepto lo que esté en .dockerignore)
COPY . .

# Exponemos el puerto del servidor web SSE
EXPOSE 8000

# Comando para correr el MCP (obligatorio el --web)
CMD ["python", "server.py", "--web"]
