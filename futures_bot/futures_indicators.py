import pandas as pd
import numpy as np
from typing import Tuple, Dict, Any

def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Calcula el RSI (Relative Strength Index) nativo
    """
    close = df['close']
    delta = close.diff()
    
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    df['rsi'] = rsi
    return df

def calculate_ema(df: pd.DataFrame, period: int, column: str = 'close') -> pd.Series:
    """
    Calcula EMA (Exponential Moving Average) nativo
    """
    return df[column].ewm(span=period, adjust=False).mean()

def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    Calcula MACD nativo
    """
    ema_fast = calculate_ema(df, fast)
    ema_slow = calculate_ema(df, slow)
    
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    
    df['macd'] = macd_line
    df['macd_signal'] = signal_line
    df['macd_histogram'] = histogram
    
    return df

def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> pd.DataFrame:
    """
    Calcula Bollinger Bands
    """
    df['bb_middle'] = df['close'].rolling(window=period).mean()
    df['bb_std'] = df['close'].rolling(window=period).std()
    df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * std_dev)
    df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * std_dev)
    return df

def calculate_all_indicators(df: pd.DataFrame, config) -> pd.DataFrame:
    """
    Calcula todos los indicadores técnicos para la estrategia multi-indicador
    """
    # RSI
    df = calculate_rsi(df, config.rsi_period)
    
    # MACD
    df = calculate_macd(df, config.macd_fast, config.macd_slow, config.macd_signal)
    
    # EMA de tendencia
    df['ema_long'] = calculate_ema(df, config.ema_long_period)
    
    # Bollinger Bands
    df = calculate_bollinger_bands(df, config.bollinger_period, config.bollinger_std_dev)
    
    return df

def get_trading_signal(df: pd.DataFrame, config) -> Tuple[str, Dict[str, Any]]:
    """
    Determina la señal de trading basada en la estrategia multi-indicador
    
    Estrategia:
    - EMA 200: Filtro de tendencia (precio > EMA = alcista, precio < EMA = bajista)
    - RSI: Momentum (< 30 = sobreventa, > 70 = sobrecompra)
    - MACD: Confirmación de tendencia (cruce de líneas)
    - Bollinger Bands: Soporte/resistencia
    
    Returns:
        Tuple[str, Dict]: (señal, detalles de indicadores)
    """
    if len(df) < config.ema_long_period:
        return 'NEUTRAL', {'reason': 'Datos insuficientes'}
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Verificar que todos los indicadores estén disponibles
    required_cols = ['rsi', 'macd', 'macd_signal', 'ema_long', 'bb_upper', 'bb_lower']
    if any(pd.isna(latest[col]) for col in required_cols):
        return 'NEUTRAL', {'reason': 'Indicadores no disponibles'}
    
    # Obtener valores de indicadores
    price = latest['close']
    rsi = latest['rsi']
    macd = latest['macd']
    macd_signal = latest['macd_signal']
    macd_prev = prev['macd']
    macd_signal_prev = prev['macd_signal']
    ema_long = latest['ema_long']
    bb_upper = latest['bb_upper']
    bb_lower = latest['bb_lower']
    
    # Detalles para logging
    details = {
        'price': price,
        'rsi': rsi,
        'macd': macd,
        'macd_signal': macd_signal,
        'ema_long': ema_long,
        'bb_upper': bb_upper,
        'bb_lower': bb_lower
    }
    
    # --- LÓGICA DE SEÑALES ---
    
    # 1. Filtro de tendencia con EMA 200
    trend_bullish = price > ema_long
    trend_bearish = price < ema_long
    
    # 2. Señales de RSI
    rsi_oversold = rsi < config.rsi_oversold
    rsi_overbought = rsi > config.rsi_overbought
    
    # 3. Señales de MACD (cruce)
    macd_bullish_cross = (macd > macd_signal) and (macd_prev <= macd_signal_prev)
    macd_bearish_cross = (macd < macd_signal) and (macd_prev >= macd_signal_prev)
    
    # 4. Señales de Bollinger Bands
    bb_oversold = price <= bb_lower
    bb_overbought = price >= bb_upper
    
    # --- SEÑALES LONG (COMPRA) ---
    long_conditions = [
        trend_bullish,  # Tendencia alcista
        rsi_oversold or bb_oversold,  # RSI sobreventa O precio en banda inferior
        macd_bullish_cross or macd > macd_signal  # MACD alcista
    ]
    
    # --- SEÑALES SHORT (VENTA) ---
    short_conditions = [
        trend_bearish,  # Tendencia bajista
        rsi_overbought or bb_overbought,  # RSI sobrecompra O precio en banda superior
        macd_bearish_cross or macd < macd_signal  # MACD bajista
    ]
    
    # Determinar señal final
    if sum(long_conditions) >= 2:  # Al menos 2 condiciones alcistas
        details['signal_reason'] = f"LONG: Tendencia={trend_bullish}, RSI/BB={rsi_oversold or bb_oversold}, MACD={macd_bullish_cross or macd > macd_signal}"
        return 'LONG', details
    elif sum(short_conditions) >= 2:  # Al menos 2 condiciones bajistas
        details['signal_reason'] = f"SHORT: Tendencia={trend_bearish}, RSI/BB={rsi_overbought or bb_overbought}, MACD={macd_bearish_cross or macd < macd_signal}"
        return 'SHORT', details
    else:
        details['signal_reason'] = "NEUTRAL: Condiciones insuficientes para señal"
        return 'NEUTRAL', details

# Función de compatibilidad para el código existente
def get_bb_signal(df: pd.DataFrame) -> str:
    """
    Función de compatibilidad - usar get_trading_signal en su lugar
    """
    latest = df.iloc[-1]
    
    if pd.isna(latest.get('bb_upper')) or pd.isna(latest.get('bb_lower')):
        return 'NEUTRAL'

    if latest['close'] <= latest['bb_lower']:
        return 'LONG'
    elif latest['close'] >= latest['bb_upper']:
        return 'SHORT'
    else:
        return 'NEUTRAL'
