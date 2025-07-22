"""
Manejo de configuración para entornos cloud y locales
"""

import os
import logging
from dotenv import load_dotenv
from pathlib import Path

# Intentar cargar variables desde archivo .env (desarrollo local)
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    logging.info("Variables de entorno cargadas desde archivo .env")
else:
    logging.info("No se encontró archivo .env, usando variables de entorno del sistema")

# Intentar importar Google Cloud Secret Manager si estamos en GCP
try:
    from google.cloud import secretmanager
    USING_GCP = True
    logging.info("Google Cloud Secret Manager disponible")
except ImportError:
    USING_GCP = False
    logging.info("Google Cloud Secret Manager no disponible, asumiendo entorno local")

def get_secret(secret_name, default=None):
    """
    Obtiene un secreto desde GCP Secret Manager o variable de entorno
    """
    # Primero intentar leer desde variable de entorno
    value = os.getenv(secret_name)
    
    # Si no existe y estamos en GCP, intentar con Secret Manager
    if value is None and USING_GCP:
        try:
            project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
            if project_id:
                client = secretmanager.SecretManagerServiceClient()
                name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
                response = client.access_secret_version(request={"name": name})
                value = response.payload.data.decode("UTF-8")
                logging.info(f"Secreto {secret_name} cargado desde GCP Secret Manager")
        except Exception as e:
            logging.error(f"Error al obtener secreto {secret_name} desde GCP: {e}")
    
    # Si no pudimos obtener el valor, usar el valor por defecto
    if value is None:
        if default is not None:
            logging.warning(f"No se encontró valor para {secret_name}, usando valor por defecto")
            return default
        else:
            logging.warning(f"No se encontró valor para {secret_name} y no hay valor por defecto")
    
    return value

# Configuración de API keys
TESTNET_API_KEY = get_secret("TESTNET_API_KEY").strip() if get_secret("TESTNET_API_KEY") else None
TESTNET_API_SECRET = get_secret("TESTNET_API_SECRET").strip() if get_secret("TESTNET_API_SECRET") else None
# Para las API keys reales, buscar primero REAL_API_KEY/REAL_API_SECRET y luego API_KEY/API_SECRET como fallback
REAL_API_KEY = get_secret("REAL_API_KEY", get_secret("API_KEY")).strip() if get_secret("REAL_API_KEY") or get_secret("API_KEY") else None
REAL_API_SECRET = get_secret("REAL_API_SECRET", get_secret("API_SECRET")).strip() if get_secret("REAL_API_SECRET") or get_secret("API_SECRET") else None
USE_TESTNET = get_secret("USE_TESTNET", "True").lower() in ("true", "t", "1")

# Configuración de Supabase
SUPABASE_URL = get_secret("SUPABASE_URL", "https://ajpyfvfkqdttgcswbshd.supabase.co")
SUPABASE_KEY = get_secret("SUPABASE_KEY")

# Configuración de Telegram
TELEGRAM_TOKEN = get_secret("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

# Configuración de logs
LOG_FILE = get_secret("LOG_FILE", "trading_bot.log")
