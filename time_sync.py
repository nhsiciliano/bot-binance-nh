#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Módulo para sincronización precisa de tiempo mediante NTP y Binance
Provee funciones para mantener el reloj del sistema sincronizado
"""

import logging
import time
import threading
import statistics
import ntplib
import requests
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Union

# Constantes
NTP_SERVERS = [
    'time.google.com',
    'pool.ntp.org',
    'time.cloudflare.com',
    'time.apple.com',
    'time.windows.com'
]

BINANCE_TIME_URL_TESTNET = "https://testnet.binance.vision/api/v3/time"
BINANCE_TIME_URL_REAL = "https://api.binance.com/api/v3/time"

# Variables globales para el control de sincronización
_time_offset_ms = 0  # Offset en milisegundos
_ntp_offset_ms = 0   # Offset específico de NTP en milisegundos
_time_offset_lock = threading.Lock()  # Lock para proteger acceso a variables de offset
_last_sync_time = 0  # Última vez que se sincronizó el tiempo (timestamp en ms)
_sync_interval_ms = 60 * 1000  # Intervalo de sincronización: 60 segundos en ms
_sync_thread = None  # Thread de sincronización continua
_stop_sync_thread = threading.Event()  # Evento para detener el thread
_is_testnet = False  # Modo testnet o real

def init_time_sync(testnet: bool = False, sync_interval_seconds: int = 60) -> None:
    """
    Inicializa el sistema de sincronización de tiempo
    
    Args:
        testnet: Si es True, usa la URL de testnet para Binance
        sync_interval_seconds: Intervalo de sincronización en segundos
    """
    global _is_testnet, _sync_interval_ms, _stop_sync_thread, _sync_thread
    
    _is_testnet = testnet
    _sync_interval_ms = sync_interval_seconds * 1000
    
    # Detener el thread anterior si existe
    if _sync_thread and _sync_thread.is_alive():
        _stop_sync_thread.set()
        _sync_thread.join(timeout=5)
    
    # Resetear el evento de parada
    _stop_sync_thread.clear()
    
    # Realizar una sincronización inicial
    full_sync()
    
    # Iniciar thread de sincronización periódica
    _sync_thread = threading.Thread(
        target=_sync_thread_worker, 
        name="NTPSyncThread",
        daemon=True
    )
    _sync_thread.start()
    logging.info(f"✅ Sincronización de tiempo inicializada (intervalo: {sync_interval_seconds}s)")

def _sync_thread_worker() -> None:
    """Thread worker para sincronización periódica"""
    while not _stop_sync_thread.is_set():
        try:
            # Dormir hasta el próximo intervalo o hasta que se solicite parada
            for _ in range(int(_sync_interval_ms / 1000)):
                if _stop_sync_thread.is_set():
                    return
                time.sleep(1)
            
            # Realizar sincronización
            full_sync()
            
        except Exception as e:
            logging.error(f"❌ Error en thread de sincronización de tiempo: {str(e)}")
            time.sleep(5)  # Esperar antes de reintentar en caso de error

def get_binance_time(max_attempts: int = 3) -> Optional[int]:
    """
    Obtiene el tiempo del servidor de Binance
    
    Args:
        max_attempts: Número máximo de intentos
    
    Returns:
        Timestamp en milisegundos o None si falla
    """
    url = BINANCE_TIME_URL_TESTNET if _is_testnet else BINANCE_TIME_URL_REAL
    
    for attempt in range(max_attempts):
        try:
            # Registrar tiempo antes de la llamada para calcular latencia
            before = time.time() * 1000
            
            with requests.Session() as session:
                response = session.get(url, timeout=5)
                
            # Registrar tiempo después de la llamada
            after = time.time() * 1000
            
            # Estimar latencia (one-way delay)
            latency_ms = int((after - before) / 2)
            
            if response.status_code == 200:
                server_time = response.json()['serverTime']
                
                # Compensar por la latencia
                adjusted_time = server_time + latency_ms
                
                logging.info(f"⏰ Tiempo Binance obtenido: {server_time} ms (latencia: {latency_ms}ms, ajustado: {adjusted_time}ms)")
                return adjusted_time
                
        except Exception as e:
            if attempt < max_attempts - 1:
                logging.warning(f"Intento {attempt+1}/{max_attempts} fallido al obtener tiempo Binance: {str(e)}")
                time.sleep(1)  # Pequeña espera antes de reintentar
            else:
                logging.error(f"❌ Error al obtener tiempo Binance después de {max_attempts} intentos: {str(e)}")
    
    return None

def update_time_offset(reference_time_ms: int) -> None:
    """
    Actualiza el offset de tiempo basado en una referencia externa
    
    Args:
        reference_time_ms: Timestamp de referencia en milisegundos
    """
    with _time_offset_lock:
        global _time_offset_ms
        local_time_ms = int(time.time() * 1000)
        new_offset = reference_time_ms - local_time_ms
        
        # Registrar el cambio para debug
        old_offset = _time_offset_ms
        _time_offset_ms = new_offset
        
        logging.info(f"⚙️ Offset de tiempo actualizado: {old_offset}ms → {new_offset}ms (delta: {new_offset - old_offset}ms)")

def full_sync() -> bool:
    """
    Realiza una sincronización de tiempo usando la API de Binance.
    La sincronización NTP ha sido deshabilitada para mejorar la estabilidad en Cloud Run.
    
    Returns:
        True si la sincronización fue exitosa
    """
    logging.info("🔄 Realizando sincronización de tiempo (API de Binance)...")
        
    # Sincronizar con Binance
    binance_time = get_binance_time()
    if binance_time:
        update_time_offset(binance_time)
        return True
    else:
        logging.error("❌ No se pudo obtener el tiempo de Binance. La sincronización falló.")
        return False

def get_timestamp_with_offset() -> int:
    """
    Obtiene el timestamp actual ajustado con el offset de Binance
    
    Returns:
        Timestamp en milisegundos ajustado
    """
    with _time_offset_lock:
        current_time_ms = int(time.time() * 1000)
        adjusted_time = current_time_ms + _time_offset_ms
        logging.debug(f"⏱️ Timestamp: local={current_time_ms}, offset={_time_offset_ms}, adjusted={adjusted_time}")
        return adjusted_time



def force_sync_if_needed(force: bool = False) -> bool:
    """
    Fuerza una sincronización si ha pasado demasiado tiempo desde la última
    o si se solicita explícitamente
    
    Args:
        force: Si es True, forzar la sincronización independientemente del tiempo
    
    Returns:
        True si se realizó la sincronización
    """
    current_time = int(time.time() * 1000)
    
    # Si nunca se ha sincronizado, ha pasado el intervalo configurado, o se fuerza
    if force or _last_sync_time == 0 or (current_time - _last_sync_time) > _sync_interval_ms:
        logging.info(f"🔄 Forzando sincronización de tiempo. Force={force}, Última sincronización hace {(current_time - _last_sync_time)/1000:.1f}s")
        return full_sync()
    
    return False

def get_time_offset_ms() -> int:
    """
    Devuelve el valor actual del offset de tiempo en milisegundos
    
    Returns:
        Offset de tiempo en milisegundos
    """
    with _time_offset_lock:
        return _time_offset_ms

def get_offset_info() -> Dict[str, int]:
    """
    Devuelve información sobre los offsets actuales
    
    Returns:
        Diccionario con información de offset
    """
    with _time_offset_lock:
        return {
            "binance_offset_ms": _time_offset_ms,
            "ntp_offset_ms": _ntp_offset_ms,
            "last_sync_time": _last_sync_time,
            "current_time_ms": int(time.time() * 1000),
            "adjusted_time_ms": get_timestamp_with_offset(),
            "ntp_adjusted_time_ms": get_timestamp_ntp_adjusted()
        }

def shutdown() -> None:
    """Detiene el thread de sincronización"""
    global _stop_sync_thread, _sync_thread
    
    if _sync_thread and _sync_thread.is_alive():
        logging.info("🛑 Deteniendo thread de sincronización de tiempo...")
        _stop_sync_thread.set()
        _sync_thread.join(timeout=5)
        logging.info("✅ Thread de sincronización de tiempo detenido")

# Inicializar automáticamente si se ejecuta como módulo independiente
if __name__ == "__main__":
    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Prueba de sincronización
    logging.info("🔍 Iniciando prueba de sincronización NTP...")
    
    # Inicializar sincronización
    init_time_sync(testnet=True, sync_interval_seconds=30)
    
    # Imprimir información de offset cada 10 segundos
    try:
        for i in range(6):  # 60 segundos de prueba
            time.sleep(10)
            offset_info = get_offset_info()
            logging.info(f"ℹ️ Offset Binance: {offset_info['binance_offset_ms']}ms, NTP: {offset_info['ntp_offset_ms']}ms")
            logging.info(f"🕒 Local: {offset_info['current_time_ms']}, Ajustado: {offset_info['adjusted_time_ms']}")
            
            # Forzar sincronización en la iteración 3
            if i == 3:
                logging.info("🔄 Forzando sincronización manual...")
                force_sync_if_needed(force=True)
    finally:
        # Detener limpiamente
        shutdown()
        logging.info("✅ Prueba completada")
