#!/usr/bin/env python3
"""
Script de monitoreo para el bot de trading de criptomonedas.
Este script verifica periódicamente:
- Que el bot esté en funcionamiento
- El estado de los indicadores y señales
- Registros de operaciones recientes
- Métricas de rendimiento
"""

import os
import time
import subprocess
import sqlite3
import datetime
import sys
import json
import logging
from typing import Dict, List, Optional
import pandas as pd

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('monitor.log')
    ]
)

class BotMonitor:
    """Clase para monitorear el estado del bot de trading"""
    
    def __init__(self, db_path: str = 'trading_bot.db', log_path: str = 'trading_bot.log'):
        self.db_path = db_path
        self.log_path = log_path
        self.bot_process_command = "python3 bot.py"
        self.last_check_time = datetime.datetime.now()
        logging.info("Iniciando monitor del bot de trading")
        
    def is_bot_running(self) -> bool:
        """Verifica si el proceso del bot está en ejecución"""
        try:
            result = subprocess.run(
                ["pgrep", "-f", "python3 bot.py"], 
                capture_output=True, 
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                pid = result.stdout.strip()
                logging.info(f"Bot en ejecución con PID: {pid}")
                return True
            else:
                logging.warning("¡El bot NO está en ejecución!")
                return False
        except Exception as e:
            logging.error(f"Error al verificar estado del bot: {e}")
            return False
    
    def get_last_log_entries(self, n_lines: int = 20) -> List[str]:
        """Obtiene las últimas n líneas del archivo de log"""
        try:
            result = subprocess.run(
                ["tail", "-n", str(n_lines), self.log_path], 
                capture_output=True, 
                text=True
            )
            if result.returncode == 0:
                return result.stdout.strip().split('\n')
            else:
                logging.error("No se pudo leer el archivo de logs")
                return []
        except Exception as e:
            logging.error(f"Error al leer logs: {e}")
            return []
    
    def get_recent_trades(self) -> pd.DataFrame:
        """Obtiene las operaciones recientes de la base de datos SQLite"""
        try:
            conn = sqlite3.connect(self.db_path)
            query = """
            SELECT * FROM trades 
            ORDER BY timestamp DESC 
            LIMIT 10
            """
            df = pd.read_sql_query(query, conn)
            conn.close()
            return df
        except Exception as e:
            logging.error(f"Error al obtener trades recientes: {e}")
            return pd.DataFrame()
    
    def get_active_positions(self) -> pd.DataFrame:
        """Obtiene las posiciones activas de la base de datos SQLite"""
        try:
            conn = sqlite3.connect(self.db_path)
            query = """
            SELECT * FROM positions 
            ORDER BY entry_time DESC
            """
            df = pd.read_sql_query(query, conn)
            conn.close()
            return df
        except Exception as e:
            logging.error(f"Error al obtener posiciones activas: {e}")
            return pd.DataFrame()
    
    def get_performance_metrics(self) -> Dict:
        """Obtiene métricas de rendimiento del bot"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Número total de operaciones
            cursor.execute("SELECT COUNT(*) FROM trades")
            total_trades = cursor.fetchone()[0]
            
            # Operaciones ganadoras y perdedoras
            cursor.execute("SELECT COUNT(*) FROM trades WHERE pnl > 0")
            winning_trades = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM trades WHERE pnl < 0")
            losing_trades = cursor.fetchone()[0]
            
            # Ganancia total
            cursor.execute("SELECT SUM(pnl) FROM trades")
            result = cursor.fetchone()[0]
            total_pnl = result if result is not None else 0
            
            # Calcular winrate
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            conn.close()
            
            return {
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": win_rate,
                "total_pnl": total_pnl
            }
        except Exception as e:
            logging.error(f"Error al obtener métricas de rendimiento: {e}")
            return {}
    
    def check_errors_in_logs(self) -> List[str]:
        """Busca errores en los logs recientes"""
        try:
            # Busca líneas con ERROR o WARNING en los últimos 100 registros
            result = subprocess.run(
                ["grep", "-E", "ERROR|WARNING", self.log_path, "|", "tail", "-100"], 
                capture_output=True, 
                text=True,
                shell=True
            )
            if result.returncode == 0 and result.stdout:
                errors = result.stdout.strip().split('\n')
                return errors
            return []
        except Exception as e:
            logging.error(f"Error al buscar errores en logs: {e}")
            return []
    
    def restart_bot_if_needed(self) -> bool:
        """Reinicia el bot si no está en ejecución"""
        if not self.is_bot_running():
            try:
                logging.warning("Intentando reiniciar el bot...")
                subprocess.Popen(
                    self.bot_process_command,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                time.sleep(5)  # Esperar a que inicie
                return self.is_bot_running()
            except Exception as e:
                logging.error(f"Error al reiniciar el bot: {e}")
                return False
        return True
    
    def generate_report(self):
        """Genera un reporte completo del estado del bot"""
        now = datetime.datetime.now()
        
        report = {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "bot_status": "running" if self.is_bot_running() else "stopped",
            "uptime": str(now - self.last_check_time) if self.is_bot_running() else "N/A",
            "recent_logs": self.get_last_log_entries(5),
            "active_positions_count": len(self.get_active_positions()),
            "performance": self.get_performance_metrics()
        }
        
        # Mostrar reporte en consola
        logging.info("=== REPORTE DE ESTADO DEL BOT ===")
        logging.info(f"Timestamp: {report['timestamp']}")
        logging.info(f"Estado: {report['bot_status']}")
        logging.info(f"Uptime: {report['uptime']}")
        logging.info(f"Posiciones activas: {report['active_positions_count']}")
        logging.info("Rendimiento:")
        for k, v in report['performance'].items():
            logging.info(f"  - {k}: {v}")
        logging.info("Logs recientes:")
        for log in report['recent_logs']:
            logging.info(f"  {log}")
        logging.info("================================")
        
        # Guardar reporte en archivo JSON
        try:
            with open('monitor_reports.json', 'a') as f:
                f.write(json.dumps(report) + '\n')
        except Exception as e:
            logging.error(f"Error al guardar reporte: {e}")
            
        return report
    
    def run(self, interval: int = 300):
        """Ejecuta el monitor en un bucle continuo
        
        Args:
            interval: Intervalo en segundos entre verificaciones (por defecto: 5 minutos)
        """
        logging.info(f"Monitor iniciado. Verificando cada {interval} segundos")
        
        try:
            while True:
                self.generate_report()
                self.restart_bot_if_needed()
                time.sleep(interval)
        except KeyboardInterrupt:
            logging.info("Monitor detenido manualmente")
        except Exception as e:
            logging.error(f"Error en el monitor: {e}")
            

if __name__ == "__main__":
    # Obtener intervalo de monitoreo desde argumentos de línea de comandos o usar valor por defecto
    interval = 300  # 5 minutos por defecto
    if len(sys.argv) > 1:
        try:
            interval = int(sys.argv[1])
        except ValueError:
            print(f"Intervalo inválido: {sys.argv[1]}. Usando valor por defecto (300 segundos)")
    
    monitor = BotMonitor()
    monitor.run(interval=interval)
