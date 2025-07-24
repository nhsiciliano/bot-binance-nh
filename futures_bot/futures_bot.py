import logging
import pandas as pd
import time
from datetime import datetime
from binance.client import Client
from futures_bot.futures_config import FuturesTradingConfig
from futures_bot.futures_indicators import calculate_all_indicators, get_trading_signal
from futures_bot.futures_utils import set_leverage_and_margin_type, create_futures_order

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class FuturesBot:
    def __init__(self, client: Client, config: FuturesTradingConfig):
        self.client = client
        self.config = config
        self.positions = {}  # Tracking de posiciones abiertas
        self._initialize_symbols()
        logging.info(f"🚀 Bot de FUTUROS inicializado para {len(self.config.symbols)} pares con apalancamiento {self.config.leverage}x")

    def _initialize_symbols(self):
        """Configura apalancamiento y tipo de margen para todos los símbolos."""
        logging.info("🔧 Inicializando configuración de futuros...")
        for symbol in self.config.symbols:
            try:
                set_leverage_and_margin_type(self.client, symbol, self.config.leverage)
                logging.info(f"✅ {symbol}: Apalancamiento {self.config.leverage}x configurado")
            except Exception as e:
                logging.error(f"❌ Error configurando {symbol}: {e}")
        logging.info("✅ Configuración de símbolos completada")

    def _get_data_and_indicators(self, symbol: str) -> pd.DataFrame:
        """Obtiene datos OHLCV y calcula todos los indicadores."""
        try:
            # Obtener suficientes datos para EMA 200
            limit = max(self.config.ema_long_period + 10, 250)
            
            klines = self.client.get_historical_klines(
                symbol,
                self.config.timeframe,
                limit=limit
            )
            
            if not klines or len(klines) < self.config.ema_long_period:
                logging.warning(f"⚠️ {symbol}: Datos insuficientes ({len(klines) if klines else 0} velas)")
                return pd.DataFrame()
            
            # Crear DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 
                'close_time', 'quote_asset_volume', 'number_of_trades', 
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            
            # Convertir a numérico
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            
            # Calcular todos los indicadores
            df = calculate_all_indicators(df, self.config)
            
            return df
            
        except Exception as e:
            logging.error(f"❌ Error obteniendo datos para {symbol}: {e}")
            return pd.DataFrame()

    def _has_open_position(self, symbol: str) -> bool:
        """Verifica si hay una posición abierta para el símbolo dado."""
        try:
            positions = self.client.futures_position_information(symbol=symbol)
            for position in positions:
                position_amt = float(position['positionAmt'])
                if position_amt != 0:
                    logging.info(f"📊 {symbol}: Posición abierta {position_amt}")
                    return True
            return False
        except Exception as e:
            logging.error(f"❌ Error verificando posición para {symbol}: {e}")
            return False

    def _check_position_limits(self, symbol: str) -> bool:
        """Verifica si se pueden abrir más posiciones."""
        try:
            # Contar posiciones totales
            all_positions = self.client.futures_position_information()
            total_positions = sum(1 for pos in all_positions if float(pos['positionAmt']) != 0)
            
            # Contar posiciones para este símbolo
            symbol_positions = sum(1 for pos in all_positions 
                                 if pos['symbol'] == symbol and float(pos['positionAmt']) != 0)
            
            if total_positions >= self.config.max_positions:
                logging.warning(f"⚠️ Límite de posiciones totales alcanzado: {total_positions}/{self.config.max_positions}")
                return False
                
            if symbol_positions >= self.config.max_positions_per_symbol:
                logging.warning(f"⚠️ {symbol}: Límite de posiciones por símbolo alcanzado: {symbol_positions}/{self.config.max_positions_per_symbol}")
                return False
                
            return True
            
        except Exception as e:
            logging.error(f"❌ Error verificando límites de posición: {e}")
            return False

    def _get_symbol_precision(self, symbol: str) -> int:
        """Obtiene la precisión correcta para la cantidad según el símbolo."""
        # Precisiones típicas para futuros de Binance
        precision_map = {
            'BTCUSDT': 3,   # 0.001
            'ETHUSDT': 3,   # 0.001  
            'SOLUSDT': 1,   # 0.1
            'XRPUSDT': 0,   # 1 (entero)
        }
        return precision_map.get(symbol, 2)  # Default 2 decimales

    def _calculate_quantity(self, symbol: str, price: float) -> float:
        """Calcula la cantidad con la precisión correcta para el símbolo."""
        raw_quantity = self.config.trade_amount_usd / price
        precision = self._get_symbol_precision(symbol)
        
        # Redondear a la precisión correcta
        quantity = round(raw_quantity, precision)
        
        # Asegurar cantidad mínima
        min_quantity = 10 ** (-precision) if precision > 0 else 1
        if quantity < min_quantity:
            quantity = min_quantity
            
        logging.info(f"📊 {symbol}: Cantidad calculada {raw_quantity:.6f} → {quantity} (precisión: {precision})")
        return quantity

    def analyze_market(self):
        """Método principal para analizar el mercado y operar."""
        logging.info(f"🔍 === Iniciando análisis de mercado FUTUROS - {datetime.now().strftime('%H:%M:%S')} ===")
        
        for symbol in self.config.symbols:
            try:
                logging.info(f"\n📈 Analizando {symbol}...")
                
                # Verificar si ya hay posición abierta
                if self._has_open_position(symbol):
                    logging.info(f"⏭️ {symbol}: Saltando análisis (posición ya abierta)")
                    continue
                
                # Verificar límites de posición
                if not self._check_position_limits(symbol):
                    logging.info(f"⏭️ {symbol}: Saltando análisis (límites alcanzados)")
                    continue
                
                # Obtener datos e indicadores
                df = self._get_data_and_indicators(symbol)
                if df.empty:
                    logging.warning(f"⚠️ {symbol}: No se pudieron obtener datos")
                    continue
                
                # Obtener señal de trading
                signal, details = get_trading_signal(df, self.config)
                latest_price = df.iloc[-1]['close']
                
                # Log de indicadores
                logging.info(f"📊 {symbol} - Precio: ${latest_price:.4f}")
                logging.info(f"📊 RSI: {details.get('rsi', 'N/A'):.2f}, MACD: {details.get('macd', 'N/A'):.6f}, EMA200: ${details.get('ema_long', 'N/A'):.4f}")
                logging.info(f"📊 BB: Superior ${details.get('bb_upper', 'N/A'):.4f}, Inferior ${details.get('bb_lower', 'N/A'):.4f}")
                
                if signal == 'NEUTRAL':
                    logging.info(f"😐 {symbol}: {details.get('signal_reason', 'Sin señal')}")
                    continue
                
                # Señal encontrada
                logging.warning(f"🚨 {symbol}: SEÑAL {signal} detectada!")
                logging.warning(f"🎯 Razón: {details.get('signal_reason', 'N/A')}")
                
                # Calcular detalles de la orden
                quantity = self._calculate_quantity(symbol, latest_price)
                
                if signal == 'LONG':
                    side = 'BUY'
                    stop_loss_price = latest_price * (1 - self.config.stop_loss_pct)
                    take_profit_price = latest_price * (1 + self.config.take_profit_pct)
                    logging.info(f"📈 LONG: Cantidad {quantity}, SL ${stop_loss_price:.4f}, TP ${take_profit_price:.4f}")
                else:  # SHORT
                    side = 'SELL'
                    stop_loss_price = latest_price * (1 + self.config.stop_loss_pct)
                    take_profit_price = latest_price * (1 - self.config.take_profit_pct)
                    logging.info(f"📉 SHORT: Cantidad {quantity}, SL ${stop_loss_price:.4f}, TP ${take_profit_price:.4f}")
                
                # Ejecutar orden
                try:
                    logging.info(f"💰 Ejecutando orden {side} para {symbol}...")
                    order_result = create_futures_order(
                        self.client,
                        symbol,
                        side,
                        quantity,
                        round(stop_loss_price, 2),
                        round(take_profit_price, 2)
                    )
                    
                    if order_result:
                        logging.info(f"✅ {symbol}: Orden {side} ejecutada exitosamente")
                        logging.info(f"📋 Detalles: {order_result}")
                    else:
                        logging.error(f"❌ {symbol}: Error ejecutando orden {side}")
                        
                except Exception as order_error:
                    logging.error(f"❌ Error ejecutando orden para {symbol}: {order_error}")
                    
            except Exception as e:
                logging.error(f"❌ Error procesando símbolo {symbol}: {e}")
                import traceback
                traceback.print_exc()
        
        logging.info(f"🏁 === Análisis de mercado FUTUROS completado - {datetime.now().strftime('%H:%M:%S')} ===")

# Example usage (for testing)
# if __name__ == '__main__':
#     from cloud_config import get_secret
#     API_KEY = get_secret("FUTURES_API_KEY")
#     API_SECRET = get_secret("FUTURES_API_SECRET")
#     
#     client = Client(API_KEY, API_SECRET, testnet=True) # Use testnet for futures
#     config = FuturesTradingConfig()
#     bot = FuturesBot(client, config)
#     bot.analyze_market()
