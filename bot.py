
"""
Bot de Trading Automatizado RSI-MACD para Criptomonedas
Optimizado para BTC/USDT con gestión avanzada de riesgo
Integrado con Supabase para análisis y seguimiento avanzado
"""

import os
import pandas as pd
import logging
import time
import math
import schedule
from datetime import datetime, timedelta
import sqlite3
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from telegram_utils import send_message, send_error_message
from binance_utils import get_ohlcv
from supabase_utils import get_connection, create_position, update_position_pl
from indicators import calculate_rsi, calculate_macd
import ccxt
import json
import subprocess
import sys
import threading
import http.server
import socketserver
# Import for cloud configuration
# Se eliminó la importación load_config que no existe
import warnings

# Importar registradores de indicadores y salud del bot
from indicator_logger import indicator_logger
from health_monitor import health_monitor

# Importar gestor de Supabase y configuración
from supabase_manager import SupabaseManager

# Cargar configuración unificada (soporta entorno local y GCP)
from cloud_config import (
    SUPABASE_URL, SUPABASE_KEY, 
    TESTNET_API_KEY, TESTNET_API_SECRET,
    REAL_API_KEY, REAL_API_SECRET,
    USE_TESTNET, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
    LOG_FILE
)

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

warnings.filterwarnings('ignore')

@dataclass
class TradingConfig:
    """Configuración del bot de trading"""
    # Exchange settings
    exchange_id: str = 'binance'
    symbols: List[str] = None
    timeframe: str = '5m'  # Timeframe base para la estrategia (scalping)

    # --- Parámetros de Estrategia Principal (Tendencia + Oscilador) ---

    # Filtro de Tendencia (para determinar la dirección general del mercado)
    ema_long_period: int = 200  # EMA de 200 para filtrar tendencia principal

    # Indicador de Momento/Entrada (RSI)
    rsi_period: int = 14
    rsi_oversold: int = 30  # Nivel estándar de sobreventa
    rsi_overbought: int = 70 # Nivel estándar de sobrecompra

    # Indicador de Momento/Confirmación (MACD)
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # --- Parámetros de Gestión de Riesgo ---
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 4.0
    trailing_stop_pct: float = 1.5
    max_position_size: float = 15.0
    max_positions: int = 5
    max_positions_per_symbol: int = 2  # Máximo 2 posiciones por símbolo

    # --- Configuración Adicional ---
    trading_start_hour: int = 0
    trading_end_hour: int = 23
    db_name: str = 'trading_bot.db'
    email_notifications: bool = True
    telegram_notifications: bool = False

    def __post_init__(self):
        if self.symbols is None:
            self.symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT']

class DatabaseManager:
    """Maneja la base de datos del bot (SQLite y Supabase)"""
    
    def __init__(self, db_name: str, use_supabase: bool = True):
        self.db_name = db_name
        self.use_supabase = use_supabase
        self.supabase = None
        
        # Inicializamos la base de datos local SQLite
        self.init_database()
        
        # Inicializamos Supabase si está habilitado
        if self.use_supabase:
            try:
                self.supabase = SupabaseManager(SUPABASE_URL, SUPABASE_KEY)
                logging.info("✅ Supabase conectado exitosamente")
            except Exception as e:
                logging.error(f"❌ Error al conectar con Supabase: {e}")
                self.use_supabase = False
                logging.warning("⚠️ Supabase desactivado, usando solo SQLite")
    
    def init_database(self):
        """Inicializa las tablas de la base de datos SQLite"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # Tabla de trades
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                symbol TEXT,
                side TEXT,
                amount REAL,
                price REAL,
                total REAL,
                pnl REAL,
                status TEXT,
                strategy_signal TEXT,
                rsi_value REAL,
                macd_value REAL,
                notes TEXT
            )
        ''')
        
        # Tabla de posiciones activas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                side TEXT,
                amount REAL,
                entry_price REAL,
                current_price REAL,
                unrealized_pnl REAL,
                stop_loss REAL,
                take_profit_1 REAL,
                take_profit_2 REAL,
                tp1_filled BOOLEAN,
                tp2_filled BOOLEAN,
                entry_time TEXT,
                last_update TEXT
            )
        ''')
        
        # Tabla de performance
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                total_balance REAL,
                btc_balance REAL,
                usdt_balance REAL,
                daily_pnl REAL,
                total_trades INTEGER,
                winning_trades INTEGER,
                losing_trades INTEGER
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def log_trade(self, trade_data: Dict) -> int:
        """Registra un trade en la base de datos local y en Supabase
        
        Args:
            trade_data: Datos del trade a registrar
            
        Returns:
            ID del trade en la base de datos local
        """
        # Registro en SQLite
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO trades (timestamp, symbol, side, amount, price, total, pnl, status, 
                           strategy_signal, rsi_value, macd_value, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trade_data.get('timestamp'),
            trade_data.get('symbol'),
            trade_data.get('side'),
            trade_data.get('amount'),
            trade_data.get('price'),
            trade_data.get('total'),
            trade_data.get('pnl', 0),
            trade_data.get('status'),
            trade_data.get('strategy_signal'),
            trade_data.get('rsi_value'),
            trade_data.get('macd_value'),
            trade_data.get('notes', '')
        ))
        
        trade_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Registro en Supabase si está habilitado
        if self.use_supabase and self.supabase:
            try:
                # Preparamos los datos para Supabase
                supabase_trade = trade_data.copy()
                
                # Aseguramos que timestamp sea string ISO para Supabase
                if isinstance(supabase_trade.get('timestamp'), datetime):
                    supabase_trade['timestamp'] = supabase_trade['timestamp'].isoformat()
                    
                # Agregamos campo de sincronización y ID local
                supabase_trade['local_id'] = trade_id
                supabase_trade['synced_at'] = datetime.now().isoformat()
                
                # Registramos en Supabase
                supabase_id = self.supabase.log_trade(supabase_trade)
                logging.info(f"✅ Trade #{trade_id} sincronizado con Supabase (ID: {supabase_id})")
            except Exception as e:
                logging.error(f"❌ Error al sincronizar trade con Supabase: {e}")
        
        return trade_id
    
    def get_active_positions(self) -> List[Dict]:
        """Obtiene las posiciones activas desde SQLite y/o Supabase
        
        Returns:
            Lista de posiciones activas
        """
        # Primero obtenemos posiciones desde SQLite (siempre)
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row  # Para acceder a los resultados por nombre de columna
        cursor = conn.cursor()
        
        # En la tabla positions no hay una columna 'status', simplemente obtenemos todas las posiciones
        cursor.execute('''
            SELECT * FROM positions
        ''')
        
        positions = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        # Si Supabase está habilitado, intentamos sincronizar
        if self.use_supabase and self.supabase:
            try:
                # Obtenemos posiciones desde Supabase
                supabase_positions = self.supabase.get_active_positions()
                
                if supabase_positions:
                    # Verificamos si hay posiciones en Supabase que no están en SQLite
                    # y las agregamos a la lista
                    local_ids = [p.get('id') for p in positions]
                    
                    for sp in supabase_positions:
                        if sp.get('local_id') not in local_ids:
                            # Convertimos a formato compatible con SQLite
                            logging.info(f"Posición encontrada en Supabase pero no en SQLite: {sp.get('id')}")
                            positions.append(sp)
            except Exception as e:
                logging.error(f"❌ Error al consultar posiciones de Supabase: {e}")
                logging.warning("⚠️ Usando solo posiciones locales de SQLite")
        
        return positions

class NotificationManager:
    """Maneja las notificaciones del bot"""
    
    def __init__(self, email_config: Dict = None, telegram_config: Dict = None):
        self.email_config = email_config or {}
        self.telegram_config = telegram_config or {}
    
    def send_email(self, subject: str, message: str):
        """Envía notificación por email"""
        if not self.email_config:
            return
        
        try:
            msg = MIMEText(message)
            msg['Subject'] = subject
            msg['From'] = self.email_config['from']
            msg['To'] = self.email_config['to']
            
            server = smtplib.SMTP(self.email_config['smtp_server'], self.email_config['port'])
            server.starttls()
            server.login(self.email_config['username'], self.email_config['password'])
            server.send_message(msg)
            server.quit()
            
            logging.info(f"Email sent: {subject}")
        except Exception as e:
            logging.error(f"Error sending email: {e}")
    
    def send_telegram(self, message: str):
        """Envía notificación por Telegram"""
        # Implementar según API de Telegram
        pass

class TechnicalAnalysis:
    """Clase para análisis técnico"""
    
    # Funciones estáticas eliminadas para evitar referencias circulares
    # Se usan las funciones de instancia más abajo
    
    @staticmethod
    def is_trading_hours(start_hour: int, end_hour: int) -> bool:
        """Verifica si está en horario de trading
        
        Configurado para operar 24/7 sin restricciones horarias
        Los parámetros start_hour y end_hour se mantienen por compatibilidad
        pero son ignorados ya que el bot está configurado para operar 24 horas
        """
        # Siempre devuelve True para operar 24/7
        return True

class TechnicalAnalyzer:
    """Analizador de datos técnicos para el bot de trading"""
    
    def __init__(self):
        self.indicators = {}
    
    def calculate_rsi(self, prices, period: int = 14):
        """Calcular el RSI (Relative Strength Index)"""
        if len(prices) < period + 1:
            logging.warning(f"No hay suficientes datos para calcular RSI: {len(prices)} periodos disponibles, se requieren {period + 1}")
            return None
            
        # Usar implementación nativa de indicators.py
        try:
            # Convertir a DataFrame para usar con la función calculate_rsi
            df = pd.DataFrame({"close": prices})
            from indicators import calculate_rsi as calc_rsi
            rsi_values = calc_rsi(df, period=period, column="close")
            
            # Verificar si el último valor es válido
            if len(rsi_values) > 0 and not np.isnan(rsi_values[-1]):
                return float(rsi_values[-1])  # Convertir a float para evitar problemas de tipo
            else:
                logging.warning(f"RSI calculado es NaN. Verificar datos de entrada.")
                return None
        except Exception as e:
            logging.warning(f"Error al calcular RSI: {e}")
            return None
    
    def calculate_macd(self, prices, fast: int = 8, slow: int = 17, signal: int = 9):
        """Calcular el MACD (Moving Average Convergence Divergence) adaptado para menos datos"""
        # Reducir el requisito mínimo de datos para permitir el cálculo con los datos disponibles
        required_periods = slow + signal
        if len(prices) < required_periods:
            logging.warning(f"No hay suficientes datos para calcular MACD: {len(prices)} periodos disponibles, se requieren {required_periods}")
            # Si tenemos al menos 22 periodos (suficiente para un análisis básico), intentamos calcular de todos modos
            if len(prices) >= 22:
                logging.info(f"Intentando calcular MACD con parámetros adaptados a {len(prices)} periodos disponibles")
                # Adaptamos temporalmente los parámetros para los datos que tenemos
                if slow > len(prices) - 10:
                    slow = len(prices) - 10
                    fast = max(5, slow // 2)
                    signal = min(5, len(prices) - slow - 2)
            else:
                return None, None, None
            
        # Usar implementación nativa de indicators.py
        try:
            # Convertir a DataFrame para usar con la función calculate_macd
            prices_array = np.array(prices, dtype=float)
            if np.isnan(prices_array).any():
                logging.warning(f"Datos de precios contienen valores NaN")
                # Limpiar valores NaN
                prices_array = prices_array[~np.isnan(prices_array)]
                
            df = pd.DataFrame({"close": prices_array})
            from indicators import calculate_macd as calc_macd
            macd_line, signal_line, histogram = calc_macd(
                df, 
                fast_period=fast, 
                slow_period=slow, 
                signal_period=signal, 
                column="close"
            )
            
            # Verificar resultados
            if len(macd_line) > 0 and len(signal_line) > 0 and len(histogram) > 0:
                if not np.isnan(macd_line[-1]) and not np.isnan(signal_line[-1]) and not np.isnan(histogram[-1]):
                    return float(macd_line[-1]), float(signal_line[-1]), float(histogram[-1])
            
            logging.warning(f"MACD calculado contiene valores NaN o vacíos. Verificar datos de entrada.")
            return None, None, None
                
        except Exception as e:
            logging.warning(f"Error al calcular MACD: {e}")
            return None, None, None
    
    def analyze_market(self, symbol: str, timeframe: str, exchange, config=None):
        """Analiza el mercado con una estrategia de seguimiento de tendencia usando EMA, RSI y MACD."""
        try:
            logging.info(f"Iniciando análisis para {symbol} en timeframe {timeframe}")

            # Cargar parámetros desde la configuración o usar defaults robustos
            ema_long_period = getattr(config, 'ema_long_period', 200)
            rsi_period = getattr(config, 'rsi_period', 14)
            rsi_oversold = getattr(config, 'rsi_oversold', 30)
            rsi_overbought = getattr(config, 'rsi_overbought', 70)
            fast_period = getattr(config, 'macd_fast', 12)
            slow_period = getattr(config, 'macd_slow', 26)
            signal_period = getattr(config, 'macd_signal', 9)

            # 1. Obtención de datos
            # Aumentamos el límite para asegurar que la EMA de 200 períodos sea precisa
            required_candles = ema_long_period + 50 
            from binance_utils import get_ohlcv
            df_ohlcv = get_ohlcv(symbol=symbol, timeframe=timeframe, limit=required_candles)

            if df_ohlcv is None or df_ohlcv.empty or len(df_ohlcv) < ema_long_period:
                logging.warning(f"Datos insuficientes para {symbol}: se requieren ~{ema_long_period} velas, se obtuvieron {len(df_ohlcv) if df_ohlcv is not None else 0}")
                return {'buy_signal': False, 'sell_signal': False, 'error': 'Datos insuficientes'}

            # 2. Cálculo de Indicadores
            df = df_ohlcv.copy()
            # df_ohlcv ya tiene timestamp como índice y 5 columnas: open, high, low, close, volume
            # No necesitamos reasignar columnas ni convertir timestamp ya que viene procesado de binance_utils
            logging.debug(f"DataFrame shape: {df.shape}, columns: {df.columns.tolist()}")

            # Filtro de Tendencia Principal (EMA 200)
            df['ema_long'] = df['close'].ewm(span=ema_long_period, adjust=False).mean()

            # Indicador de Momento/Entrada (RSI)
            df['rsi'] = self.calculate_rsi(df['close'].values, period=rsi_period)

            # Indicador de Confirmación (MACD)
            df['macd'], df['macdsignal'], df['macdhist'] = self.calculate_macd(
                df['close'].values, fast=fast_period, slow=slow_period, signal=signal_period
            )

            # Bollinger Bands (para análisis de soporte/resistencia)
            bb_period = 20
            bb_std = 2
            df['bb_middle'] = df['close'].rolling(window=bb_period).mean()
            bb_std_dev = df['close'].rolling(window=bb_period).std()
            df['bb_upper'] = df['bb_middle'] + (bb_std_dev * bb_std)
            df['bb_lower'] = df['bb_middle'] - (bb_std_dev * bb_std)
            df['bb_width'] = df['bb_upper'] - df['bb_lower']  # Ancho de las bandas

            # 3. Extracción de Valores Actuales (última vela cerrada)
            current_close = df['close'].iloc[-1]
            current_ema_long = df['ema_long'].iloc[-1]
            current_rsi = df['rsi'].iloc[-1]
            current_macd = df['macd'].iloc[-1]
            current_signal = df['macdsignal'].iloc[-1]
            current_hist = df['macdhist'].iloc[-1]
            previous_hist = df['macdhist'].iloc[-2]
            current_bb_upper = df['bb_upper'].iloc[-1]
            current_bb_lower = df['bb_lower'].iloc[-1]
            current_bb_middle = df['bb_middle'].iloc[-1]
            current_bb_width = df['bb_width'].iloc[-1]

            # 4. Lógica de Señal de Compra
            
            # Señales de trading
            buy_signal = False
            sell_signal = False
            signal_strength = 0  # 0=neutral, +1 a +3 compra, -1 a -3 venta
            signals = []
            
            # Evaluación RSI adaptado para scalping
            if current_rsi < rsi_oversold:
                rsi_signal = "sobrevendido"
                df['rsi_signal'] = 'buy'
                signal_strength += 1
                signals.append(f"RSI sobrevendido ({current_rsi:.2f} < {rsi_oversold})")
            elif current_rsi > rsi_overbought:
                rsi_signal = "sobrecomprado"
                df['rsi_signal'] = 'sell'
                signal_strength -= 1
                signals.append(f"RSI sobrecomprado ({current_rsi:.2f} > {rsi_overbought})")
            else:
                rsi_signal = "neutral"
                df['rsi_signal'] = 'neutral'
            
            # Evaluación MACD (más sensible para scalping)
            if current_hist > 0 and df['macdhist'].iloc[-2] <= 0:  # Cruce alcista
                macd_signal = "alcista"
                df['macd_signal'] = 'buy'
                signal_strength += 1
                signals.append(f"MACD cruce alcista ({current_hist:.6f})")
            elif current_hist > 0 and current_hist > df['macdhist'].iloc[-2]:  # Incremento del histograma positivo
                macd_signal = "fortaleciendo alcista"
                df['macd_signal'] = 'buy'
                signal_strength += 0.5
                signals.append(f"MACD fortaleciendose ({current_hist:.6f} > {df['macdhist'].iloc[-2]:.6f})")
            elif current_hist < 0 and df['macdhist'].iloc[-2] >= 0:  # Cruce bajista
                macd_signal = "bajista"
                df['macd_signal'] = 'sell'
                signal_strength -= 1
                signals.append(f"MACD cruce bajista ({current_hist:.6f})")
            elif current_hist < 0 and current_hist < df['macdhist'].iloc[-2]:  # Disminución del histograma negativo
                macd_signal = "fortaleciendo bajista"
                df['macd_signal'] = 'sell'
                signal_strength -= 0.5
                signals.append(f"MACD debilitandose ({current_hist:.6f} < {df['macdhist'].iloc[-2]:.6f})")
            else:
                macd_signal = "neutral"
                df['macd_signal'] = 'neutral'
            
            # Evaluación de Bollinger Bands
            if not np.isnan(current_bb_lower) and not np.isnan(current_bb_upper):
                price_position = (current_close - current_bb_lower) / (current_bb_upper - current_bb_lower) if (current_bb_upper - current_bb_lower) > 0 else 0.5
                
                # Precio cerca o por debajo de la banda inferior (posible compra)
                if current_close <= current_bb_lower * 1.005:  # Dentro del 0.5% de la banda inferior
                    bb_signal = "soporte BB inferior"
                    signal_strength += 1
                    signals.append("Precio en/debajo banda inferior BB")
                    df['bb_signal'] = 'buy'
                # Precio cerca o por encima de la banda superior (posible venta)
                elif current_close >= current_bb_upper * 0.995:  # Dentro del 0.5% de la banda superior
                    bb_signal = "resistencia BB superior"
                    signal_strength -= 1
                    signals.append("Precio en/encima banda superior BB")
                    df['bb_signal'] = 'sell'
                # Contracción de bandas (posible ruptura inminente)
                elif current_bb_width < df['bb_width'].rolling(window=5).mean().iloc[-1] * 0.8:
                    bb_signal = "compresión de bandas"
                    df['bb_signal'] = 'neutral_compression'
                    signals.append("Compresión de bandas BB (volatilidad inminente)")
                # Precio cruzando la media hacia arriba
                elif current_close > current_bb_middle and df['close'].iloc[-2] <= df['bb_middle'].iloc[-2]:
                    bb_signal = "cruce media alcista"
                    signal_strength += 0.5
                    signals.append("Cruce alcista de media BB")
                    df['bb_signal'] = 'buy'
                # Precio cruzando la media hacia abajo
                elif current_close < current_bb_middle and df['close'].iloc[-2] >= df['bb_middle'].iloc[-2]:
                    bb_signal = "cruce media bajista"
                    signal_strength -= 0.5
                    signals.append("Cruce bajista de media BB")
                    df['bb_signal'] = 'sell'
                else:
                    bb_signal = "neutral"
                    df['bb_signal'] = 'neutral'
            else:
                bb_signal = "no disponible"
                df['bb_signal'] = 'neutral'
            
            # Evaluación de niveles Fibonacci (deshabilitado por ahora)
            fib_signal = "neutral"
            # TODO: Implementar cálculo de niveles Fibonacci si se requiere
            
            # Combinación de señales para estrategia de scalping
            # Se requiere al menos 2 puntos de fuerza para generar señal
            if signal_strength >= 2:
                buy_signal = True
                df['combined_signal'] = 'buy'
            elif signal_strength <= -2:
                sell_signal = True
                df['combined_signal'] = 'sell'
            else:
                df['combined_signal'] = 'neutral'
            
            # Registrar indicadores en Supabase (si está habilitado)
            if indicator_logger and indicator_logger.enabled:
                try:
                    # Añadir EMA para consistencia con registros anteriores
                    ema_short_period = min(10, len(df) - 3)  # EMA corta
                    ema_long_period = min(21, len(df) - 3)   # EMA larga
                    df['ema_short'] = df['close'].ewm(span=ema_short_period, adjust=False).mean()
                    df['ema_long'] = df['close'].ewm(span=ema_long_period, adjust=False).mean()
                    
                    # Registrar indicadores con todos los parámetros
                    indicator_params = {
                        'rsi_period': rsi_period,
                        'rsi_oversold': rsi_oversold,
                        'rsi_overbought': rsi_overbought,
                        'macd_fast': fast_period,
                        'macd_slow': slow_period,
                        'macd_signal': signal_period,
                        'bb_period': bb_period,
                        'bb_stddev': bb_std,
                        'signal_strength': signal_strength,
                        'ema_short_period': ema_short_period,
                        'ema_long_period': ema_long_period
                    }
                    
                    success_count, fail_count = indicator_logger.log_indicators_from_dataframe(
                        df=df,
                        symbol=symbol,
                        timeframe=timeframe,
                        parameters=indicator_params
                    )
                    
                    if success_count > 0:
                        logging.info(f"📊 Indicadores registrados en Supabase: {success_count} éxitos, {fail_count} fallos")
                    elif fail_count > 0:
                        logging.warning(f"⚠️ Fallos al registrar indicadores: {fail_count}")
                    
                except Exception as e:
                    logging.error(f"❌ Error al registrar indicadores: {e}")
            
            signals = {
                'rsi': current_rsi,
                'macd_line': current_macd,
                'signal_line': current_signal,
                'histogram': current_hist,
                'buy_signal': buy_signal,
                'sell_signal': sell_signal,
                'rsi_signal': rsi_signal,
                'macd_signal': macd_signal
            }
            
            logging.info(f"Análisis completado: RSI={current_rsi:.2f}, MACD={current_hist:.2f}, Señal={'COMPRA' if buy_signal else 'VENTA' if sell_signal else 'NEUTRAL'}")
                
            return signals
                
        except Exception as e:
            import traceback
            logging.error(f"Error en analyze_market: {e}")
            logging.error(traceback.format_exc())
            return {
                'rsi': None,
                'macd_line': None,
                'signal_line': None,
                'histogram': None,
                'buy_signal': False,
                'sell_signal': False,
                'error': str(e)
            }


class CryptoTradingBot:
    """Bot de trading de criptomonedas basado en indicadores técnicos
    Con integración dual en SQLite (local) y Supabase (cloud)"""
    
    def __init__(self, config: TradingConfig, api_key: str, api_secret: str, sandbox: bool = False, use_supabase: bool = True):
        self.config = config
        # Ahora trabajamos con una lista de símbolos en lugar de un símbolo único
        self.symbols = config.symbols
        self.api_key = api_key
        self.api_secret = api_secret
        self.sandbox = sandbox
        self.use_supabase = use_supabase
        
        # Inicializar componentes
        self.db_manager = DatabaseManager(config.db_name, use_supabase=self.use_supabase)
        self.notifier = NotificationManager()
        self.analyzer = TechnicalAnalyzer()
        
        # Inicializar conexión con exchange
        exchange_config = {
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'enableRateLimit': True,
        }


        self.exchange = ccxt.binance(exchange_config)
        
        if self.sandbox:
            self.exchange.set_sandbox_mode(True)
            logging.info("⚠️ Modo SANDBOX activado - Usando Binance Testnet")
        
        # Configuración de registro de operaciones
        self.log_registry = {
            'local': True,              # SQLite siempre activo
            'cloud': self.use_supabase  # Supabase configurable
        }
        logging.info(f"📊 Registro de operaciones: Local={self.log_registry['local']}, Cloud={self.log_registry['cloud']}")
        
        # Variables de estado
        self.running = False
        self.last_check = datetime.now()
        self.positions = {}
        self.last_signal_time = None
        
        # Configurar logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('trading_bot.log'),
                logging.StreamHandler()
            ]
        )
        
        logging.info("Bot de trading inicializado")
    
    def get_market_data(self, symbol: str, limit: int = 100) -> pd.DataFrame:
        """Obtiene datos del mercado para un símbolo específico"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(
                symbol, 
                self.config.timeframe, 
                limit=limit
            )
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            return df
        
        except Exception as e:
            logging.error(f"Error obteniendo datos del mercado para {symbol}: {e}")
            return pd.DataFrame()
    
    def calculate_indicators(self, df: pd.DataFrame) -> Dict:
        """Calcula todos los indicadores técnicos"""
        if df.empty or len(df) < 50:
            return {}
        
        close_prices = df['close'].values
        volume = df['volume'].values
        
        # RSI
        rsi = TechnicalAnalysis.calculate_rsi(close_prices, self.config.rsi_period)
        
        # MACD
        macd_line, signal_line, histogram = TechnicalAnalysis.calculate_macd(
            close_prices, self.config.macd_fast, self.config.macd_slow, self.config.macd_signal
        )
        
        # EMA Filter
        ema_filter = TechnicalAnalysis.calculate_ema(close_prices, self.config.ema_filter)
        
        # Volume filter
        avg_volume = pd.Series(volume).rolling(20).mean().values
        
        return {
            'rsi': rsi[-1] if not np.isnan(rsi[-1]) else 50,
            'macd_line': macd_line[-1] if not np.isnan(macd_line[-1]) else 0,
            'signal_line': signal_line[-1] if not np.isnan(signal_line[-1]) else 0,
            'histogram': histogram[-1] if not np.isnan(histogram[-1]) else 0,
            'ema_filter': ema_filter[-1] if not np.isnan(ema_filter[-1]) else close_prices[-1],
            'current_price': close_prices[-1],
            'volume': volume[-1],
            'avg_volume': avg_volume[-1] if not np.isnan(avg_volume[-1]) else volume[-1],
            'prev_macd': macd_line[-2] if len(macd_line) > 1 and not np.isnan(macd_line[-2]) else 0,
            'prev_signal': signal_line[-2] if len(signal_line) > 1 and not np.isnan(signal_line[-2]) else 0
        }
    
    def generate_signal(self, indicators: Dict) -> str:
        """Genera señales de trading"""
        if not indicators:
            return 'HOLD'
        
        # Verificar horario de trading
        if not TechnicalAnalysis.is_trading_hours(
            self.config.trading_start_hour, 
            self.config.trading_end_hour
        ):
            return 'HOLD'
        
        rsi = indicators['rsi']
        macd_line = indicators['macd_line']
        signal_line = indicators['signal_line']
        prev_macd = indicators['prev_macd']
        prev_signal = indicators['prev_signal']
        current_price = indicators['current_price']
        ema_filter = indicators['ema_filter']
        volume = indicators['volume']
        avg_volume = indicators['avg_volume']
        
        # Señal de COMPRA
        buy_conditions = [
            rsi < self.config.rsi_oversold,  # RSI en sobreventa
            macd_line > signal_line and prev_macd <= prev_signal,  # MACD cruzó por encima
            macd_line < 0,  # MACD por debajo de cero
            current_price < ema_filter,  # Precio por debajo de EMA
            volume > avg_volume  # Volumen superior al promedio
        ]
        
        if all(buy_conditions):
            return 'BUY'
        
        # Señal de VENTA
        sell_conditions = [
            rsi > self.config.rsi_overbought,  # RSI en sobrecompra
            macd_line < signal_line and prev_macd >= prev_signal,  # MACD cruzó por debajo
            macd_line > 0,  # MACD por encima de cero
            current_price > ema_filter,  # Precio por encima de EMA
            volume > avg_volume  # Volumen superior al promedio
        ]
        
        if all(sell_conditions):
            return 'SELL'
        
        return 'HOLD'
    
    def get_account_balance(self) -> Dict:
        """Obtiene el balance de la cuenta"""
        try:
            # Obtener todos los balances
            balances = self.exchange.fetch_balance()
            # Filtrar solo aquellos con saldo disponible
            available_balances = {
                currency: float(balance) for currency, balance in balances['free'].items() 
                if float(balance) > 0
            }
            return available_balances
        except Exception as e:
            logging.error(f"Error al obtener balance de cuenta: {e}")
            return {}
            
    def is_trading_hours(self):
        """Verifica si estamos en horario de trading
        
        Configurado para operar 24/7 sin restricciones horarias
        Los parámetros de configuración se mantienen por compatibilidad
        pero son ignorados ya que el bot está configurado para operar 24 horas
        """
        # Siempre devuelve True para operar 24/7
        return True
            
    def get_current_price(self, symbol: str):
        """Obtiene el precio actual del símbolo especificado"""
        max_retries = 3
        retry_delay = 2  # segundos
        
        for attempt in range(1, max_retries + 1):
            try:
                ticker = self.exchange.fetch_ticker(symbol)
                if 'last' in ticker and ticker['last'] is not None:
                    return ticker['last']
                else:
                    logging.warning(f"El ticker no contiene precio 'last' válido para {symbol}: {ticker}")
                    if attempt < max_retries:
                        logging.info(f"Reintentando obtener precio de {symbol} ({attempt}/{max_retries})...")
                        time.sleep(retry_delay)
                        continue
                    return 0.0  # Valor predeterminado para evitar errores de formato
            except Exception as e:
                if attempt < max_retries:
                    logging.warning(f"Error al obtener precio de {symbol} (intento {attempt}/{max_retries}): {e}")
                    logging.info(f"Reintentando en {retry_delay} segundos...")
                    time.sleep(retry_delay)
                else:
                    logging.error(f"Error al obtener precio de {symbol} después de {max_retries} intentos: {e}")
                    return 0.0  # Valor predeterminado para evitar errores de formato
    
    def calculate_position_size(self, price: float, balance: Dict) -> float:
        """Calcula el tamaño de la posición"""
        available_usdt = balance['USDT'] if 'USDT' in balance else 0
        max_investment = available_usdt * (self.config.max_position_size / 100)
        
        # Calcular cantidad de BTC a comprar
        btc_amount = max_investment / price
        
        # Aplicar límites mínimos del exchange
        min_notional = 10  # Binance mínimo ~10 USDT
        if max_investment < min_notional:
            logging.warning(f"Inversión muy pequeña: {max_investment} USDT")
            return 0
        
        return btc_amount
    
    def execute_trade(self, signal: str, indicators: Dict) -> bool:
        """Ejecuta una operación de trading"""
        try:
            balance = self.get_account_balance()
            current_price = indicators['current_price']
            
            if signal == 'BUY' and len(self.positions) < self.config.max_positions:
                # Calcular tamaño de posición
                amount = self.calculate_position_size(current_price, balance)
                
                if amount <= 0:
                    logging.info("Cantidad insuficiente para abrir posición")
                    return False
                
                # Ejecutar orden de compra
                order = self.exchange.create_market_buy_order(self.config.symbol, amount)
                
                if order['status'] == 'closed' or order['filled'] > 0:
                    entry_price = order['average'] or current_price
                    actual_amount = order['filled']
                    
                    # Calcular niveles de stop loss y take profit
                    stop_loss = entry_price * (1 - self.config.stop_loss_pct / 100)
                    take_profit_1 = entry_price * (1 + self.config.take_profit_1_pct / 100)
                    take_profit_2 = entry_price * (1 + self.config.take_profit_2_pct / 100)
                    
                    # Guardar posición
                    position_id = f"{self.config.symbol}_{int(time.time())}"
                    self.positions[position_id] = {
                        'symbol': self.config.symbol,
                        'side': 'long',
                        'amount': actual_amount,
                        'entry_price': entry_price,
                        'stop_loss': stop_loss,
                        'take_profit_1': take_profit_1,
                        'take_profit_2': take_profit_2,
                        'tp1_filled': False,
                        'tp2_filled': False,
                        'entry_time': datetime.now().isoformat()
                    }
                    
                    # Log del trade
                    trade_data = {
                        'timestamp': datetime.now().isoformat(),
                        'symbol': self.config.symbol,
                        'side': 'BUY',
                        'amount': actual_amount,
                        'price': entry_price,
                        'total': actual_amount * entry_price,
                        'status': 'FILLED',
                        'strategy_signal': 'RSI_MACD_BUY',
                        'rsi_value': indicators['rsi'],
                        'macd_value': indicators['macd_line'],
                        'notes': f'SL: {stop_loss:.2f}, TP1: {take_profit_1:.2f}, TP2: {take_profit_2:.2f}'
                    }
                    
                    self.db.log_trade(trade_data)
                    
                    # Notificación
                    message = f"""
                    🚀 COMPRA EJECUTADA
                    Par: {self.config.symbol}
                    Cantidad: {actual_amount:.6f} BTC
                    Precio: ${entry_price:.2f}
                    Total: ${actual_amount * entry_price:.2f}
                    
                    Stop Loss: ${stop_loss:.2f}
                    Take Profit 1: ${take_profit_1:.2f}
                    Take Profit 2: ${take_profit_2:.2f}
                    
                    RSI: {indicators['rsi']:.2f}
                    MACD: {indicators['macd_line']:.4f}
                    """
                    
                    self.notifications.send_email("🚀 Nueva Compra Ejecutada", message)
                    logging.info(f"Compra ejecutada: {actual_amount:.6f} BTC a ${entry_price:.2f}")
                    
                    return True
            
            elif signal == 'SELL' and self.positions:
                # Cerrar todas las posiciones largas
                for pos_id, position in list(self.positions.items()):
                    self.close_position(pos_id, "SELL_SIGNAL", current_price)
                
                return True
        
        except Exception as e:
            logging.error(f"Error ejecutando trade: {e}")
            return False
        
        return False
    
    def close_position(self, position_id: str, reason: str, current_price: float):
        """Cierra una posición"""
        try:
            if position_id not in self.positions:
                return
            
            position = self.positions[position_id]
            amount = position['amount']
            
            # Ejecutar orden de venta
            order = self.exchange.create_market_sell_order(self.config.symbol, amount)
            
            if order['status'] == 'closed' or order['filled'] > 0:
                exit_price = order['average'] or current_price
                pnl = (exit_price - position['entry_price']) * amount
                pnl_pct = (exit_price / position['entry_price'] - 1) * 100
                
                # Log del trade
                trade_data = {
                    'timestamp': datetime.now().isoformat(),
                    'symbol': self.config.symbol,
                    'side': 'SELL',
                    'amount': amount,
                    'price': exit_price,
                    'total': amount * exit_price,
                    'pnl': pnl,
                    'status': 'FILLED',
                    'strategy_signal': reason,
                    'rsi_value': 0,
                    'macd_value': 0,
                    'notes': f'Entry: ${position["entry_price"]:.2f}, PnL: {pnl_pct:.2f}%'
                }
                
                self.db.log_trade(trade_data)
                
                # Notificación
                message = f"""
                💰 VENTA EJECUTADA
                Par: {self.config.symbol}
                Cantidad: {amount:.6f} BTC
                Precio Entrada: ${position['entry_price']:.2f}
                Precio Salida: ${exit_price:.2f}
                
                PnL: ${pnl:.2f} ({pnl_pct:.2f}%)
                Razón: {reason}
                """
                
                emoji = "🟢" if pnl > 0 else "🔴"
                self.notifications.send_email(f"{emoji} Posición Cerrada", message)
                logging.info(f"Posición cerrada: PnL ${pnl:.2f} ({pnl_pct:.2f}%)")
                
                # Remover posición
                del self.positions[position_id]
        
        except Exception as e:
            logging.error(f"Error cerrando posición: {e}")
    
    def execute_buy_order(self, symbol: str, current_price: float) -> bool:
        """Ejecuta una orden de compra para el símbolo especificado"""
        try:
            balance = self.get_account_balance()
            if 'USDT' not in balance or balance['USDT'] <= 0:
                logging.warning(f"No hay suficiente balance USDT para {symbol}")
                return False
                
            # Verificar si ya tenemos demasiadas posiciones abiertas
            positions_for_symbol = [p for p in self.positions.values() if p['symbol'] == symbol]
            if len(positions_for_symbol) >= self.config.max_positions_per_symbol:
                logging.warning(f"Máximo de posiciones alcanzado para {symbol}")
                return False
                
            # Calcular tamaño de posición
            max_investment = balance['USDT'] * (self.config.max_position_size / 100)
            # Si tenemos múltiples símbolos, dividimos el capital entre todos
            if len(self.config.symbols) > 1:
                max_investment = max_investment / len(self.config.symbols)
                
            # Calcular cantidad de criptomoneda a comprar
            amount = max_investment / current_price
            
            # Aplicar límites mínimos del exchange
            min_notional = 10  # Binance mínimo ~10 USDT
            if max_investment < min_notional:
                logging.warning(f"Inversión muy pequeña para {symbol}: {max_investment} USDT")
                return False
            
            # Ejecutar la orden de compra
            logging.info(f"Ejecutando compra de {amount:.8f} {symbol} a ${current_price:.2f}")
            order = self.exchange.create_market_buy_order(symbol, amount)
            
            if order['status'] == 'closed' or order['filled'] > 0:
                entry_price = order['average'] or current_price
                actual_amount = order['filled']
                
                # Calcular niveles de stop loss y take profit
                stop_loss = entry_price * (1 - self.config.stop_loss_pct / 100)
                take_profit_1 = entry_price * (1 + self.config.take_profit_1_pct / 100)
                take_profit_2 = entry_price * (1 + self.config.take_profit_2_pct / 100)
                
                # Guardar posición
                position_id = f"{symbol}_{int(time.time())}"
                self.positions[position_id] = {
                    'symbol': symbol,
                    'side': 'long',
                    'amount': actual_amount,
                    'entry_price': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit_1': take_profit_1,
                    'take_profit_2': take_profit_2,
                    'tp1_filled': False,
                    'tp2_filled': False,
                    'entry_time': datetime.now().isoformat()
                }
                
                # Log del trade
                trade_data = {
                    'timestamp': datetime.datetime.now().isoformat(),
                    'symbol': symbol,
                    'side': 'BUY',
                    'amount': actual_amount,
                    'price': entry_price,
                    'total': actual_amount * entry_price,
                    'status': 'FILLED',
                    'strategy_signal': 'RSI_MACD_BUY',
                    'rsi_value': 0,  # Estos valores se podrían rellenar si tenemos los indicadores
                    'macd_value': 0,  # Estos valores se podrían rellenar si tenemos los indicadores
                    'notes': f'SL: {stop_loss:.2f}, TP1: {take_profit_1:.2f}, TP2: {take_profit_2:.2f}'
                }
                
                self.db_manager.log_trade(trade_data)
                
                # Notificación
                message = f"""
                🚀 COMPRA EJECUTADA
                Par: {symbol}
                Cantidad: {actual_amount:.6f}
                Precio: ${entry_price:.2f}
                Total: ${actual_amount * entry_price:.2f}
                
                Stop Loss: ${stop_loss:.2f}
                Take Profit 1: ${take_profit_1:.2f}
                Take Profit 2: ${take_profit_2:.2f}
                """
                
                logging.info(f"Compra ejecutada: {actual_amount:.6f} de {symbol} a ${entry_price:.2f}")
                self.notifier.send_message("🚀 Nueva Compra Ejecutada", message)
                
                return True
            else:
                logging.warning(f"La orden para {symbol} no se completó correctamente: {order}")
                return False
                
        except Exception as e:
            logging.error(f"Error ejecutando orden de compra para {symbol}: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return False

    def close_positions(self, symbol: str, current_price: float, reason: str) -> bool:
        """Cierra todas las posiciones abiertas para un símbolo específico"""
        try:
            # Filtrar posiciones por símbolo
            symbol_positions = {pos_id: position for pos_id, position in self.positions.items()
                               if position['symbol'] == symbol}
            
            if not symbol_positions:
                logging.info(f"No hay posiciones abiertas para {symbol}")
                return False
            
            successful_closes = 0
            
            # Cerrar cada posición para el símbolo
            for pos_id, position in symbol_positions.items():
                amount = position['amount']
                
                # Ejecutar orden de venta
                logging.info(f"Cerrando posición {pos_id} para {symbol}: {amount} a ${current_price:.2f}")
                order = self.exchange.create_market_sell_order(symbol, amount)
                
                if order['status'] == 'closed' or order['filled'] > 0:
                    exit_price = order['average'] or current_price
                    actual_amount = order['filled'] or amount
                    
                    # Calcular PnL
                    pnl = (exit_price - position['entry_price']) * actual_amount
                    pnl_pct = (exit_price / position['entry_price'] - 1) * 100
                    
                    # Log del trade
                    trade_data = {
                        'timestamp': datetime.now().isoformat(),
                        'symbol': symbol,
                        'side': 'SELL',
                        'amount': actual_amount,
                        'price': exit_price,
                        'total': actual_amount * exit_price,
                        'pnl': pnl,
                        'status': 'FILLED',
                        'strategy_signal': reason,
                        'rsi_value': 0,
                        'macd_value': 0,
                        'notes': f'Entry: ${position["entry_price"]:.2f}, PnL: {pnl_pct:.2f}%'
                    }
                    
                    self.db_manager.log_trade(trade_data)
                    
                    # Notificación
                    message = f"""
                    💰 VENTA EJECUTADA
                    Par: {symbol}
                    Cantidad: {actual_amount:.6f}
                    Precio Entrada: ${position['entry_price']:.2f}
                    Precio Salida: ${exit_price:.2f}
                    
                    PnL: ${pnl:.2f} ({pnl_pct:.2f}%)
                    Razón: {reason}
                    """
                    
                    emoji = "🟢" if pnl > 0 else "🔴"
                    self.notifier.send_message(f"{emoji} Posición Cerrada", message)
                    logging.info(f"Posición {pos_id} cerrada: PnL ${pnl:.2f} ({pnl_pct:.2f}%)")
                    
                    # Remover posición
                    del self.positions[pos_id]
                    successful_closes += 1
                else:
                    logging.warning(f"La orden de venta para {symbol} no se completó correctamente: {order}")
            
            return successful_closes > 0
                
        except Exception as e:
            logging.error(f"Error cerrando posiciones para {symbol}: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return False
            
    def manage_positions(self, current_price: float):
        """Gestiona las posiciones abiertas"""
        for pos_id, position in list(self.positions.items()):
            entry_price = position['entry_price']
            stop_loss = position['stop_loss']
            take_profit_1 = position['take_profit_1']
            take_profit_2 = position['take_profit_2']
            
            # Stop Loss
            if current_price <= stop_loss:
                self.close_position(pos_id, "STOP_LOSS", current_price)
                continue
            
            # Take Profit 1 (30% de la posición)
            if current_price >= take_profit_1 and not position['tp1_filled']:
                try:
                    partial_amount = position['amount'] * 0.3
                    order = self.exchange.create_market_sell_order(self.config.symbol, partial_amount)
                    
                    if order['status'] == 'closed' or order['filled'] > 0:
                        position['tp1_filled'] = True
                        position['amount'] -= order['filled']
                        
                        # Actualizar trailing stop
                        new_trailing_stop = current_price * (1 - self.config.trailing_stop_pct / 100)
                        if new_trailing_stop > position['stop_loss']:
                            position['stop_loss'] = new_trailing_stop
                        
                        logging.info(f"TP1 ejecutado: {order['filled']:.6f} BTC a ${current_price:.2f}")
                
                except Exception as e:
                    logging.error(f"Error ejecutando TP1: {e}")
            
            # Take Profit 2 (50% de la posición restante)
            if current_price >= take_profit_2 and not position['tp2_filled'] and position['tp1_filled']:
                try:
                    partial_amount = position['amount'] * 0.5
                    order = self.exchange.create_market_sell_order(self.config.symbol, partial_amount)
                    
                    if order['status'] == 'closed' or order['filled'] > 0:
                        position['tp2_filled'] = True
                        position['amount'] -= order['filled']
                        
                        logging.info(f"TP2 ejecutado: {order['filled']:.6f} BTC a ${current_price:.2f}")
                
                except Exception as e:
                    logging.error(f"Error ejecutando TP2: {e}")
            
            # Trailing Stop después de TP1
            if position['tp1_filled']:
                trailing_stop = current_price * (1 - self.config.trailing_stop_pct / 100)
                if trailing_stop > position['stop_loss']:
                    position['stop_loss'] = trailing_stop
            
            # Salida por RSI extremo
            df = self.get_market_data(50)
            if not df.empty:
                indicators = self.calculate_indicators(df)
                if indicators.get('rsi', 50) > 80:
                    self.close_position(pos_id, "RSI_EXTREME", current_price)
    
    def run_strategy(self):
        """Ejecuta la estrategia de trading para todos los símbolos configurados"""
        try:
            logging.info("=== Ejecutando estrategia de trading para múltiples pares ===")
            
            # Verificar horario de trading
            if not self.is_trading_hours():
                hora_actual = datetime.datetime.utcnow().hour
                logging.info(f"Fuera de horario de trading ({hora_actual} UTC). Horario: {self.config.trading_start_hour}-{self.config.trading_end_hour} UTC")
                return
            
            logging.info("Dentro de horario de trading")
            
            # Comprobar posiciones activas
            # Convertir la lista de posiciones a un diccionario indexado por ID para mantener compatibilidad
            positions_list = self.db_manager.get_active_positions()
            self.positions = {}
            for position in positions_list:
                # Usar el campo 'id' como clave si existe, o generar uno nuevo
                position_id = position.get('id') or position.get('local_id') or str(uuid.uuid4())
                self.positions[position_id] = position
            logging.info(f"Posiciones activas: {len(self.positions)}/{self.config.max_positions}")
            
            if len(self.positions) >= self.config.max_positions:
                logging.info(f"Número máximo de posiciones alcanzado ({len(self.positions)}/{self.config.max_positions})")
                return
            
            # Comprobar conexión con exchange
            try:
                self.exchange.load_markets()
                logging.info(f"Conexión con {self.exchange.name} establecida correctamente")
            except Exception as e:
                logging.error(f"Error al conectar con {self.exchange.name}: {e}")
                return
            
            # Inicializar variable signal para evitar errores
            signal = "Sin señales"
            
            # Procesar cada símbolo configurado
            for symbol in self.symbols:
                logging.info(f"\n=== Procesando par {symbol} en timeframe {self.config.timeframe} ===")
                
                # Obtener precio actual para este símbolo
                try:
                    ticker = self.exchange.fetch_ticker(symbol)
                    current_price = ticker['last'] if ticker and 'last' in ticker else None
                    
                    if current_price is None:
                        logging.error(f"No se pudo obtener precio actual para {symbol}")
                        continue
                    
                    logging.info(f"Precio actual de {symbol}: ${current_price:.2f}")
                except Exception as e:
                    logging.error(f"Error al obtener precio actual para {symbol}: {e}")
                    continue
                
                # Analizar mercado con múltiples reintentos
                logging.info(f"Analizando mercado para {symbol} en timeframe {self.config.timeframe}...")
                max_analysis_retries = 3
                retry_delay = 3  # segundos
                indicators = {}
                
                for attempt in range(1, max_analysis_retries + 1):
                    try:
                        indicators = self.analyzer.analyze_market(symbol, self.config.timeframe, self.exchange)
                        
                        # Verificar si hay error en los indicadores
                        if 'error' in indicators and indicators['error']:
                            if attempt < max_analysis_retries:
                                logging.warning(f"Error en análisis de mercado para {symbol} (intento {attempt}/{max_analysis_retries}): {indicators['error']}")
                                logging.info(f"Reintentando análisis en {retry_delay} segundos...")
                                time.sleep(retry_delay)
                                continue
                            else:
                                logging.warning(f"No se pudo completar el análisis de mercado para {symbol} después de {max_analysis_retries} intentos")
                                break
                        
                        # Verificar que los indicadores no sean None
                        if indicators.get('rsi') is None or indicators.get('macd_line') is None:
                            if attempt < max_analysis_retries:
                                logging.warning(f"Indicadores incompletos para {symbol} (intento {attempt}/{max_analysis_retries}), reintentando...")
                                time.sleep(retry_delay)
                                continue
                            else:
                                logging.warning(f"No se pudieron calcular indicadores para {symbol} después de {max_analysis_retries} intentos")
                                break
                            
                        # Si llegamos aquí, los indicadores están completos
                        break
                        
                    except Exception as e:
                        if attempt < max_analysis_retries:
                            logging.error(f"Error en analyze_market para {symbol} (intento {attempt}/{max_analysis_retries}): {e}")
                            logging.info(f"Reintentando en {retry_delay} segundos...")
                            time.sleep(retry_delay)
                        else:
                            logging.error(f"Error en analyze_market para {symbol} después de {max_analysis_retries} intentos: {e}")
                            break
                
                # Si no tenemos indicadores válidos, pasamos al siguiente símbolo
                if not indicators or 'error' in indicators or indicators.get('rsi') is None:
                    logging.warning(f"No hay indicadores disponibles para {symbol}, pasando al siguiente par")
                    continue
                
                # Comprobar señales para este símbolo
                signal = "Neutral"
                
                if indicators.get('buy_signal'):
                    signal = "Compra"
                    logging.info(f"SEÑAL DE COMPRA DETECTADA para {symbol} a ${current_price:.2f}")
                    if not self.sandbox:
                        logging.info(f"Ejecutando orden de compra para {symbol}...")
                        self.execute_buy_order(symbol, current_price)
                    else:
                        logging.info("Modo sandbox: no se ejecuta orden real")
                elif indicators.get('sell_signal'):
                    signal = "Venta"
                    logging.info(f"SEÑAL DE VENTA DETECTADA para {symbol} a ${current_price:.2f}")
                    if not self.sandbox:
                        logging.info(f"Cerrando posiciones para {symbol}...")
                        self.close_positions(symbol, current_price, "Señal de venta")
                    else:
                        logging.info("Modo simulación: no se ejecuta orden real")
                else:
                    logging.info(f"Sin señales para {symbol} en este momento. RSI: {indicators.get('rsi', 'N/A')}, MACD: {indicators.get('histogram', 'N/A')}")
                
                # Pequeña pausa entre símbolos para evitar rate limits
                time.sleep(1)
            else:
                logging.info("No se detectaron señales de trading")
            
            # Log detallado con formato mejorado
            rsi_value = indicators.get('rsi', float('nan'))
            macd_value = indicators.get('macd_line', float('nan'))
            signal_line = indicators.get('signal_line', float('nan'))
            hist_value = indicators.get('histogram', float('nan'))
            
            # Preparar los valores con el formato adecuado para evitar errores
            # Verificar si es None antes de usar math.isnan()
            rsi_formatted = "N/A" if rsi_value is None or (isinstance(rsi_value, float) and math.isnan(rsi_value)) else f"{rsi_value:.2f}"
            macd_formatted = "N/A" if macd_value is None or (isinstance(macd_value, float) and math.isnan(macd_value)) else f"{macd_value:.6f}"
            signal_formatted = "N/A" if signal_line is None or (isinstance(signal_line, float) and math.isnan(signal_line)) else f"{signal_line:.6f}"
            hist_formatted = "N/A" if hist_value is None or (isinstance(hist_value, float) and math.isnan(hist_value)) else f"{hist_value:.6f}"
            
            logging.info(f"""
            === ESTADO DEL BOT ===
            SÍMBOLO: {symbol}
            PRECIO: ${current_price:.2f}
            RSI: {rsi_formatted} (Sobrecompra >70, Sobreventa <30)
            MACD: {macd_formatted}
            Señal MACD: {signal_formatted}
            Histograma: {hist_formatted}
            INTERPRETACIÓN: {signal}
            POSICIONES: {len(self.positions)}/{self.config.max_positions}
            ======================
            """)
            
            # Actualizar métricas en Supabase si está activado
            if self.use_supabase and self.db_manager.supabase:
                try:
                    self.db_manager.supabase.update_performance_metrics()
                    logging.info("Métricas de rendimiento actualizadas en Supabase")
                except Exception as e:
                    logging.error(f"Error al actualizar métricas en Supabase: {e}")
        
        except Exception as e:
            import traceback
            logging.error(f"Error en run_strategy: {e}")
            logging.error(traceback.format_exc())
    
    def start(self):
        """Inicia el bot de trading"""
        self.is_running = True
        logging.info("🚀 Bot de trading iniciado")
        
        # Ejecutar estrategia inmediatamente al iniciar
        logging.info("Ejecutando estrategia inmediatamente...")
        self.run_strategy()
        
        # Programar ejecución cada 15 minutos
        schedule.every(15).minutes.do(self.run_strategy)
        
        # Reporte diario
        schedule.every().day.at("00:00").do(self.daily_report)
        
        # Loop principal
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Verificar cada minuto
            except KeyboardInterrupt:
                logging.info("Deteniendo bot...")
                self.stop()
            except Exception as e:
                logging.error(f"Error en loop principal: {e}")
                time.sleep(300)  # Esperar 5 minutos en caso de error
    
    def stop(self):
        """Detiene el bot"""
        self.is_running = False
        logging.info("🛑 Bot de trading detenido")
    
    def daily_report(self):
        """Genera reporte diario"""
        try:
            balance = self.get_account_balance()
            
            # Calcular performance diaria
            conn = sqlite3.connect(self.config.db_name)
            today = datetime.now().date().isoformat()
            
            query = """
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                SUM(pnl) as daily_pnl
            FROM trades 
            WHERE DATE(timestamp) = ?
            """
            
            cursor = conn.cursor()
            cursor.execute(query, (today,))
            stats = cursor.fetchone()
            
            message = f"""
            📊 REPORTE DIARIO - {today}
            
            💰 Balance:
            - USDT: ${balance['total_usdt']:.2f}
            - BTC: {balance['total_btc']:.6f}
            
            📈 Trading:
            - Trades totales: {stats[0]}
            - Trades ganadores: {stats[1]}
            - Trades perdedores: {stats[2]}
            - PnL diario: ${stats[3] or 0:.2f}
            
            🔄 Posiciones activas: {len(self.positions)}
            """
            
            self.notifications.send_email("📊 Reporte Diario", message)
            conn.close()
            
        except Exception as e:
            logging.error(f"Error generando reporte diario: {e}")

def test_trade():
    """
    Función para probar una operación en modo sandbox
    """
    # Configuración de prueba con múltiples pares
    config = TradingConfig(
        exchange_id='binance',
        symbols=['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT'],
        timeframe='5m'  # Scalping con timeframe de 5 minutos
    )
    
    # Usar API Keys desde la configuración (entorno o Cloud Secret Manager)
    api_key = os.getenv('TESTNET_API_KEY')
    api_secret = os.getenv('TESTNET_API_SECRET')
    
    if not api_key or not api_secret:
        logging.error("❌ Error: No se encontraron credenciales de API en la configuración")
        return
    
    # Iniciar bot en modo sandbox
    bot = CryptoTradingBot(config, api_key, api_secret, sandbox=True, use_supabase=True)
    
    # Mostrar símbolos disponibles para prueba
    print("\n🔍 Símbolos configurados para trading:")
    for i, symbol in enumerate(config.symbols, 1):
        print(f"{i}. {symbol}")
    
    # Seleccionar un símbolo para la prueba (por defecto el primero)
    test_symbol = config.symbols[0]
    print(f"\n✅ Usando {test_symbol} para la prueba de operación")
    
    # Obtener balance actual
    balances = bot.exchange.fetch_balance()
    usdt_balance = balances['free'].get('USDT', 0)
    
    # Obtener saldo de la moneda base del par seleccionado
    base_currency = test_symbol.split('/')[0]
    base_balance = balances['free'].get(base_currency, 0)
    
    print("\n💰 Balance inicial:")
    print(f"USDT: ${usdt_balance:.2f}")
    print(f"{base_currency}: {base_balance:.8f}")
    
    # Obtener precio actual del símbolo seleccionado
    print("\n🔍 Obteniendo datos actuales del mercado...")
    ticker = bot.exchange.fetch_ticker(test_symbol)
    current_price = ticker['last']
    print(f"Precio actual de {test_symbol}: ${current_price}")
    
    # Calcular cantidad a comprar (máximo $100 o 1% del balance USDT)
    max_amount_usd = min(100.0, usdt_balance * 0.01)
    coin_amount = max_amount_usd / current_price
    
    # Redondear a 6 decimales para cumplir con los requisitos de Binance
    coin_amount = round(coin_amount, 6)
    
    print("\n⚙️ Ejecutando operación forzada de prueba...")
    print(f"Comprando {coin_amount} {base_currency} a ${current_price} (Total: ${coin_amount * current_price:.2f} USDT)")
    
    try:
        # Ejecutar orden de mercado para el símbolo seleccionado
        order = bot.exchange.create_market_buy_order(test_symbol, coin_amount)
        print("\n✅ Orden ejecutada con éxito!")
        print(f"ID de orden: {order['id']}")
        
        # Registrar el trade en la base de datos (local SQLite + Supabase)
        trade_data = {
            'timestamp': datetime.now(),
            'symbol': test_symbol,
            'side': 'buy',
            'amount': coin_amount,
            'price': current_price,
            'total': coin_amount * current_price,
            'status': 'open',
            'strategy_signal': 'test',
            'rsi_value': 50,  # Valores ficticios para pruebas
            'macd_value': 0,  # Valores ficticios para pruebas
            'notes': f'Operación de prueba forzada con Supabase para {test_symbol}'
        }
        
        # El registro en Supabase ocurre automáticamente dentro de log_trade si está habilitado
        trade_id = bot.db_manager.log_trade(trade_data)
        print(f"📝 Trade registrado con ID local: {trade_id}")
        
        # Calcular y mostrar stop loss y take profits
        stop_loss = current_price * (1 - config.stop_loss_pct / 100)
        take_profit_1 = current_price * (1 + config.take_profit_1_pct / 100)
        take_profit_2 = current_price * (1 + config.take_profit_2_pct / 100)
        
        print(f"\n🛑 Stop Loss: ${stop_loss:.2f} (-{config.stop_loss_pct}%)")
        print(f"📈 Take Profit 1: ${take_profit_1:.2f} (+{config.take_profit_1_pct}%)")
        print(f"📈 Take Profit 2: ${take_profit_2:.2f} (+{config.take_profit_2_pct}%)")
        
        # Mostrar balance actualizado
        balances = bot.exchange.fetch_balance()
        usdt_balance_after = balances['free'].get('USDT', 0)
        base_balance_after = balances['free'].get(base_currency, 0)
        
        print("\n💰 Balance después de la operación:")
        print(f"USDT: ${usdt_balance_after:.2f}")
        print(f"{base_currency}: {base_balance_after:.8f}")
        print(f"Cambio en {base_currency}: {base_balance_after - base_balance:.8f}")
        
        if bot.log_registry['cloud']:
            print("\n☁️ Operación sincronizada con Supabase Cloud")
        
    except Exception as e:
        print(f"\n❌ Error al ejecutar la operación: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🔔 Prueba completada.")

# Nota: La función start_http_server se ha eliminado ya que server.py se encarga de gestionar el servidor HTTP

def main():
    """
    Función principal del bot de trading
    """
    print("🚀 Iniciando bot de trading...")
    
    # Nota: El servidor HTTP ahora se gestiona desde server.py
    logging.info("ℹ️ El bot está utilizando el servidor HTTP gestionado por server.py")
    
    try:
        # Configuración del bot con múltiples pares
        config = TradingConfig(
            symbols=['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT'],
            timeframe='5m'  # Scalping con timeframe de 5 minutos
        )
        
        # Usar API Keys configuradas (desde variables de entorno o Secret Manager)
        if USE_TESTNET:
            api_key = TESTNET_API_KEY
            api_secret = TESTNET_API_SECRET
            logging.info("⚠️ Modo TESTNET activado - Usando Binance Testnet")
        else:
            api_key = REAL_API_KEY
            api_secret = REAL_API_SECRET
            logging.info("🔴 Modo REAL activado - Usando Binance Real")
        
        if not api_key or not api_secret:
            logging.error("❌ Error: No se encontraron credenciales API en la configuración")
            return 1
            
        # Inicializar bot con configuración y credenciales
        bot = CryptoTradingBot(config, api_key, api_secret, sandbox=USE_TESTNET)
        bot.start()
    except Exception as e:
        # Capturar cualquier error pero mantener el proceso vivo para que el servidor HTTP siga respondiendo
        logging.error(f"❌ Error en la ejecución del bot: {e}")
        logging.info("🔄 El servidor HTTP sigue ejecutándose a pesar del error")
        # Mantener el proceso vivo indefinidamente para que Cloud Run no reinicie el contenedor
        while True:
            time.sleep(60)

if __name__ == "__main__":
    # Para operación normal del bot usar: main()
    # Para pruebas inmediatas usar: test_trade()
    main()