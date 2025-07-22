#!/usr/bin/env python3
"""
Script para depurar el error "Invalid header value" en la obtención del balance de cuenta
"""
import logging
import ccxt
import sys
import json
from typing import Dict, Optional
from cloud_config import TESTNET_API_KEY, TESTNET_API_SECRET, REAL_API_KEY, REAL_API_SECRET, USE_TESTNET

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def inspect_api_keys():
    """Inspecciona el formato y caracteres de las API keys"""
    # Oculta parte de las keys por seguridad
    def mask_string(s):
        if not s:
            return "None or Empty"
        if len(s) <= 8:
            return "*" * len(s)
        return s[:4] + "*" * (len(s) - 8) + s[-4:]
    
    keys = {
        "TESTNET_API_KEY": TESTNET_API_KEY,
        "TESTNET_API_SECRET": TESTNET_API_SECRET,
        "REAL_API_KEY": REAL_API_KEY,
        "REAL_API_SECRET": REAL_API_SECRET
    }
    
    for key_name, key_value in keys.items():
        logging.info(f"{key_name} - Formato:")
        logging.info(f"  - Valor (enmascarado): {mask_string(key_value)}")
        if key_value:
            logging.info(f"  - Longitud: {len(key_value)}")
            logging.info(f"  - Tipo: {type(key_value)}")
            # Verificar si hay espacios, saltos de línea u otros caracteres problemáticos
            has_special_chars = any(c.isspace() for c in key_value)
            logging.info(f"  - Contiene espacios o saltos: {has_special_chars}")
            if has_special_chars:
                logging.warning(f"  - ⚠️ {key_name} contiene caracteres especiales que pueden causar problemas en headers HTTP")

def get_binance_client(testnet: Optional[bool] = None) -> ccxt.binance:
    """
    Crea y retorna un cliente de CCXT para Binance con logging detallado
    """
    if testnet is None:
        testnet = USE_TESTNET
    
    # Decidir qué credenciales usar
    if testnet:
        api_key = TESTNET_API_KEY
        api_secret = TESTNET_API_SECRET
        urls = {
            'api': 'https://testnet.binance.vision/api',
        }
    else:
        api_key = REAL_API_KEY
        api_secret = REAL_API_SECRET
        urls = {}  # URLs por defecto para la API real
    
    if not api_key or not api_secret:
        logging.error(f"⚠️ {'Testnet' if testnet else 'Real'} API keys no configuradas.")
        raise ValueError(f"{'Testnet' if testnet else 'Real'} API keys no configuradas")
    
    # Crear cliente CCXT con verbose=True para ver requests
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'verbose': True,  # Habilita el debug para ver las peticiones HTTP
        'options': {
            'defaultType': 'future',
            'adjustForTimeDifference': True,
            'recvWindow': 10000,
        },
        'urls': urls
    })
    
    # Configurar para testnet si es necesario
    if testnet:
        exchange.set_sandbox_mode(True)
        logging.info("🧪 Usando Binance Testnet API")
    else:
        logging.info("🔴 Usando Binance API Real")
    
    return exchange

def get_account_balance(testnet: Optional[bool] = None) -> Dict:
    """
    Obtiene el balance de la cuenta con captura detallada de errores
    """
    exchange = get_binance_client(testnet)
    
    try:
        logging.info("📊 Intentando obtener balance de cuenta...")
        balance = exchange.fetch_balance()
        logging.info("✅ Balance obtenido correctamente")
        return balance
    except ccxt.InvalidNonce as e:
        logging.error(f"❌ Error de nonce inválido: {str(e)}")
        logging.error("💡 Solución: Sincroniza el reloj del sistema o utiliza nonce personalizado")
        return {}
    except ccxt.AuthenticationError as e:
        logging.error(f"❌ Error de autenticación: {str(e)}")
        logging.error("💡 Solución: Verifica las API keys y secretos")
        return {}
    except ccxt.ExchangeError as e:
        logging.error(f"❌ Error del exchange: {str(e)}")
        if "Invalid header value" in str(e):
            logging.error("💡 Error de header inválido detectado - Probable problema con formato de API key/secret")
        return {}
    except Exception as e:
        logging.error(f"❌ Error inesperado al obtener balance: {str(e)}")
        logging.error(f"Tipo de error: {type(e)}")
        import traceback
        logging.error(f"Stacktrace completo:\n{traceback.format_exc()}")
        return {}

def test_simple_client():
    """Prueba un cliente CCXT con configuración mínima"""
    logging.info("🧪 Probando cliente CCXT con configuración mínima...")
    
    # Decidir qué credenciales usar
    testnet = USE_TESTNET
    if testnet:
        api_key = TESTNET_API_KEY
        api_secret = TESTNET_API_SECRET
        urls = {'api': 'https://testnet.binance.vision/api'}
    else:
        api_key = REAL_API_KEY
        api_secret = REAL_API_SECRET
        urls = {}
    
    # Crear cliente CCXT simplificado
    try:
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'verbose': True,
        })
        
        if testnet:
            exchange.set_sandbox_mode(True)
        
        logging.info("🔍 Intentando obtener mercados (no requiere auth)...")
        markets = exchange.load_markets()
        logging.info(f"✅ Mercados cargados: {len(markets)} pares disponibles")
        
        logging.info("🔍 Intentando obtener balance con cliente simple...")
        balance = exchange.fetch_balance()
        logging.info("✅ Balance obtenido correctamente con cliente simple")
    except Exception as e:
        logging.error(f"❌ Error con cliente simple: {str(e)}")
        import traceback
        logging.error(f"Stacktrace:\n{traceback.format_exc()}")

if __name__ == "__main__":
    logging.info("=== DIAGNÓSTICO DE CLIENTE BINANCE ===")
    logging.info("Inspeccionando API keys...")
    inspect_api_keys()
    
    logging.info("\n=== PROBANDO OBTENCIÓN DE BALANCE ===")
    try:
        balance = get_account_balance()
        if balance:
            # Mostrar solo los saldos disponibles para no sobrecargar el log
            available = {k: v['free'] for k, v in balance['total'].items() if v['free'] > 0}
            logging.info(f"Saldos disponibles: {json.dumps(available, indent=2)}")
    except Exception as e:
        logging.error(f"Error en test principal: {e}")
    
    logging.info("\n=== PROBANDO CLIENTE SIMPLIFICADO ===")
    test_simple_client()
    
    logging.info("=== FIN DEL DIAGNÓSTICO ===")
