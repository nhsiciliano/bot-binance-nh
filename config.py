"""
Archivo de configuración para el bot de trading
"""

# Configuración de Supabase
SUPABASE_URL = "https://ajpyfvfkqdttgcswbshd.supabase.co"  # Reemplaza con tu URL de Supabase
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFqcHlmdmZrcWR0dGdjc3dic2hkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDkzMzg3MzgsImV4cCI6MjA2NDkxNDczOH0.Gao5uuC9PKZY98Q5CA6_n6dzvcuyJqh_iGWjHxb_43k"  # Reemplaza con tu API Key de Supabase

# Configuración de notificaciones
EMAIL_CONFIG = {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_user": "tu-email@gmail.com",
    "smtp_password": "tu-contraseña-app",
    "from_email": "tu-email@gmail.com",
    "to_email": "destinatario@email.com"
}

# Configuración de Telegram (opcional)
TELEGRAM_CONFIG = {
    "bot_token": "",
    "chat_id": ""
}

# Ruta de logs
LOG_FILE = "trading_bot.log"
