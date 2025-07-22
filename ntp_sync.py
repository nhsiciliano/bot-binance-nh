"""
Módulo de sincronización de tiempo NTP para trading bot
Maneja la sincronización con servidores NTP y ajustes de offset de tiempo
"""

import time
import logging
import threading
from datetime import datetime
import requests

class TimeSync:
    def __init__(self):
        self.time_offset_ms = 0
        self.last_sync_time = 0
        self.sync_lock = threading.Lock()
        self.sync_interval = 60  # Sincronizar cada 60 segundos
        
    def get_timestamp_with_offset(self):
        """Obtiene timestamp actual ajustado con offset"""
        current_time_ms = int(time.time() * 1000)
        return current_time_ms + self.time_offset_ms
    
    def get_time_offset_ms(self):
        """Obtiene el offset actual en milisegundos"""
        return self.time_offset_ms
    
    def update_time_offset(self, server_time_ms):
        """Actualiza el offset basado en tiempo del servidor"""
        with self.sync_lock:
            local_time_ms = int(time.time() * 1000)
            old_offset = self.time_offset_ms
            self.time_offset_ms = server_time_ms - local_time_ms
            delta = self.time_offset_ms - old_offset
            
            logging.info(f"⚙️ Offset de tiempo actualizado: {old_offset}ms → {self.time_offset_ms}ms (delta: {delta}ms)")
            self.last_sync_time = time.time()
    
    def full_sync(self):
        """Realiza sincronización completa con servidor NTP"""
        try:
            # Intentar sincronizar con API de Binance (más confiable para trading)
            response = requests.get('https://api.binance.com/api/v3/time', timeout=5)
            if response.status_code == 200:
                server_time = response.json()['serverTime']
                self.update_time_offset(server_time)
                logging.info(f"🔄 Sincronización exitosa con API de Binance")
                return True
        except Exception as e:
            logging.error(f"❌ Error en sincronización con Binance: {e}")
        
        # Fallback: usar tiempo local sin ajuste
        logging.warning("⚠️ Usando tiempo local sin ajuste NTP")
        return False
    
    def force_sync_if_needed(self, force=False):
        """Fuerza sincronización si es necesario"""
        current_time = time.time()
        time_since_last_sync = current_time - self.last_sync_time
        
        if force or time_since_last_sync > self.sync_interval:
            logging.info("🔄 Realizando sincronización de tiempo (API de Binance)...")
            return self.full_sync()
        
        return True

# Instancia global del sincronizador
_time_sync = TimeSync()

# Funciones públicas del módulo
def get_timestamp_with_offset():
    """Obtiene timestamp actual con offset aplicado"""
    return _time_sync.get_timestamp_with_offset()

def get_time_offset_ms():
    """Obtiene el offset actual en milisegundos"""
    return _time_sync.get_time_offset_ms()

def update_time_offset(server_time_ms):
    """Actualiza el offset de tiempo"""
    _time_sync.update_time_offset(server_time_ms)

def full_sync():
    """Realiza sincronización completa"""
    return _time_sync.full_sync()

def force_sync_if_needed(force=False):
    """Fuerza sincronización si es necesario"""
    return _time_sync.force_sync_if_needed(force)

def init_time_sync(testnet=True, sync_interval_seconds=60):
    """Inicializa el módulo de sincronización de tiempo"""
    _time_sync.sync_interval = sync_interval_seconds
    logging.info(f"⏱️ Sincronización de tiempo inicializada (intervalo: {sync_interval_seconds}s)")
    
    # Realizar sincronización inicial
    return _time_sync.full_sync()
