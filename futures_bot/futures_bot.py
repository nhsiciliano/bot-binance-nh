import logging
import pandas as pd
from binance.client import Client
from futures_bot.futures_config import FuturesTradingConfig
from futures_bot.futures_indicators import calculate_bollinger_bands, get_bb_signal
from futures_bot.futures_utils import set_leverage_and_margin_type, create_futures_order

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class FuturesBot:
    def __init__(self, client: Client, config: FuturesTradingConfig):
        self.client = client
        self.config = config
        self._initialize_symbols()

    def _initialize_symbols(self):
        """Set up leverage and margin type for all symbols in the config."""
        logging.info("Initializing symbols for futures trading...")
        for symbol in self.config.symbols:
            set_leverage_and_margin_type(self.client, symbol, self.config.leverage)
        logging.info("Symbol initialization complete.")

    def _get_data_and_indicators(self, symbol: str) -> pd.DataFrame:
        """Fetch OHLCV data and calculate indicators."""
        klines = self.client.get_historical_klines(
            symbol,
            self.config.timeframe,
            limit=self.config.bollinger_period + 5 # Fetch enough data
        )
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
        df['close'] = pd.to_numeric(df['close'])
        df = calculate_bollinger_bands(df, self.config.bollinger_period, self.config.bollinger_std_dev)
        return df

    def _has_open_position(self, symbol: str) -> bool:
        """Check if there is an open position for the given symbol."""
        positions = self.client.futures_position_information(symbol=symbol)
        for position in positions:
            if float(position['positionAmt']) != 0:
                logging.info(f"Open position found for {symbol}: {position['positionAmt']}")
                return True
        return False

    def analyze_market(self):
        """Main method to analyze the market and trade."""
        logging.info("Starting futures market analysis cycle...")
        for symbol in self.config.symbols:
            try:
                if self._has_open_position(symbol):
                    logging.info(f"Skipping {symbol} as a position is already open.")
                    continue

                df = self._get_data_and_indicators(symbol)
                signal = get_bb_signal(df)
                latest_price = df.iloc[-1]['close']

                if signal == 'NEUTRAL':
                    logging.info(f"[{symbol}] No signal. Price: {latest_price}")
                    continue

                logging.warning(f"[{symbol}] Signal found: {signal} at price {latest_price}")

                # Calculate order details
                quantity = round(self.config.trade_amount_usd / latest_price, 3) # Basic quantity calculation
                
                if signal == 'LONG':
                    side = 'BUY'
                    stop_loss_price = latest_price * (1 - self.config.stop_loss_pct)
                    take_profit_price = latest_price * (1 + self.config.take_profit_pct)
                else: # SHORT
                    side = 'SELL'
                    stop_loss_price = latest_price * (1 + self.config.stop_loss_pct)
                    take_profit_price = latest_price * (1 - self.config.take_profit_pct)

                # Place orders
                create_futures_order(
                    self.client,
                    symbol,
                    side,
                    quantity,
                    round(stop_loss_price, 2),
                    round(take_profit_price, 2)
                )

            except Exception as e:
                logging.error(f"Error processing symbol {symbol}: {e}")

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
