#!/usr/bin/env python
"""
Servidor HTTP independiente para Cloud Run
Este archivo inicia un servidor HTTP simple en el puerto especificado por la variable
de entorno PORT (predeterminado 8080), y luego ejecuta el bot de trading en un hilo separado.
Incluye monitoreo de salud e integración con el registro de indicadores.
Implementa un mecanismo de heartbeat para mantener el contenedor activo en Cloud Run.
"""

import os
import sys
import threading
import time
import http.server
import socketserver
import json
import logging
import socket
from datetime import datetime
import subprocess
import fcntl
import atexit
import signal
import requests
import traceback

# Importar módulos de monitoreo y registro
from health_monitor import health_monitor
from indicator_logger import indicator_logger

# Importar módulo de sincronización NTP
import time_sync

# Importar componentes del bot de futuros
from binance.client import Client
from cloud_config import get_secret
from futures_bot.futures_bot import FuturesBot
from futures_bot.futures_config import FuturesTradingConfig

# Archivo de bloqueo global para prevenir inicializaciones múltiples a nivel de sistema
LOCK_FILE = '/tmp/binance_bot_server.lock'

# Mantener referencia global al archivo de bloqueo
lock_file_handle = None

# Control de singleton para el servidor HTTP
_server_instance = None

# Control para heartbeat
_heartbeat_thread = None
_heartbeat_active = False
_server_start_time = None
_server_lock = threading.Lock()
_server_initialized = False  # Bandera explícita para evitar reinicializaciones

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("server.log"),
        logging.StreamHandler()
    ]
)

class CustomTCPServer(socketserver.TCPServer):
    """TCPServer personalizado que permite la reutilización de direcciones"""
    allow_reuse_address = True  # Evita errores 'Address already in use'
    
    def server_bind(self):
        """Sobrescribe server_bind para establecer SO_REUSEADDR en el socket"""
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return super().server_bind()

class HealthHandler(http.server.SimpleHTTPRequestHandler):
    """Manejador HTTP para responder a solicitudes de estado"""
    
    def do_GET(self):
        """Responder a solicitudes GET con un mensaje JSON"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        
        # Obtener estado del monitor de salud si está habilitado
        status = "running"
        if hasattr(health_monitor, 'status') and health_monitor.enabled:
            status = health_monitor.status
        
        self.wfile.write(json.dumps({
            'status': status,
            'timestamp': datetime.now().isoformat(),
            'host': socket.gethostname(),
            'version': getattr(health_monitor, 'version', '1.0.0'),
            'uptime_seconds': (datetime.now() - health_monitor.active_since).total_seconds() if hasattr(health_monitor, 'active_since') else 0
        }).encode('utf-8'))
    
    def log_message(self, format, *args):
        """Silenciar logs del servidor HTTP para no saturar la consola"""
        return

def start_heartbeat_thread():
    """Iniciar un hilo que envía peticiones periódicas al endpoint /health para mantener el contenedor activo"""
    global _heartbeat_thread, _heartbeat_active
    
    def keep_alive():
        """Función para mantener el contenedor de Cloud Run activo mediante solicitudes periódicas"""
        logging.info("💓 Iniciando mecanismo de heartbeat para mantener el contenedor activo")
        heartbeat_count = 0
        
        while _heartbeat_active:
            try:
                # Realizar una solicitud a nuestro propio servidor cada 5 minutos
                port = int(os.environ.get('PORT', 8080))
                response = requests.get(f"http://localhost:{port}/health", timeout=10)
                
                # Registrar solo cada 12 heartbeats (aproximadamente cada hora)
                heartbeat_count += 1
                if heartbeat_count % 12 == 0:
                    uptime_mins = int((datetime.now() - _server_start_time).total_seconds() / 60) if _server_start_time else 0
                    logging.info(f"💓 Heartbeat enviado ({heartbeat_count}). Contenedor activo por {uptime_mins} minutos")
                    
                # Verificar la respuesta
                if response.status_code != 200:
                    logging.warning(f"⚠️ Heartbeat recibió respuesta inesperada: {response.status_code}")
                    
            except Exception as e:
                logging.error(f"❌ Error en heartbeat: {e}")
                traceback.print_exc()
            
            # Esperar 5 minutos antes del próximo heartbeat
            for _ in range(30):  # Verificar cada 10 segundos si debemos detenernos
                if not _heartbeat_active:
                    break
                time.sleep(10)
    
    # Si ya existe un hilo de heartbeat activo, no crear otro
    if _heartbeat_thread is not None and _heartbeat_thread.is_alive():
        logging.info("ℹ️ Heartbeat ya está activo, omitiendo creación de nuevo hilo")
        return _heartbeat_thread
    
    # Iniciar nuevo hilo de heartbeat
    _heartbeat_active = True
    _heartbeat_thread = threading.Thread(target=keep_alive)
    _heartbeat_thread.daemon = True  # El hilo terminará cuando el programa principal termine
    _heartbeat_thread.start()
    logging.info("✅ Hilo de heartbeat iniciado correctamente")
    return _heartbeat_thread

def stop_heartbeat_thread():
    """Detener el hilo de heartbeat de forma segura"""
    global _heartbeat_active, _heartbeat_thread
    
    if _heartbeat_thread and _heartbeat_thread.is_alive():
        logging.info("⏹️ Deteniendo hilo de heartbeat...")
        _heartbeat_active = False
        _heartbeat_thread.join(timeout=30)  # Esperar hasta 30 segundos a que termine
        if _heartbeat_thread.is_alive():
            logging.warning("⚠️ El hilo de heartbeat no se detuvo correctamente")
        else:
            logging.info("✅ Hilo de heartbeat detenido correctamente")
        _heartbeat_thread = None

def start_bot_thread():
    """Iniciar el bot de trading en un hilo separado"""
    def run_bot():
        try:
            logging.info("🚀 Iniciando el bot de trading en un hilo separado")
            
            # Actualizar estado del monitor de salud
            if health_monitor.enabled:
                health_monitor.start_monitoring()
                logging.info("💓 Monitor de salud inicializado y reportando heartbeats")
            
            # Importar el bot aquí para evitar importaciones circulares
            import bot
            
            # Ejecutar la función principal del bot
            bot.main()
            
        except Exception as e:
            logging.error(f"❌ Error en el hilo del bot: {e}")
            
            # Reportar el error al monitor de salud
            if health_monitor.enabled:
                health_monitor.report_error(str(e))
            
            # Imprimir el traceback completo para depuración
            import traceback
            traceback.print_exc()

    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True  # El hilo terminará cuando el programa principal termine
    bot_thread.start()
    return bot_thread

def start_futures_bot_thread():
    """Iniciar el bot de futuros en un hilo separado."""
    def run_futures_bot():
        try:
            logging.info("🚀 Iniciando el bot de FUTUROS en un hilo separado")
            
            # Cargar configuración y credenciales
            use_testnet = get_secret("USE_FUTURES_TESTNET", "True").lower() in ('true', '1', 't')
            api_key_name = "FUTURES_TESTNET_API_KEY" if use_testnet else "FUTURES_API_KEY"
            api_secret_name = "FUTURES_TESTNET_API_SECRET" if use_testnet else "FUTURES_API_SECRET"

            api_key = get_secret(api_key_name)
            api_secret = get_secret(api_secret_name)

            if not api_key or not api_secret:
                logging.error("No se encontraron las API keys para el bot de futuros. Abortando hilo.")
                return

            client = Client(api_key, api_secret, testnet=use_testnet)
            config = FuturesTradingConfig()
            bot = FuturesBot(client, config)

            logging.info(f"Bot de futuros configurado para operar en {'TESTNET' if use_testnet else 'PRODUCCIÓN'}.")

            while True:
                bot.analyze_market()
                # Esperar 60 segundos antes del próximo ciclo
                time.sleep(60)

        except Exception as e:
            logging.error(f"❌ Error crítico en el hilo del bot de futuros: {e}")
            import traceback
            traceback.print_exc()

    futures_bot_thread = threading.Thread(target=run_futures_bot)
    futures_bot_thread.daemon = True
    futures_bot_thread.start()
    return futures_bot_thread

def create_http_server():
    """Crea una instancia del servidor HTTP si no existe"""
    global _server_instance, _server_lock, _server_initialized
    
    # Si el servidor ya ha sido inicializado, nunca intentar reiniciarlo
    if _server_initialized:
        logging.info("✅ Servidor HTTP ya inicializado anteriormente, omitiendo cualquier intento de reinicio")
        return _server_instance
    
    # Usar lock para garantizar exclusión mutua durante la creación del servidor
    with _server_lock:
        # Si ya existe una instancia del servidor, devolverla
        if _server_instance is not None:
            logging.info("ℹ️ Servidor HTTP ya está en ejecución, reutilizando instancia existente")
            _server_initialized = True  # Marcar como inicializado
            return _server_instance
            
        # Obtener puerto del entorno (Cloud Run) o usar 8080 por defecto
        port = int(os.environ.get('PORT', 8080))
        # Usar 0.0.0.0 para asegurar que escucha en todas las interfaces de red
        server_address = ('0.0.0.0', port)
        
        try:
            # Crear socket directamente con SO_REUSEADDR activado
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Verificar si el puerto ya está en uso
            result = sock.connect_ex(server_address)
            sock.close()
            
            # Si el puerto está en uso pero es nuestra primera inicialización, forzar cierre
            if result == 0:
                logging.warning(f"⚠️ El puerto {port} ya está en uso. Verificando si podemos forzar la reutilización...")
                # Intentar de todas formas, confiando en SO_REUSEADDR
            
            # Crear y configurar servidor con opciones robustas
            httpd = CustomTCPServer(server_address, HealthHandler)
            _server_instance = httpd
            _server_initialized = True  # Marcar como inicializado
            logging.info(f"✅ Servidor HTTP inicializado correctamente en {server_address[0]}:{server_address[1]}")
            return httpd
            
        except OSError as e:
            logging.error(f"❌ Error al inicializar servidor HTTP: {e}")
            return None

def acquire_global_lock():
    """Adquiere un bloqueo exclusivo a nivel de sistema de archivos"""
    global lock_file_handle
    try:
        # Abrir o crear el archivo de bloqueo
        lock_file_handle = open(LOCK_FILE, 'w')
        
        # Intento de bloqueo exclusivo y no bloqueante
        fcntl.flock(lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        
        # Escribir PID en el archivo como referencia
        pid = os.getpid()
        lock_file_handle.seek(0)
        lock_file_handle.write(str(pid))
        lock_file_handle.flush()
        
        logging.info(f"✅ Bloqueo global adquirido para PID {pid}")
        return True
    except IOError:
        # Si ya está bloqueado, leemos el PID del proceso que lo tiene
        try:
            with open(LOCK_FILE, 'r') as f:
                pid = f.read().strip()
                logging.warning(f"⚠️ El servidor ya está en ejecución (PID {pid}). Abortando esta instancia.")
        except:
            logging.warning("⚠️ El servidor ya está en ejecución (PID desconocido). Abortando esta instancia.")
        
        return False

def release_global_lock():
    """Libera el bloqueo global al salir"""
    global lock_file_handle
    if lock_file_handle:
        try:
            # Verificar si el archivo está cerrado antes de operar sobre él
            if not lock_file_handle.closed:
                fcntl.flock(lock_file_handle, fcntl.LOCK_UN)
                lock_file_handle.close()
                
            # Verificar si el archivo de bloqueo existe antes de intentar eliminarlo
            if os.path.exists(LOCK_FILE):
                os.unlink(LOCK_FILE)  # Eliminar el archivo de bloqueo
                
            logging.info("✅ Bloqueo global liberado correctamente")
            # Resetear la variable para evitar dobles liberaciones
            lock_file_handle = None
        except Exception as e:
            logging.error(f"❌ Error al liberar bloqueo global: {e}")
            # Intentar limpiar en caso de error
            lock_file_handle = None

def signal_handler(sig, frame):
    """Manejador de señales para capturar interrupciones"""
    logging.info("👋 Señal de terminación recibida. Limpiando recursos...")
    stop_heartbeat_thread()
    release_global_lock()
    sys.exit(0)

def main():
    """Función principal del servidor"""
    global _server_start_time
    
    # Registrar limpieza de recursos al salir
    atexit.register(release_global_lock)
    atexit.register(stop_heartbeat_thread)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Registrar tiempo de inicio
    _server_start_time = datetime.now()
    
    # Intentar adquirir bloqueo global exclusivo a nivel de sistema
    if not acquire_global_lock():
        logging.error("❌ No se pudo adquirir el bloqueo global. Otra instancia del servidor ya está en ejecución.")
        sys.exit(1)
    
    # Crear mutex local adicional para garantizar que main() solo se ejecuta una vez
    main_lock = threading.Lock()
    if not main_lock.acquire(blocking=False):
        logging.warning("⚠️ Se detectó un intento de iniciar el servidor más de una vez. Ignorando...")
        release_global_lock()
        return
    
    try:
        # Configurar monitor de salud con información del entorno
        version = os.environ.get("APP_VERSION", "1.0.0")
        environment = "testnet" if os.environ.get("USE_TESTNET", "True").lower() in ("true", "t", "1") else "production"
        health_monitor.version = version
        health_monitor.environment = environment
        
        # Inicializar módulos de monitoreo y registro
        logging.info("🔄 Inicializando módulos de monitoreo y registro")
        if not health_monitor.enabled:
            logging.warning("⚠️ Monitor de salud deshabilitado - no se enviarán heartbeats")
        if not indicator_logger.enabled:
            logging.warning("⚠️ Registro de indicadores deshabilitado - no se registrarán indicadores")
            
        # Inicializar sincronización de tiempo
        try:
            # Determinar si estamos en testnet basado en variables de entorno
            is_testnet = os.environ.get("USE_TESTNET", "True").lower() in ("true", "t", "1")
            # Intervalo de sincronización: cada 60 segundos
            time_sync.init_time_sync(testnet=is_testnet, sync_interval_seconds=60)
            logging.info("⏱️ Sincronización de tiempo inicializada (intervalo: 60s)")
        except Exception as e:
            logging.error(f"❌ Error al inicializar sincronización de tiempo: {e}")
        
        # Obtener puerto del entorno (Cloud Run) o usar 8080 por defecto
        port = int(os.environ.get('PORT', 8080))
        logging.info(f"🌐 Iniciando servidor HTTP en puerto {port}")
        
        # Crear y configurar el servidor HTTP como singleton
        httpd = create_http_server()
        if not httpd:
            logging.error("❌ Error crítico: No se pudo iniciar el servidor HTTP. Abortando.")
            sys.exit(1)  # Salir con código de error
        
        # Iniciar el bot en un hilo separado después de que el servidor esté listo
        logging.info("⏳ Esperando 2 segundos antes de iniciar el bot...")
        time.sleep(2)  # Dar tiempo al servidor para estabilizarse
        
        # Iniciar SOLO el bot de futuros y el heartbeat en hilos separados
        logging.info("🚀 MODO FUTUROS ÚNICAMENTE - Bot de spot deshabilitado")
        # bot_thread = start_bot_thread()  # DESHABILITADO - Solo futuros
        futures_bot_thread = start_futures_bot_thread()
        heartbeat_thread = start_heartbeat_thread()
        
        # Iniciar servidor (bloqueante)
        logging.info(f"✅ Servidor HTTP iniciado y respondiendo en 0.0.0.0:{port}")
        try:
            # Usar un enfoque más robusto para la ejecución del servidor
            httpd.serve_forever(poll_interval=1.0)  # Revisar cada segundo
        except KeyboardInterrupt:
            logging.info("👋 Deteniendo servidor HTTP y limpiando recursos...")
        except Exception as e:
            logging.error(f"❌ Error en la ejecución del servidor HTTP: {e}")
            
        # Detener el monitor de salud y el heartbeat antes de salir
        if health_monitor.enabled:
            health_monitor.stop_monitoring()
            
        # Detener el mecanismo de heartbeat
        stop_heartbeat_thread()
            
        # Cerrar el servidor si todavía existe
        if httpd:
            httpd.server_close()
            
        # Detener la sincronización de tiempo
        try:
            time_sync.shutdown()
            logging.info("✅ Sincronización de tiempo detenida")
        except Exception as e:
            logging.error(f"❌ Error al detener sincronización de tiempo: {e}")
            
    except Exception as e:
        # Capturar cualquier excepción no manejada en el bloque principal
        logging.error(f"❌ Error crítico en el servidor: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Liberar el lock principal en cualquier caso
        main_lock.release()

if __name__ == "__main__":
    main()
