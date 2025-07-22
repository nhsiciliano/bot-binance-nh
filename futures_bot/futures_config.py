from dataclasses import dataclass, field
from typing import List

@dataclass
class FuturesTradingConfig:
    """Configuration for the Futures Trading Bot."""
    # List of symbols to trade on the futures market
    symbols: List[str] = field(default_factory=lambda: ['BTCUSDT', 'ETHUSDT'])

    # Timeframe for the OHLCV data
    timeframe: str = '5m'

    # Leverage for futures trading
    leverage: int = 5

    # Bollinger Bands parameters
    bollinger_period: int = 20
    bollinger_std_dev: float = 2.0

    # Risk management parameters
    stop_loss_pct: float = 0.01  # 1% stop loss
    take_profit_pct: float = 0.015  # 1.5% take profit

    # The amount in USD for each trade (base size)
    trade_amount_usd: float = 20.0
