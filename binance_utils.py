"""
Módulo para interactuar con Binance API
Provee utilidades para obtener datos OHLCV, crear órdenes, consultar balances, etc.
"""
import logging
import ccxt
import pandas as pd
import numpy as np
import time
import datetime
import threading
from typing import Dict, List, Optional, Union, Tuple
from cloud_config import TESTNET_API_KEY, TESTNET_API_SECRET, REAL_API_KEY, REAL_API_SECRET, USE_TESTNET

# Importar nuestro módulo personalizado de sincronización NTP
import ntp_sync

# Valor por defecto para recvWindow (aumentado para mayor tolerancia)
DEFAULT_RECV_WINDOW = 300000  # 300 segundos (5 minutos)

def get_timestamp_with_offset():
    """Obtiene timestamp actual ajustado con el offset"""
    # Usar nuestra implementación NTP para obtener un timestamp preciso
    adjusted_time = ntp_sync.get_timestamp_with_offset()
    return adjusted_time

def update_time_offset(server_time):
    """Actualiza el offset de tiempo basado en la hora del servidor"""
    # Usar nuestra implementación NTP para actualizar el offset
    ntp_sync.update_time_offset(server_time)

def synchronize_time(exchange, retry_count=5):
    """Sincroniza el reloj local con el del servidor de Binance"""
    # Utilizar nuestra implementación NTP para una sincronización completa
    testnet = exchange.urls.get('api') and 'testnet' in exchange.urls.get('api')
    logging.info(f"Iniciando sincronización de tiempo NTP (testnet={testnet})")
    
    try:
        # Realizar sincronización completa con NTP y Binance
        success = ntp_sync.full_sync()
        return success
    except Exception as e:
        logging.error(f"❌ Error al sincronizar tiempo: {str(e)}")
        return False

def get_binance_client(testnet: Optional[bool] = None) -> ccxt.binance:
    """
    Crea y retorna un cliente de CCXT para Binance
    
    Args:
        testnet: Si es True, usa API de testnet. Si es None, usa la configuración global.
    
    Returns:
        Instancia de cliente ccxt.binance
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
    
    # Crear cliente CCXT
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'spot',
            'adjustForTimeDifference': True,
            'recvWindow': 60000,  # 60 segundos para evitar errores de sincronización
            'createMarketBuyOrderRequiresPrice': False
        },
        'urls': urls
    })
    
    # Intentar sincronizar el tiempo con el servidor de Binance
    synchronize_time(exchange)
    
    # Configurar para testnet si es necesario
    if testnet:
        exchange.set_sandbox_mode(True)
        logging.info("🧪 Usando Binance Testnet API")
    else:
        logging.info("🔴 Usando Binance API Real")
    
    return exchange

def force_time_sync_if_needed(exchange, force=False):
    """
    Fuerza una sincronización de tiempo si ha pasado demasiado tiempo desde la última sincronización
    o si se requiere explícitamente
    
    Args:
        exchange: Instancia del cliente de exchange
        force: Si es True, forzar la sincronización independientemente del tiempo transcurrido
    
    Returns:
        bool: True si se forzó la sincronización, False si no fue necesario
    """
    # Usar nuestra implementación NTP para forzar sincronización si es necesario
    return ntp_sync.force_sync_if_needed(force)

def get_ohlcv(
    symbol: str, 
    timeframe: str = '5m', 
    limit: int = 100, 
    since: Optional[int] = None,
    testnet: Optional[bool] = None,
    recv_window: int = 120000  # Aumentado a 120 segundos
) -> pd.DataFrame:
    """
    Obtiene datos OHLCV de Binance y los convierte en un DataFrame
    
    Args:
        symbol: Par de trading (ej. 'BTC/USDT')
        timeframe: Intervalo de tiempo (ej. '1h', '4h', '1d')
        limit: Número máximo de velas a obtener
        since: Timestamp UNIX en milisegundos para inicio de datos
        testnet: Si usar testnet o API real (None = usar configuración global)
        recv_window: Ventana de recepción en ms para la API de Binance
    
    Returns:
        DataFrame con datos OHLCV
    """
    max_attempts = 3
    retry_delay = 2
    
    for attempt in range(1, max_attempts + 1):
        exchange = get_binance_client(testnet)
        
        try:
            # Forzar sincronización si es necesario
            force_time_sync_if_needed(exchange)
            
            # Obtener el offset actual usando la función pública
            offset_ms = ntp_sync.get_time_offset_ms()
            logging.info(f"Obteniendo OHLCV para {symbol}, timeframe={timeframe}, offset={offset_ms}")

            # Intentar obtener datos OHLCV
            # No se pasan 'params' personalizados (recvWindow, timestamp) porque el endpoint público
            # de OHLCV no los acepta y causaba un error -1104.
            ohlcv = exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                since=since
            )
            
            if not ohlcv:
                logging.error(f"❌ No se pudieron obtener datos OHLCV para {symbol}")
                return pd.DataFrame()
            
            # Convertir a DataFrame
            df = pd.DataFrame(
                ohlcv, 
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            
            # Convertir timestamp a datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Establecer timestamp como índice
            df.set_index('timestamp', inplace=True)
            
            logging.info(f"✅ Obtenidas {len(df)} velas {timeframe} para {symbol}")
            return df
            
        except Exception as e:
            if attempt < max_attempts:
                logging.warning(f"Intento {attempt}/{max_attempts} fallido al obtener datos OHLCV para {symbol}: {str(e)}. Reintentando en {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Aumentar el tiempo de espera exponencialmente
            else:
                logging.error(f"❌ Error al obtener datos OHLCV para {symbol} después de {max_attempts} intentos: {str(e)}")
                return pd.DataFrame()

def get_account_balance(testnet: Optional[bool] = None, recv_window: int = 120000) -> Dict:
    """
    Obtiene el balance de la cuenta
    
    Args:
        testnet: Si usar testnet o API real
        recv_window: Ventana de recepción en ms para la API de Binance
    
    Returns:
        Diccionario con el balance de la cuenta
    """
    max_attempts = 3
    retry_delay = 2
    
    for attempt in range(1, max_attempts + 1):
        exchange = get_binance_client(testnet)
        
        try:
            # Forzar sincronización si es necesario
            force_time_sync_if_needed(exchange)
            
            # Preparar parámetros con timestamp actualizado y recvWindow amplio
            params = {
                'recvWindow': recv_window,  # 60 segundos para evitar errores de timestamp
            }
            
            # Añadir timestamp ajustado justo antes de hacer la llamada
            current_timestamp = get_timestamp_with_offset()
            params['timestamp'] = current_timestamp
            
            logging.info(f"Obteniendo balance de cuenta, timestamp={current_timestamp}, offset={ntp_sync.get_time_offset_ms()}")
            
            balance = exchange.fetch_balance(params=params)
            logging.info(f"✅ Balance obtenido exitosamente")
            return balance
            
        except Exception as e:
            if attempt < max_attempts:
                logging.warning(f"Intento {attempt}/{max_attempts} fallido al obtener balance: {str(e)}. Reintentando en {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Aumentar el tiempo de espera exponencialmente
            else:
                logging.error(f"❌ Error al obtener balance después de {max_attempts} intentos: {str(e)}")
                return {}

def create_order(
    symbol: str,
    type: str,
    side: str,
    amount: float,
    price: Optional[float] = None,
    params: Dict = {},
    testnet: Optional[bool] = None,
    recv_window: int = 120000
) -> Dict:
    """
    Crea una orden en Binance
    
    Args:
        symbol: Par de trading (ej. 'BTC/USDT')
        type: Tipo de orden ('market', 'limit', etc.)
        side: Dirección ('buy' o 'sell')
        amount: Cantidad a comprar/vender
        price: Precio para órdenes limit (None para market)
        params: Parámetros adicionales
        testnet: Si usar testnet o API real
        recv_window: Ventana de recepción en ms para la API de Binance
    
    Returns:
        Información de la orden creada
    """
    max_attempts = 3
    retry_delay = 2
    
    for attempt in range(1, max_attempts + 1):
        exchange = get_binance_client(testnet)
        
        try:
            # Siempre forzar sincronización de tiempo antes de operaciones críticas
            force_time_sync_if_needed(exchange, force=True)
            
            # Asegurarnos de que recvWindow y timestamp estén incluidos en los parámetros
            order_params = params.copy()
            order_params['recvWindow'] = recv_window  # Ventana amplia para evitar errores de timestamp
            
            # Añadir timestamp ajustado justo antes de hacer la llamada
            current_timestamp = get_timestamp_with_offset()
            order_params['timestamp'] = current_timestamp
            
            logging.info(f"Creando orden {side} {amount} {symbol}, timestamp={current_timestamp}, offset={ntp_sync.get_time_offset_ms()}")
            
            order = exchange.create_order(
                symbol=symbol,
                type=type,
                side=side,
                amount=amount,
                price=price,
                params=order_params
            )
            logging.info(f"✅ Orden creada: {side} {amount} {symbol} a {price if price else 'precio de mercado'}")
            return order
            
        except Exception as e:
            if attempt < max_attempts:
                logging.warning(f"Intento {attempt}/{max_attempts} fallido al crear orden {side} {amount} {symbol}: {str(e)}. Reintentando en {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Aumentar el tiempo de espera exponencialmente
            else:
                logging.error(f"❌ Error al crear orden {side} {amount} {symbol} después de {max_attempts} intentos: {str(e)}")
                raise
