import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def set_leverage_and_margin_type(client: Client, symbol: str, leverage: int):
    """
    Sets the leverage and margin type for a given symbol.

    Args:
        client: The Binance API client.
        symbol: The trading symbol (e.g., 'BTCUSDT').
        leverage: The desired leverage.
    """
    try:
        logging.info(f"Setting leverage for {symbol} to {leverage}x")
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
    except BinanceAPIException as e:
        if e.code == -4046: # "No need to change leverage"
            logging.info(f"Leverage for {symbol} is already set to {leverage}x.")
        else:
            logging.error(f"Error setting leverage for {symbol}: {e}")
            raise

    try:
        logging.info(f"Setting margin type for {symbol} to ISOLATED")
        client.futures_change_margin_type(symbol=symbol, marginType='ISOLATED')
    except BinanceAPIException as e:
        if e.code == -4046: # "No need to change margin type"
            logging.info(f"Margin type for {symbol} is already ISOLATED.")
        else:
            logging.error(f"Error setting margin type for {symbol}: {e}")
            raise

def create_futures_order(client: Client, symbol: str, side: str, quantity: float, stop_loss_price: float, take_profit_price: float):
    """
    Creates a market order and accompanying SL/TP orders.

    Args:
        client: The Binance API client.
        symbol: The trading symbol.
        side: 'BUY' (for LONG) or 'SELL' (for SHORT).
        quantity: The amount of the asset to trade.
        stop_loss_price: The price at which to trigger the stop loss.
        take_profit_price: The price at which to trigger the take profit.
    """
    position_side = 'LONG' if side == 'BUY' else 'SHORT'
    close_side = 'SELL' if side == 'BUY' else 'BUY'

    try:
        # 1. Create the initial market order to open the position
        logging.info(f"Placing {position_side} market order for {quantity} {symbol}")
        market_order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type='MARKET',
            quantity=quantity
        )
        logging.info(f"Market order placed: {market_order['orderId']}")

        # 2. Create the Stop-Loss order
        logging.info(f"Placing STOP_MARKET (SL) order for {symbol} at {stop_loss_price}")
        sl_order = client.futures_create_order(
            symbol=symbol,
            side=close_side, # Opposite side to close
            type='STOP_MARKET',
            stopPrice=stop_loss_price,
            closePosition=True # Ensures it closes the position
        )
        logging.info(f"Stop-Loss order placed: {sl_order['orderId']}")

        # 3. Create the Take-Profit order
        logging.info(f"Placing TAKE_PROFIT_MARKET (TP) order for {symbol} at {take_profit_price}")
        tp_order = client.futures_create_order(
            symbol=symbol,
            side=close_side, # Opposite side to close
            type='TAKE_PROFIT_MARKET',
            stopPrice=take_profit_price,
            closePosition=True # Ensures it closes the position
        )
        logging.info(f"Take-Profit order placed: {tp_order['orderId']}")

        return market_order, sl_order, tp_order

    except BinanceAPIException as e:
        logging.error(f"An error occurred while creating orders for {symbol}: {e}")
        # Attempt to cancel any open orders for this symbol to prevent dangling orders
        try:
            client.futures_cancel_all_open_orders(symbol=symbol)
            logging.warning(f"All open orders for {symbol} cancelled due to an error during order placement.")
        except BinanceAPIException as cancel_e:
            logging.error(f"Could not cancel open orders for {symbol} after an error: {cancel_e}")
        return None, None, None
