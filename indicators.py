"""
Módulo para el cálculo de indicadores técnicos.
Provee funciones para calcular RSI, MACD y otros indicadores técnicos
usando implementaciones nativas con numpy y pandas, con ajustes para cantidades limitadas de datos.
"""
import logging
import numpy as np
import pandas as pd

def calculate_rsi(data, period=14, column='close'):
    """
    Calcula el índice de fuerza relativa (RSI) usando implementación nativa
    
    Args:
        data: DataFrame con datos OHLCV
        period: Período para RSI (por defecto 14)
        column: Columna para usar en el cálculo
        
    Returns:
        Serie con valores RSI calculados
    """
    try:
        if len(data) < period + 1:
            logging.warning(f"⚠️ Insuficientes datos para RSI (mínimo {period+1}, disponibles {len(data)})")
            return np.array([np.nan] * len(data))
        
        # Implementación nativa de RSI
        delta = data[column].diff()
        gain = delta.copy()
        loss = delta.copy()
        gain[gain < 0] = 0
        loss[loss > 0] = 0
        loss = abs(loss)
        
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        # Primera versión del RSI (período inicial)
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        # Convertir a numpy array para mantener compatibilidad con la API anterior
        rsi_values = rsi.to_numpy()
        
        if not np.isnan(rsi_values[-1]):
            logging.debug(f"✅ RSI calculado (período {period}) - último valor: {rsi_values[-1]:.2f}")
        
        return rsi_values
        
    except Exception as e:
        logging.error(f"❌ Error calculando RSI: {str(e)}")
        return np.array([np.nan] * len(data))

def calculate_macd(data, fast_period=12, slow_period=26, signal_period=9, column='close'):
    """
    Calcula Moving Average Convergence/Divergence (MACD) usando implementación nativa
    
    Args:
        data: DataFrame con datos OHLCV
        fast_period: Período para la media móvil rápida
        slow_period: Período para la media móvil lenta
        signal_period: Período de la señal
        column: Columna para usar en el cálculo
        
    Returns:
        Tupla de (macd, signal, histogram)
    """
    try:
        min_period = max(fast_period, slow_period) + signal_period
        
        if len(data) < min_period:
            logging.warning(f"⚠️ Insuficientes datos para MACD (mínimo {min_period}, disponibles {len(data)})")
            nan_array = np.array([np.nan] * len(data))
            return nan_array, nan_array, nan_array
            
        # Implementación nativa de MACD
        # Calcular las medias móviles exponenciales
        ema_fast = data[column].ewm(span=fast_period, adjust=False).mean()
        ema_slow = data[column].ewm(span=slow_period, adjust=False).mean()
        
        # MACD línea = EMA rápida - EMA lenta
        macd_line = ema_fast - ema_slow
        
        # Línea señal = EMA de MACD línea
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        
        # Histograma = MACD línea - línea señal
        histogram = macd_line - signal_line
        
        # Convertir a numpy arrays para mantener compatibilidad con la API anterior
        macd_values = macd_line.to_numpy()
        signal_values = signal_line.to_numpy()
        histogram_values = histogram.to_numpy()
        
        # Mostrar último valor
        if not np.isnan(histogram_values[-1]):
            logging.debug(f"✅ MACD calculado (períodos {fast_period}/{slow_period}/{signal_period}) - último valor: {histogram_values[-1]:.6f}")
        
        return macd_values, signal_values, histogram_values
        
    except Exception as e:
        logging.error(f"❌ Error calculando MACD: {str(e)}")
        nan_array = np.array([np.nan] * len(data))
        return nan_array, nan_array, nan_array

def calculate_ema(data, period=20, column='close'):
    """
    Calcula Exponential Moving Average (EMA) usando implementación nativa
    
    Args:
        data: DataFrame con datos OHLCV
        period: Período para el EMA
        column: Columna para usar en el cálculo
        
    Returns:
        Serie con valores EMA calculados
    """
    try:
        if len(data) < period + 1:
            logging.warning(f"⚠️ Insuficientes datos para EMA (mínimo {period+1}, disponibles {len(data)})")
            return np.array([np.nan] * len(data))
            
        # Calcular EMA usando pandas
        ema = data[column].ewm(span=period, adjust=False).mean().to_numpy()
        
        if not np.isnan(ema[-1]):
            logging.debug(f"✅ EMA calculado (período {period}) - último valor: {ema[-1]:.2f}")
        
        return ema
        
    except Exception as e:
        logging.error(f"❌ Error calculando EMA: {str(e)}")
        return np.array([np.nan] * len(data))

def calculate_bollinger_bands(data, period=20, stddev=2, column='close'):
    """
    Calcula Bandas de Bollinger usando implementación nativa
    
    Args:
        data: DataFrame con datos OHLCV
        period: Período para el promedio móvil
        stddev: Número de desviaciones estándar
        column: Columna para usar en el cálculo
        
    Returns:
        Tupla de (upper, middle, lower)
    """
    try:
        if len(data) < period + 1:
            logging.warning(f"⚠️ Insuficientes datos para Bollinger Bands (mínimo {period+1}, disponibles {len(data)})")
            nan_array = np.array([np.nan] * len(data))
            return nan_array, nan_array, nan_array
            
        # Calcular Bandas de Bollinger usando pandas
        # Media móvil simple
        middle = data[column].rolling(window=period).mean()
        
        # Desviación estándar
        rolling_std = data[column].rolling(window=period).std()
        
        # Banda superior e inferior
        upper = middle + (rolling_std * stddev)
        lower = middle - (rolling_std * stddev)
        
        # Convertir a numpy arrays para mantener compatibilidad
        upper_values = upper.to_numpy()
        middle_values = middle.to_numpy()
        lower_values = lower.to_numpy()
        
        logging.debug(f"✅ Bollinger Bands calculadas (período {period}, stddev {stddev})")
        return upper_values, middle_values, lower_values
        
    except Exception as e:
        logging.error(f"❌ Error calculando Bollinger Bands: {str(e)}")
        nan_array = np.array([np.nan] * len(data))
        return nan_array, nan_array, nan_array

def calculate_fibonacci_retracement(data, lookback=30, levels=[0.236, 0.382, 0.5, 0.618, 0.786], column='close'):
    """
    Calcula niveles de retroceso de Fibonacci basados en máximos y mínimos recientes.
    
    Args:
        data: DataFrame con datos OHLCV
        lookback: Número de velas para buscar máximos/mínimos
        levels: Niveles de Fibonacci a calcular
        column: Columna para usar en el cálculo
        
    Returns:
        Diccionario con niveles de retroceso de Fibonacci y tendencia detectada
    """
    try:
        if len(data) < lookback:
            logging.warning(f"⚠️ Insuficientes datos para Fibonacci (mínimo {lookback}, disponibles {len(data)})")
            return {'levels': {}, 'trend': None, 'high': None, 'low': None}
            
        # Obtener los últimos N precios según lookback
        recent_prices = data[column].iloc[-lookback:]
        
        # Encontrar máximo y mínimo recientes
        high = recent_prices.max()
        low = recent_prices.min()
        high_idx = recent_prices.idxmax()
        low_idx = recent_prices.idxmin()
        
        # Determinar tendencia
        if high_idx > low_idx:
            trend = 'up'  # El máximo es más reciente, tendencia alcista
        else:
            trend = 'down'  # El mínimo es más reciente, tendencia bajista
        
        # Calcular los niveles de retroceso
        fib_levels = {}
        range_price = high - low
        
        if trend == 'up':
            # Retroceso desde máximo (bajada)
            for level in levels:
                fib_levels[level] = high - (range_price * level)
            # Añadir niveles extremos
            fib_levels[0] = high
            fib_levels[1.0] = low
        else:  # trend == 'down'
            # Retroceso desde mínimo (subida)
            for level in levels:
                fib_levels[level] = low + (range_price * level)
            # Añadir niveles extremos
            fib_levels[0] = low
            fib_levels[1.0] = high
        
        logging.debug(f"✅ Niveles Fibonacci calculados - Tendencia: {trend}, High: {high:.2f}, Low: {low:.2f}")
        return {'levels': fib_levels, 'trend': trend, 'high': high, 'low': low}
        
    except Exception as e:
        logging.error(f"❌ Error calculando Fibonacci Retracement: {str(e)}")
        return {'levels': {}, 'trend': None, 'high': None, 'low': None}


def calculate_adaptive_rsi_macd(data, min_candles=25, column='close'):
    """
    Calcula RSI y MACD adaptando los períodos según la cantidad de datos disponibles
    
    Args:
        data: DataFrame con datos OHLCV
        min_candles: Mínimo de velas requeridas
        column: Columna para usar en el cálculo
        
    Returns:
        Diccionario con RSI y MACD adaptados
    """
    num_candles = len(data)
    result = {}
    
    # Si hay menos datos que el mínimo requerido
    if num_candles < min_candles:
        logging.warning(f"⚠️ Insuficientes datos para indicadores: {num_candles} < {min_candles}")
        return {
            'rsi': np.array([np.nan] * num_candles),
            'macd': np.array([np.nan] * num_candles),
            'signal': np.array([np.nan] * num_candles),
            'histogram': np.array([np.nan] * num_candles),
            'params': {'rsi_period': None, 'macd_fast': None, 'macd_slow': None, 'macd_signal': None}
        }
    
    # Ajuste adaptativo - si hay menos datos usar períodos más cortos
    if num_candles < 30:
        rsi_period = 10
        macd_fast = 8
        macd_slow = 17
        macd_signal = 9
    elif num_candles < 50:
        rsi_period = 12
        macd_fast = 10
        macd_slow = 22
        macd_signal = 9
    else:
        rsi_period = 14
        macd_fast = 12
        macd_slow = 26
        macd_signal = 9
    
    # Calcular RSI
    rsi = calculate_rsi(data, period=rsi_period, column=column)
    
    # Calcular MACD
    macd, signal, histogram = calculate_macd(
        data, 
        fast_period=macd_fast,
        slow_period=macd_slow,
        signal_period=macd_signal, 
        column=column
    )
    
    # Guardar todos los resultados
    result = {
        'rsi': rsi,
        'macd': macd,
        'signal': signal,
        'histogram': histogram,
        'params': {
            'rsi_period': rsi_period,
            'macd_fast': macd_fast,
            'macd_slow': macd_slow,
            'macd_signal': macd_signal
        }
    }
    
    return result
