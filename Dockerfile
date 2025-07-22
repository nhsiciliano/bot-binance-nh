FROM python:3.10-slim

WORKDIR /app

# Instalar dependencias básicas y herramientas de compilación (reducidas)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements.txt y instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el código del proyecto
COPY . .

# Asegurar que los scripts tengan permisos de ejecución
RUN chmod +x server.py start.sh

# Variables de entorno para Render
ENV PORT=10000
ENV PYTHONUNBUFFERED=1

# Exponer el puerto (Render usa 10000 por defecto)
EXPOSE 10000

# Comando para ejecutar el servidor
CMD ["python", "server.py"]
