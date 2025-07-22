# Binance Trading Bot - Despliegue en Render

## Configuración en Render

### 1. Crear cuenta en Render
- Ve a https://render.com
- Regístrate con tu cuenta de GitHub

### 2. Conectar repositorio
- Haz clic en "New +" → "Web Service"
- Conecta tu repositorio de GitHub
- Selecciona la rama `main`

### 3. Configuración del servicio
- **Name**: `binance-trading-bot`
- **Environment**: `Docker`
- **Plan**: `Starter` ($7/mes) o `Free` (con limitaciones)
- **Dockerfile Path**: `./Dockerfile`

### 4. Variables de entorno (Environment Variables)
Configura las siguientes variables en la sección "Environment":

```
API_KEY=tu_api_key_de_binance
API_SECRET=tu_api_secret_de_binance
SUPABASE_URL=tu_url_de_supabase
SUPABASE_KEY=tu_key_de_supabase
TELEGRAM_TOKEN=tu_token_de_telegram
TELEGRAM_CHAT_ID=tu_chat_id_de_telegram
USE_TESTNET=True
ENVIRONMENT=production
PORT=10000
PYTHON_UNBUFFERED=1
```

### 5. Configuración avanzada
- **Auto-Deploy**: `Yes` (para despliegue automático desde GitHub)
- **Health Check Path**: `/health`
- **Start Command**: Se usa el CMD del Dockerfile automáticamente

### 6. Despliegue
- Haz clic en "Create Web Service"
- Render construirá y desplegará automáticamente
- El proceso toma 5-10 minutos

### 7. Monitoreo
- **URL del servicio**: `https://tu-servicio.onrender.com`
- **Endpoint de salud**: `https://tu-servicio.onrender.com/health`
- **Logs**: Disponibles en tiempo real en el dashboard de Render

## Ventajas de Render vs Google Cloud

✅ **Configuración simple**: Sin problemas de permisos IAM
✅ **Despliegue automático**: Desde GitHub
✅ **SSL automático**: HTTPS incluido
✅ **Logs en tiempo real**: Interfaz web amigable
✅ **Escalado automático**: Según demanda
✅ **Precio predecible**: $7/mes plan Starter

## Solución de problemas

### Bot no inicia
- Verificar variables de entorno
- Revisar logs en el dashboard
- Confirmar que el puerto 10000 esté disponible

### Errores de conexión
- Verificar credenciales de Binance
- Confirmar configuración de Supabase
- Revisar tokens de Telegram

### Performance
- Plan Free: Limitaciones de CPU/memoria
- Plan Starter: Mejor para producción 24/7
