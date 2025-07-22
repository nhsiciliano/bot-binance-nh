"""
Script para probar la configuración cloud del bot de trading
"""

import logging
import os

# Configurar logging básico
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Importar la configuración cloud
from cloud_config import (
    TESTNET_API_KEY, TESTNET_API_SECRET,
    REAL_API_KEY, REAL_API_SECRET,
    USE_TESTNET, SUPABASE_URL, SUPABASE_KEY,
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
)

def test_config():
    """Probar que la configuración cloud funciona correctamente"""
    
    print("\n===== PRUEBA DE CONFIGURACIÓN CLOUD =====\n")
    
    # Verificar API keys
    if USE_TESTNET:
        print(f"🔑 Modo: TESTNET")
    else:
        print(f"🔑 Modo: REAL")
        
    # Verificar API keys de Binance
    if TESTNET_API_KEY and len(TESTNET_API_KEY) > 10:
        print(f"✅ TESTNET_API_KEY: OK ({TESTNET_API_KEY[:5]}...{TESTNET_API_KEY[-5:]})")
    else:
        print(f"❌ TESTNET_API_KEY: No encontrada o inválida")
        
    if TESTNET_API_SECRET and len(TESTNET_API_SECRET) > 10:
        print(f"✅ TESTNET_API_SECRET: OK ({TESTNET_API_SECRET[:5]}...{TESTNET_API_SECRET[-5:]})")
    else:
        print(f"❌ TESTNET_API_SECRET: No encontrada o inválida")
    
    # Verificar conexión a Supabase
    if SUPABASE_URL and SUPABASE_KEY:
        print(f"✅ Supabase: URL y KEY configurados")
        print(f"   URL: {SUPABASE_URL}")
        print(f"   KEY: {SUPABASE_KEY[:5]}...{SUPABASE_KEY[-5:] if len(SUPABASE_KEY) > 10 else ''}")
    else:
        print(f"❌ Supabase: Configuración incompleta")
    
    # Verificar configuración de Telegram
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        print(f"✅ Telegram: Configurado")
        print(f"   TOKEN: {TELEGRAM_TOKEN[:5]}...{TELEGRAM_TOKEN[-5:] if len(TELEGRAM_TOKEN) > 10 else ''}")
        print(f"   CHAT_ID: {TELEGRAM_CHAT_ID}")
    else:
        print(f"⚠️ Telegram: Configuración incompleta o no requerida")
    
    print("\n========================================\n")
    
if __name__ == "__main__":
    test_config()
