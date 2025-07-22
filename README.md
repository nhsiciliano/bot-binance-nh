# Bot de Trading Binance + Supabase

Bot automatizado de trading para criptomonedas que utiliza la API de Binance y almacena datos en Supabase.

## Características

- **Timeframe**: Análisis en timeframe de 4 horas (4h)
- **Indicadores**: Utiliza RSI y MACD adaptados para funcionar con datos limitados
- **Gestión de riesgo**: Stop loss y take profit configurables
- **Base de datos**: Integración con Supabase para almacenar operaciones y métricas
- **Notificaciones**: Alertas vía Telegram

## Configuración

1. Copia el archivo `.env.sample` a `.env` y configura tus credenciales:

```bash
cp .env.sample .env
nano .env  # Edita el archivo para configurar tus claves API
```

## Ejecución local

```bash
python3 bot.py
```

## Despliegue en Google Cloud Run

### Prerrequisitos

1. Cuenta de Google Cloud Platform
2. Google Cloud SDK instalado
3. Docker instalado localmente

### Paso 1: Autenticación con Google Cloud

```bash
gcloud auth login
gcloud config set project <tu-proyecto-id>
```

### Paso 2: Habilitar las APIs necesarias

```bash
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  cloudscheduler.googleapis.com
```

### Paso 3: Crear secretos en Secret Manager

```bash
# Crear secretos para las API keys
gcloud secrets create TESTNET_API_KEY --data-file=- <<< "tu-api-key"
gcloud secrets create TESTNET_API_SECRET --data-file=- <<< "tu-api-secret"
gcloud secrets create SUPABASE_KEY --data-file=- <<< "tu-supabase-key"
gcloud secrets create TELEGRAM_TOKEN --data-file=- <<< "tu-telegram-token"
gcloud secrets create TELEGRAM_CHAT_ID --data-file=- <<< "tu-chat-id"
```

### Paso 4: Construir y subir la imagen Docker

```bash
# Construir la imagen con Cloud Build
gcloud builds submit --tag gcr.io/<tu-proyecto-id>/binance-trading-bot .
```

### Paso 5: Desplegar en Cloud Run

```bash
gcloud run deploy binance-trading-bot \
  --image gcr.io/<tu-proyecto-id>/binance-trading-bot \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --cpu 1 \
  --memory 512Mi \
  --set-env-vars USE_TESTNET=True,SUPABASE_URL=https://ajpyfvfkqdttgcswbshd.supabase.co \
  --update-secrets=TESTNET_API_KEY=TESTNET_API_KEY:latest,TESTNET_API_SECRET=TESTNET_API_SECRET:latest,SUPABASE_KEY=SUPABASE_KEY:latest,TELEGRAM_TOKEN=TELEGRAM_TOKEN:latest,TELEGRAM_CHAT_ID=TELEGRAM_CHAT_ID:latest
```

### Paso 6: Configurar una tarea programada (opcional para ejecución periódica)

```bash
# Crear un servicio de App Engine (necesario para Cloud Scheduler)
gcloud app create --region=us-central

# Crear una tarea programada
gcloud scheduler jobs create http trading-bot-job \
  --schedule="*/30 * * * *" \
  --uri="https://<tu-cloud-run-url>/run" \
  --http-method=POST \
  --attempt-deadline=540s
```

## Monitorización

Para monitorizar el rendimiento del bot:

1. **Logs de Cloud Run**: Visualiza los logs directamente en la consola de GCP
2. **Supabase**: Revisa las métricas y operaciones en tu panel de Supabase
3. **Alertas**: Configura notificaciones de Telegram para eventos importantes

---

## Desarrollo

Para contribuir al proyecto:

1. Clona este repositorio
2. Instala las dependencias: `pip install -r requirements.txt`
3. Asegúrate de tener TA-Lib instalado: [Instrucciones](https://github.com/TA-Lib/ta-lib-python)
4. Configura tu archivo `.env` con tus credenciales
5. Ejecuta el bot: `python3 bot.py`
