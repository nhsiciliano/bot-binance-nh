#!/usr/bin/env python
"""
Módulo para monitorear la salud del bot y enviar heartbeats a Supabase
"""
import os
import sys
import uuid
import psutil
import socket
import logging
import datetime
import threading
import time
from typing import Dict, Any, Optional, Tuple
from supabase import create_client, Client

# Importar configuración
from cloud_config import SUPABASE_URL, SUPABASE_KEY

class HealthMonitor:
    """Clase para monitorear la salud del bot y enviar heartbeats a Supabase"""
    
    def __init__(self, 
                heartbeat_interval: int = 60,
                version: str = "1.0.0",
                environment: str = "testnet"):
        """
        Inicializar el monitor de salud
        
        Args:
            heartbeat_interval: Intervalo en segundos para enviar heartbeats
            version: Versión del bot
            environment: Entorno (production, development, testnet)
        """
        # Generar ID de instancia único (o usar ID de Cloud Run si está disponible)
        self.instance_id = os.environ.get("K_REVISION", str(uuid.uuid4()))
        self.hostname = socket.gethostname()
        self.version = version
        self.environment = environment
        self.heartbeat_interval = heartbeat_interval
        self.status = "starting"
        self.error_message = None
        self.active_since = datetime.datetime.now()
        self._stop_event = threading.Event()
        self._heartbeat_thread = None
        
        # Inicializar conexión con Supabase
        try:
            if not SUPABASE_URL or not SUPABASE_KEY:
                logging.warning("⚠️ Falta configuración de Supabase, monitor de salud deshabilitado")
                self.enabled = False
                return
                
            self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
            self.enabled = True
            logging.info("✅ HealthMonitor inicializado correctamente")
            
            # Registrar estado inicial
            self._register_bot_status()
            
        except Exception as e:
            logging.error(f"❌ Error al inicializar HealthMonitor: {e}")
            self.enabled = False
    
    def start_monitoring(self):
        """Iniciar el monitoreo y envío de heartbeats en un hilo separado"""
        if not self.enabled:
            logging.warning("Monitor de salud deshabilitado, no se enviarán heartbeats")
            return
            
        self.status = "running"
        self._register_bot_status()
        
        # Iniciar hilo de heartbeat si no está ya corriendo
        if not self._heartbeat_thread or not self._heartbeat_thread.is_alive():
            self._stop_event.clear()
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                daemon=True
            )
            self._heartbeat_thread.start()
            logging.info(f"🔔 Monitoreo de salud iniciado (interval: {self.heartbeat_interval}s)")
    
    def stop_monitoring(self):
        """Detener el monitoreo de salud"""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._stop_event.set()
            self._heartbeat_thread.join(timeout=5)
            logging.info("🛑 Monitoreo de salud detenido")
        
        # Registrar estado detenido
        self.status = "stopped"
        self._register_bot_status()
    
    def report_error(self, error_message: str):
        """Reportar un error en el bot"""
        self.status = "error"
        self.error_message = error_message
        self._register_bot_status()
        logging.error(f"❌ Bot en estado de error: {error_message}")
    
    def _get_resource_usage(self) -> Dict[str, float]:
        """Obtener uso de recursos del proceso actual"""
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_usage = memory_info.rss / (1024 * 1024)  # Convertir a MB
            cpu_usage = process.cpu_percent(interval=0.1)
            return {"memory_usage": memory_usage, "cpu_usage": cpu_usage}
        except:
            return {"memory_usage": None, "cpu_usage": None}
    
    def _register_bot_status(self) -> bool:
        """Registrar estado del bot en Supabase"""
        if not self.enabled:
            return False
            
        try:
            # Obtener uso de recursos
            resource_usage = self._get_resource_usage()
            
            # Preparar datos para insertar/actualizar
            bot_data = {
                "instance_id": self.instance_id,
                "host": self.hostname,
                "status": self.status,
                "last_heartbeat": datetime.datetime.now().isoformat(),
                "memory_usage": resource_usage.get("memory_usage"),
                "cpu_usage": resource_usage.get("cpu_usage"),
                "active_since": self.active_since.isoformat(),
                "version": self.version,
                "environment": self.environment,
                "metadata": {
                    "python_version": sys.version,
                    "platform": sys.platform
                }
            }
            
            # Añadir mensaje de error si existe
            if self.error_message:
                bot_data["error_message"] = self.error_message
                
            # Insertar o actualizar en Supabase
            result = self.supabase.table("bot_status").upsert(
                bot_data,
                on_conflict=["instance_id"]
            ).execute()
            
            if hasattr(result, 'data') and result.data:
                logging.debug(f"✅ Estado del bot registrado: {self.status}")
                return True
            else:
                logging.warning(f"⚠️ Posible error al registrar estado del bot: {result}")
                return False
                
        except Exception as e:
            logging.error(f"❌ Error al registrar estado del bot en Supabase: {e}")
            return False
    
    def _heartbeat_loop(self):
        """Bucle para enviar heartbeats periódicamente"""
        while not self._stop_event.is_set():
            try:
                success = self._register_bot_status()
                if success:
                    logging.debug(f"💓 Heartbeat enviado: {self.status}")
            except Exception as e:
                logging.error(f"❌ Error en heartbeat: {e}")
                
            # Esperar hasta el próximo heartbeat o hasta que se detenga
            self._stop_event.wait(self.heartbeat_interval)

# Instancia singleton para uso en toda la aplicación
health_monitor = HealthMonitor()

if __name__ == "__main__":
    # Código de prueba
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Crear monitor y probar
    monitor = HealthMonitor(heartbeat_interval=5)  # Intervalo corto para pruebas
    monitor.start_monitoring()
    
    try:
        # Simular ejecución del bot
        logging.info("Bot simulado ejecutándose...")
        time.sleep(15)  # Permitir algunos heartbeats
        
        # Simular error
        logging.info("Simulando error...")
        monitor.report_error("Error de prueba")
        time.sleep(10)  # Permitir heartbeats en estado de error
        
    finally:
        # Detener monitoreo
        monitor.stop_monitoring()
        logging.info("Prueba completada")
