#!/bin/bash
# Script de inicio para Render
# Render usa el puerto 10000 por defecto

export PORT=${PORT:-10000}
export PYTHONUNBUFFERED=1

echo "Starting Binance Trading Bot on port $PORT"
echo "Environment: $ENVIRONMENT"
echo "Python version: $(python --version)"

# Ejecutar el servidor
python server.py
