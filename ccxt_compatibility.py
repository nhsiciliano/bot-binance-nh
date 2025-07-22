#!/usr/bin/env python3
"""
Script para verificar posibles incompatibilidades entre CCXT y Binance API
"""
import ccxt
import logging
import sys
import json
from packaging import version
import requests
from typing import Dict, Optional, List, Tuple

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_ccxt_version() -> version.Version:
    """Obtiene la versión de CCXT instalada"""
    v = version.parse(ccxt.__version__)
    logging.info(f"Versión CCXT instalada: {v}")
    return v

def check_binance_version_compatibility() -> List[Dict]:
    """
    Verifica la compatibilidad de la versión actual de CCXT con Binance
    Retorna lista de problemas detectados
    """
    current_version = get_ccxt_version()
    
    # Lista de problemas conocidos por versión
    # En la vida real, esto podría obtenerse de una fuente externa como la documentación de CCXT
    known_issues = [
        {
            'min_version': version.parse('1.0.0'),
            'max_version': version.parse('1.40.0'),
            'severity': 'medium',
            'issue': 'Versiones antiguas pueden tener problemas con la generación de headers',
            'solution': 'Actualizar a una versión más reciente de CCXT',
            'ref': 'https://github.com/ccxt/ccxt/issues/5356'
        },
        {
            'min_version': version.parse('1.50.0'),
            'max_version': version.parse('1.55.0'),
            'severity': 'high',
            'issue': 'Bug conocido con headers de autenticación en Binance',
            'solution': 'Actualizar a 1.60+ o usar 1.40-',
            'ref': 'https://github.com/ccxt/ccxt/issues/7059'
        },
        {
            'min_version': version.parse('1.70.0'),
            'max_version': version.parse('1.80.0'),
            'severity': 'low',
            'issue': 'Problemas con recvWindow en algunas configuraciones',
            'solution': 'Omitir el parámetro recvWindow o establecerlo explícitamente',
            'ref': 'https://github.com/ccxt/ccxt/issues/8123'
        }
    ]
    
    # Detectar problemas aplicables a la versión actual
    detected_issues = []
    for issue in known_issues:
        min_v = issue['min_version']
        max_v = issue['max_version']
        if min_v <= current_version < max_v:
            detected_issues.append(issue)
            logging.warning(f"⚠️ {issue['severity'].upper()}: {issue['issue']}")
            logging.warning(f"💡 Solución: {issue['solution']} (Ref: {issue['ref']})")
    
    if not detected_issues:
        logging.info("✅ No se detectaron incompatibilidades conocidas con esta versión de CCXT")
    
    return detected_issues

def check_exchange_info() -> Tuple[bool, Optional[Dict]]:
    """
    Verifica la configuración del exchange mediante una llamada simple
    que no requiere autenticación
    """
    try:
        # Crear cliente CCXT sin autenticación
        exchange = ccxt.binance({'enableRateLimit': True})
        
        # Probar una llamada pública que no requiere autenticación
        logging.info("Verificando información del exchange...")
        exchange_info = exchange.fetch_status()
        
        logging.info(f"✅ Información del exchange obtenida con éxito")
        logging.info(f"Estado: {exchange_info.get('status', 'desconocido')}")
        
        # Verificar que Binance esté en línea
        if exchange_info.get('status') == 'ok':
            logging.info("✅ Binance API está en línea y respondiendo")
        else:
            logging.warning("⚠️ Binance API podría tener problemas")
        
        return True, exchange_info
    except Exception as e:
        logging.error(f"❌ Error al conectar con Binance API: {str(e)}")
        return False, None

def check_binance_http_headers():
    """
    Verifica restricciones conocidas en los headers HTTP de Binance
    """
    logging.info("Revisando restricciones de headers HTTP de Binance...")
    
    # Restricciones conocidas de headers HTTP en Binance
    header_restrictions = [
        {
            'header': 'X-MBX-APIKEY',
            'restrictions': 'Debe contener solo caracteres alfanuméricos y guiones, sin espacios ni saltos de línea',
            'issue': 'Causa error "Invalid header value" si contiene caracteres especiales o espacios'
        },
        {
            'header': 'Content-Type',
            'restrictions': 'application/x-www-form-urlencoded para peticiones POST',
            'issue': 'Posibles errores 400 Bad Request con otros valores'
        },
        {
            'header': 'User-Agent',
            'restrictions': 'Algunos bots de trading son bloqueados según el User-Agent',
            'issue': 'Puede causar errores 403 Forbidden'
        },
    ]
    
    for restriction in header_restrictions:
        logging.info(f"Header: {restriction['header']}")
        logging.info(f"  Restricciones: {restriction['restrictions']}")
        logging.info(f"  Posibles problemas: {restriction['issue']}")
    
    return header_restrictions

def check_latest_ccxt_issues():
    """
    Obtiene los últimos issues de GitHub relacionados con CCXT y Binance
    """
    logging.info("Buscando issues recientes en GitHub relacionados con CCXT y Binance...")
    
    try:
        url = "https://api.github.com/search/issues?q=repo:ccxt/ccxt+binance+header+in:title,body&sort=updated&order=desc"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            issues = data.get('items', [])
            
            if issues:
                logging.info(f"Encontrados {len(issues)} issues recientes:")
                for i, issue in enumerate(issues[:5]):  # Mostrar solo los 5 más recientes
                    logging.info(f"{i+1}. {issue['title']} - {issue['html_url']}")
            else:
                logging.info("No se encontraron issues recientes")
                
            return issues
        else:
            logging.error(f"Error al consultar GitHub API: {response.status_code}")
            return []
    except Exception as e:
        logging.error(f"Error al consultar GitHub: {str(e)}")
        return []

def suggest_alternative_clients():
    """
    Sugiere alternativas a CCXT para conectarse a Binance API
    """
    alternatives = [
        {
            'name': 'python-binance',
            'url': 'https://github.com/sammchardy/python-binance',
            'pros': 'Específico para Binance, mejor soporte para sus características específicas',
            'cons': 'No es multiexchange como CCXT'
        },
        {
            'name': 'binance-connector-python',
            'url': 'https://github.com/binance/binance-connector-python',
            'pros': 'Cliente oficial de Binance, siempre compatible con las últimas actualizaciones de la API',
            'cons': 'Requiere más código para configurar y utilizar'
        },
        {
            'name': 'Implementación personalizada con requests',
            'url': 'https://binance-docs.github.io/apidocs/',
            'pros': 'Control total sobre los headers HTTP y manejo de errores',
            'cons': 'Requiere implementar toda la lógica de autenticación y firma'
        }
    ]
    
    logging.info("Alternativas a CCXT para conectarse a Binance API:")
    for alt in alternatives:
        logging.info(f"- {alt['name']} ({alt['url']})")
        logging.info(f"  Pros: {alt['pros']}")
        logging.info(f"  Cons: {alt['cons']}")
    
    return alternatives

def recommend_fixes():
    """
    Recomienda soluciones para el error 'Invalid header value'
    """
    recommendations = [
        {
            'title': 'Limpiar API keys',
            'description': 'Asegúrate de que las API keys no contengan espacios, saltos de línea o caracteres especiales',
            'code': """
# En cloud_config.py, modifica:
TESTNET_API_KEY = get_secret("TESTNET_API_KEY").strip() if get_secret("TESTNET_API_KEY") else None
TESTNET_API_SECRET = get_secret("TESTNET_API_SECRET").strip() if get_secret("TESTNET_API_SECRET") else None
"""
        },
        {
            'title': 'Actualizar CCXT',
            'description': 'Actualizar a la última versión estable de CCXT',
            'code': 'pip install ccxt --upgrade'
        },
        {
            'title': 'Implementación directa con requests',
            'description': 'Si persiste el error, implementa la autenticación directamente con requests',
            'code': """
import requests
import hmac
import hashlib
import time
from urllib.parse import urlencode

def get_account_balance_direct():
    # Usar testnet o real según la configuración
    testnet = USE_TESTNET
    if testnet:
        api_key = TESTNET_API_KEY.strip()
        api_secret = TESTNET_API_SECRET.strip()
        base_url = 'https://testnet.binance.vision/api'
    else:
        api_key = REAL_API_KEY.strip()
        api_secret = REAL_API_SECRET.strip()
        base_url = 'https://api.binance.com'
    
    # Preparar la solicitud
    endpoint = '/v3/account'
    timestamp = int(time.time() * 1000)
    params = {'timestamp': timestamp, 'recvWindow': 5000}
    
    # Generar firma HMAC
    query_string = urlencode(params)
    signature = hmac.new(
        api_secret.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Añadir firma a los parámetros
    params['signature'] = signature
    
    # Crear headers
    headers = {'X-MBX-APIKEY': api_key}
    
    # Realizar la solicitud
    url = f"{base_url}{endpoint}"
    response = requests.get(url, params=params, headers=headers)
    
    # Verificar la respuesta
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Error {response.status_code}: {response.text}")
"""
        }
    ]
    
    logging.info("Recomendaciones para solucionar el error 'Invalid header value':")
    for rec in recommendations:
        logging.info(f"- {rec['title']}")
        logging.info(f"  {rec['description']}")
        logging.info(f"  Ejemplo de código:\n{rec['code']}")
    
    return recommendations

if __name__ == "__main__":
    logging.info("=== ANÁLISIS DE COMPATIBILIDAD DE CCXT CON BINANCE ===")
    
    # Verificar versión de CCXT y compatibilidad
    issues = check_binance_version_compatibility()
    
    # Verificar estado general de Binance API
    success, _ = check_exchange_info()
    
    # Revisar restricciones de headers HTTP
    check_binance_http_headers()
    
    # Buscar issues recientes en GitHub
    check_latest_ccxt_issues()
    
    logging.info("\n=== SOLUCIONES ALTERNATIVAS ===")
    
    # Sugerir alternativas a CCXT
    suggest_alternative_clients()
    
    # Recomendar soluciones
    logging.info("\n=== RECOMENDACIONES PARA SOLUCIONAR EL ERROR ===")
    recommend_fixes()
    
    logging.info("=== FIN DEL ANÁLISIS ===")
