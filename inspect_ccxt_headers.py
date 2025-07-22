#!/usr/bin/env python3
"""
Script para inspeccionar y depurar los headers generados por CCXT para la API de Binance
"""
import logging
import ccxt
import json
import re
import sys
from typing import Dict, Optional
from cloud_config import TESTNET_API_KEY, TESTNET_API_SECRET, REAL_API_KEY, REAL_API_SECRET, USE_TESTNET

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Clase de intercepción para capturar los headers
class HeaderInterceptor:
    def __init__(self):
        self.captured_headers = []
    
    def capture(self, response):
        """Captura headers de respuesta y request"""
        request_headers = getattr(response, 'request_headers', {})
        self.captured_headers.append({
            'url': response.url if hasattr(response, 'url') else 'unknown',
            'request_headers': request_headers
        })
        return response

def strip_credentials(header_dict):
    """Elimina o enmascara credenciales sensibles de los headers para mostrarlos de forma segura"""
    sanitized = {}
    for k, v in header_dict.items():
        if k.lower() in ('authorization', 'x-mbx-apikey'):
            if v and len(v) > 8:
                sanitized[k] = v[:4] + '****' + v[-4:]
            else:
                sanitized[k] = '****'
        else:
            sanitized[k] = v
    return sanitized

def validate_header_value(header_name, header_value):
    """
    Valida un valor de header según RFC7230
    Los headers HTTP no deben contener ciertos caracteres y estructuras
    """
    if header_value is None:
        logging.error(f"Header '{header_name}' tiene valor None")
        return False
    
    # Expresión regular para caracteres válidos en headers según RFC7230
    valid_pattern = re.compile(r'^[\x20-\x7E]*$')
    
    if not valid_pattern.match(str(header_value)):
        logging.error(f"Header '{header_name}' contiene caracteres inválidos: {repr(header_value)}")
        return False
    
    # Verificar caracteres problemáticos específicos
    problematic_chars = ['\n', '\r', '\0', '\t']
    for char in problematic_chars:
        if char in str(header_value):
            logging.error(f"Header '{header_name}' contiene caracter problemático: {repr(char)}")
            return False
    
    return True

def custom_auth_headers():
    """
    Genera headers de autenticación personalizados para probar si hay problemas
    con los headers generados por CCXT
    """
    from urllib.parse import urlencode
    import hmac
    import hashlib
    import time
    
    # Use testnet or real based on config
    testnet = USE_TESTNET
    if testnet:
        api_key = TESTNET_API_KEY
        api_secret = TESTNET_API_SECRET
        base_url = 'https://testnet.binance.vision/api'
    else:
        api_key = REAL_API_KEY
        api_secret = REAL_API_SECRET
        base_url = 'https://api.binance.com'
    
    # Parámetros para la solicitud de balance
    endpoint = '/v3/account'
    timestamp = int(time.time() * 1000)
    params = {'timestamp': timestamp, 'recvWindow': 5000}
    
    # Crear firma HMAC
    query_string = urlencode(params)
    signature = hmac.new(
        api_secret.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Añadir firma a los parámetros
    params['signature'] = signature
    full_url = f"{base_url}{endpoint}?{urlencode(params)}"
    
    # Crear headers
    headers = {
        'X-MBX-APIKEY': api_key
    }
    
    # Validar headers
    for name, value in headers.items():
        if not validate_header_value(name, value):
            logging.error(f"Header personalizado inválido: {name}")
    
    return {
        'url': full_url,
        'headers': headers
    }

def check_ccxt_binance_compatibility():
    """Verifica la compatibilidad de la versión de CCXT con Binance"""
    logging.info(f"Versión de CCXT: {ccxt.__version__}")
    
    # Verificar problemas conocidos según la versión
    version = tuple(map(int, ccxt.__version__.split('.')))
    
    known_issues = [
        {
            'min_version': (1, 0, 0),
            'max_version': (1, 50, 0),
            'issue': 'Versiones antiguas pueden tener problemas con la generación de headers',
            'solution': 'Actualizar a una versión más reciente de CCXT'
        },
        {
            'min_version': (1, 50, 0),
            'max_version': (1, 60, 0),
            'issue': 'Algunas versiones tienen problemas con la autenticación en Binance',
            'solution': 'Revisar headers y considerar cambiar a versión 1.60+ o 1.40-'
        }
    ]
    
    for issue in known_issues:
        min_v = issue['min_version']
        max_v = issue['max_version']
        if min_v <= version < max_v:
            logging.warning(f"⚠️ Posible problema de compatibilidad: {issue['issue']}")
            logging.warning(f"💡 Solución recomendada: {issue['solution']}")

def analyze_api_key_format():
    """Analiza el formato de las API keys en busca de problemas"""
    # Oculta parte de las keys por seguridad
    def analyze_key(name, key):
        if not key:
            logging.error(f"⚠️ {name} no está configurada o está vacía")
            return False
        
        # Verificar longitud
        if len(key) < 10:
            logging.warning(f"⚠️ {name} parece demasiado corta ({len(key)} caracteres)")
        
        # Verificar caracteres especiales o espacios
        has_special = any(not c.isalnum() for c in key)
        if has_special:
            logging.warning(f"⚠️ {name} contiene caracteres especiales que podrían causar problemas")
            
            # Destacar específicamente los problemas con espacios
            if any(c.isspace() for c in key):
                logging.error(f"❌ {name} contiene espacios, saltos de línea o tabulaciones")
                logging.error(f"Valor con escapes: {repr(key)}")
                return False
        
        return True
    
    keys_valid = True
    keys_valid &= analyze_key("TESTNET_API_KEY", TESTNET_API_KEY)
    keys_valid &= analyze_key("TESTNET_API_SECRET", TESTNET_API_SECRET)
    keys_valid &= analyze_key("REAL_API_KEY", REAL_API_KEY)
    keys_valid &= analyze_key("REAL_API_SECRET", REAL_API_SECRET)
    
    return keys_valid

def test_minimal_fetch():
    """Test con la configuración más simple posible"""
    # Use testnet or real based on config
    testnet = USE_TESTNET
    if testnet:
        api_key = TESTNET_API_KEY
        api_secret = TESTNET_API_SECRET
    else:
        api_key = REAL_API_KEY
        api_secret = REAL_API_SECRET
    
    # Crear un exchange con configuración mínima
    exchange = ccxt.binance({
        'apiKey': api_key.strip(),  # Eliminar espacios en blanco
        'secret': api_secret.strip(),  # Eliminar espacios en blanco
        'enableRateLimit': True,
    })
    
    if testnet:
        exchange.urls['api'] = 'https://testnet.binance.vision/api'
        exchange.set_sandbox_mode(True)
    
    try:
        # Intentar obtener balance con configuración mínima
        logging.info("🧪 Intentando obtener balance con configuración mínima...")
        balance = exchange.fetch_balance()
        logging.info("✅ Balance obtenido correctamente")
        return True
    except Exception as e:
        logging.error(f"❌ Error con configuración mínima: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    logging.info("=== DIAGNÓSTICO DE HEADERS CCXT PARA BINANCE ===")
    
    # Verificar versión y compatibilidad de CCXT
    check_ccxt_binance_compatibility()
    
    # Analizar formato de API keys
    logging.info("\n=== ANÁLISIS DE FORMATO DE API KEYS ===")
    if analyze_api_key_format():
        logging.info("✅ Formato de API keys parece correcto")
    else:
        logging.error("❌ Problemas detectados en formato de API keys")
    
    # Generar headers personalizados
    logging.info("\n=== GENERACIÓN DE HEADERS PERSONALIZADOS ===")
    auth_data = custom_auth_headers()
    logging.info(f"Headers personalizados generados: {json.dumps(auth_data['headers'], indent=2)}")
    logging.info(f"URL: {auth_data['url']}")
    
    # Probar con configuración mínima
    logging.info("\n=== PRUEBA CON CONFIGURACIÓN MÍNIMA ===")
    if test_minimal_fetch():
        logging.info("✅ Prueba con configuración mínima exitosa")
    else:
        logging.error("❌ Prueba con configuración mínima falló")
    
    logging.info("=== FIN DEL DIAGNÓSTICO ===")
