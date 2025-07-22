#!/usr/bin/env python
"""
Módulo para registrar indicadores técnicos en Supabase
"""
import logging
import json
import socket
import datetime
import pandas as pd
from typing import Dict, Any, Optional, List, Tuple
from supabase import create_client, Client

# Importar configuración
from cloud_config import SUPABASE_URL, SUPABASE_KEY

class IndicatorLogger:
    """Clase para registrar indicadores técnicos y señales en Supabase"""
    
    def __init__(self):
        """Inicializar conexión con Supabase"""
        try:
            if not SUPABASE_URL or not SUPABASE_KEY:
                logging.warning("⚠️ Falta configuración de Supabase, logger de indicadores deshabilitado")
                self.enabled = False
                return
                
            self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
            self.enabled = True
            logging.info("✅ IndicatorLogger inicializado correctamente")
        except Exception as e:
            logging.error(f"❌ Error al inicializar IndicatorLogger: {e}")
            self.enabled = False
    
    def log_indicators(self, 
                      symbol: str,
                      timeframe: str,
                      timestamp: datetime.datetime,
                      close_price: float,
                      rsi: Optional[float] = None,
                      macd: Optional[float] = None,
                      macd_signal: Optional[float] = None,
                      macd_hist: Optional[float] = None,
                      ema_short: Optional[float] = None,
                      ema_long: Optional[float] = None,
                      bb_upper: Optional[float] = None,
                      bb_middle: Optional[float] = None,
                      bb_lower: Optional[float] = None,
                      rsi_signal: Optional[str] = None,
                      macd_signal_value: Optional[str] = None,
                      bb_signal: Optional[str] = None,
                      combined_signal: Optional[str] = None,
                      parameters: Optional[Dict[str, Any]] = None) -> bool:
        """
        Registra los indicadores técnicos en Supabase
        
        Args:
            symbol: Símbolo del par (ej: BTC/USDT)
            timeframe: Intervalo de tiempo (ej: 4h)
            timestamp: Datetime de la vela
            close_price: Precio de cierre
            rsi, macd, etc.: Valores de indicadores
            
        Returns:
            bool: True si se registró correctamente, False en caso contrario
        """
        if not self.enabled:
            logging.debug("Logger de indicadores deshabilitado, no se registrarán indicadores")
            return False
            
        try:
            # Preparar datos para insertar
            indicator_data = {
                "symbol": symbol,
                "timestamp": timestamp.isoformat(),
                "timeframe": timeframe,
                "close_price": close_price,
                "rsi": rsi,
                "macd": macd,
                "macd_signal": macd_signal,
                "macd_hist": macd_hist,
                "ema_short": ema_short,
                "ema_long": ema_long,
                "bb_upper": bb_upper,
                "bb_middle": bb_middle,
                "bb_lower": bb_lower,
                "rsi_signal": rsi_signal,
                "macd_signal_value": macd_signal_value,
                "bb_signal": bb_signal,
                "combined_signal": combined_signal,
                "parameters": parameters
            }
            
            # Filtrar valores None
            indicator_data = {k: v for k, v in indicator_data.items() if v is not None}
            
            # Insertar en Supabase con manejo de duplicados (upsert)
            # Usar formato de string o diccionario para on_conflict para que coincida exactamente con la restricción UNIQUE
            result = self.supabase.table("indicators").upsert(
                indicator_data, 
                on_conflict="symbol,timestamp,timeframe"  # Usar string con el orden exacto de columnas
            ).execute()
            
            if hasattr(result, 'data') and result.data:
                logging.debug(f"✅ Indicadores registrados para {symbol} {timeframe} @ {timestamp}")
                return True
            else:
                logging.warning(f"⚠️ Posible error al registrar indicadores para {symbol}: {result}")
                return False
                
        except Exception as e:
            logging.error(f"❌ Error al registrar indicadores en Supabase: {e}")
            return False
    
    def log_indicators_from_dataframe(self, 
                                     df: pd.DataFrame, 
                                     symbol: str, 
                                     timeframe: str,
                                     indicators: Dict[str, str] = None,
                                     parameters: Dict[str, Any] = None) -> Tuple[int, int]:
        """
        Registra indicadores desde un DataFrame con los resultados calculados
        
        Args:
            df: DataFrame con datos OHLCV e indicadores
            symbol: Símbolo del par
            timeframe: Timeframe
            indicators: Mapeo de columnas del DataFrame a columnas de la BD
            parameters: Parámetros utilizados para calcular los indicadores
            
        Returns:
            Tuple[int, int]: (registros_exitosos, registros_fallidos)
        """
        if not self.enabled or df.empty:
            return 0, 0
            
        # Mapeo por defecto de columnas
        default_indicators = {
            "close": "close_price",
            "rsi": "rsi",
            "macd": "macd",
            "macdsignal": "macd_signal",
            "macdhist": "macd_hist",
            "ema_short": "ema_short",
            "ema_long": "ema_long",
            "bb_upper": "bb_upper",
            "bb_middle": "bb_middle",
            "bb_lower": "bb_lower",
            "rsi_signal": "rsi_signal",
            "macd_signal": "macd_signal_value",
            "bb_signal": "bb_signal",
            "combined_signal": "combined_signal"
        }
        
        # Usar mapeo personalizado si se proporciona
        if indicators:
            indicator_map = {**default_indicators, **indicators}
        else:
            indicator_map = default_indicators
            
        success_count = 0
        fail_count = 0
        
        # Registrar los últimos N registros (para no sobrecargar la BD)
        last_n = min(25, len(df))
        for idx, row in df.tail(last_n).iterrows():
            try:
                # Construir diccionario para el registro
                data = {}
                
                # Añadir valores según mapeo
                for df_col, db_col in indicator_map.items():
                    if df_col in row and not pd.isna(row[df_col]):
                        data[db_col] = float(row[df_col]) if isinstance(row[df_col], (int, float)) else row[df_col]
                        
                # Asegurar valores requeridos
                if "close_price" not in data and "close" in row:
                    data["close_price"] = float(row["close"])
                    
                # Registrar indicadores
                timestamp = idx if isinstance(idx, datetime.datetime) else pd.Timestamp(idx).to_pydatetime()
                success = self.log_indicators(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=timestamp,
                    close_price=data.get("close_price", 0.0),
                    rsi=data.get("rsi"),
                    macd=data.get("macd"),
                    macd_signal=data.get("macd_signal"),
                    macd_hist=data.get("macd_hist"),
                    ema_short=data.get("ema_short"),
                    ema_long=data.get("ema_long"),
                    bb_upper=data.get("bb_upper"),
                    bb_middle=data.get("bb_middle"),
                    bb_lower=data.get("bb_lower"),
                    rsi_signal=data.get("rsi_signal"),
                    macd_signal_value=data.get("macd_signal_value"),
                    bb_signal=data.get("bb_signal"),
                    combined_signal=data.get("combined_signal"),
                    parameters=parameters
                )
                
                if success:
                    success_count += 1
                else:
                    fail_count += 1
                    
            except Exception as e:
                logging.error(f"❌ Error al registrar indicador desde DataFrame: {e}")
                fail_count += 1
                
        logging.info(f"📊 Registro de indicadores completado: {success_count} éxitos, {fail_count} fallos")
        return success_count, fail_count

# Instancia singleton para uso en toda la aplicación
indicator_logger = IndicatorLogger()

if __name__ == "__main__":
    # Código de prueba
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Crear instancia y probar registro
    logger = IndicatorLogger()
    
    # Datos de prueba
    test_data = {
        "symbol": "BTC/USDT",
        "timeframe": "4h",
        "timestamp": datetime.datetime.now(),
        "close_price": 45000.0,
        "rsi": 58.5,
        "macd": 120.5,
        "macd_signal": 100.2,
        "macd_hist": 20.3,
        "combined_signal": "buy",
        "parameters": {
            "rsi_period": 14,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9
        }
    }
    
    # Registrar indicador de prueba
    result = logger.log_indicators(**test_data)
    print(f"Resultado del registro: {'Éxito' if result else 'Fallo'}")
