from dataclasses import dataclass, field
from typing import List

@dataclass
class FuturesTradingConfig:
    """Configuration for the Futures Trading Bot - Multi-Indicator Strategy."""
    # Exchange settings
    exchange_id: str = 'binance'
    symbols: List[str] = field(default_factory=lambda: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT'])
    timeframe: str = '5m'  # Timeframe base para la estrategia (scalping)

    # Leverage for futures trading
    leverage: int = 5

    # --- Parámetros de Estrategia Multi-Indicador ---
    
    # Filtro de Tendencia (EMA)
    ema_long_period: int = 200  # EMA de 200 para filtrar tendencia principal

    # Indicador de Momento/Entrada (RSI)
    rsi_period: int = 14
    rsi_oversold: int = 30  # Nivel de sobreventa
    rsi_overbought: int = 70 # Nivel de sobrecompra

    # Indicador de Momento/Confirmación (MACD)
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # Bollinger Bands (Soporte/Resistencia)
    bollinger_period: int = 20
    bollinger_std_dev: float = 2.0

    # --- Parámetros de Gestión de Riesgo ---
    stop_loss_pct: float = 0.015  # 1.5% stop loss
    take_profit_pct: float = 0.025  # 2.5% take profit
    trailing_stop_pct: float = 0.01  # 1% trailing stop
    max_position_size: float = 25.0  # $25 por posición
    max_positions: int = 6  # Máximo 6 posiciones totales
    max_positions_per_symbol: int = 2  # Máximo 2 posiciones por símbolo

    # The amount in USD for each trade (base size)
    trade_amount_usd: float = 25.0

    # --- Configuración Adicional ---
    trading_start_hour: int = 0
    trading_end_hour: int = 23
    email_notifications: bool = True
    telegram_notifications: bool = False
