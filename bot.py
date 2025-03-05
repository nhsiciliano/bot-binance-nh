from binance.client import Client
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import os
import requests

# Cargar variables de entorno desde el archivo .env
load_dotenv()


# Obtener configuración de las variables de entorno
use_testnet = os.getenv('USE_TESTNET') == 'True'
if use_testnet:
    api_key = os.getenv('TESTNET_API_KEY')
    api_secret = os.getenv('TESTNET_API_SECRET')
else:
    api_key = os.getenv('REAL_API_KEY')
    api_secret = os.getenv('REAL_API_SECRET')

# Crear cliente de Binance
client = Client(api_key, api_secret, testnet=use_testnet)

# Función para obtener datos históricos
def get_historical_data(symbol, interval, lookback):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=lookback)
    data = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    data['close'] = data['close'].astype(float)
    return data

# Calcular RSI
def calculate_rsi(data, period=14):
    delta = data['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# Calcular Bandas de Bollinger
def calculate_bollinger_bands(data, window=20):
    sma = data['close'].rolling(window=window).mean()
    std = data['close'].rolling(window=window).std()
    upper_band = sma + (std * 2)
    lower_band = sma - (std * 2)
    return upper_band, lower_band

# Calcular MACD
def calculate_macd(data, short_window=12, long_window=26, signal_window=9):
    short_ema = data['close'].ewm(span=short_window, adjust=False).mean()
    long_ema = data['close'].ewm(span=long_window, adjust=False).mean()
    macd = short_ema - long_ema
    signal = macd.ewm(span=signal_window, adjust=False).mean()
    return macd, signal

# Calcular EMA
def calculate_ema(data, window=20):
    ema = data['close'].ewm(span=window, adjust=False).mean()
    return ema

# Configuración de Telegram
telegram_token = os.getenv('TELEGRAM_TOKEN')
chat_id = os.getenv('TELEGRAM_CHAT_ID')

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message
    }
    requests.post(url, data=payload)

# Diccionario para rastrear posiciones
positions = {}

def update_position(symbol, action, price):
    if action == "Comprar":
        positions[symbol] = price
    elif action == "Vender" and symbol in positions:
        entry_price = positions.pop(symbol)
        profit_loss = price - entry_price
        send_telegram_message(f"{action} {symbol} - Precio de entrada: {entry_price}, Precio de salida: {price}, Ganancia/Pérdida: {profit_loss}")


# Lista de pares de criptomonedas a monitorear
symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT']

def calculate_stop_loss_take_profit(entry_price, volatility):
    stop_loss = entry_price * (1 - volatility)
    take_profit = entry_price * (1 + volatility)
    return stop_loss, take_profit

# Estrategia de Trading
def trading_strategy(symbol):
    data = get_historical_data(symbol, '1h', 100)
    data['rsi'] = calculate_rsi(data)
    data['upper_band'], data['lower_band'] = calculate_bollinger_bands(data)
    data['macd'], data['signal'] = calculate_macd(data)
    data['ema'] = calculate_ema(data)

    current_price = data['close'].iloc[-1]
    volatility = (data['upper_band'].iloc[-1] - data['lower_band'].iloc[-1]) / data['close'].iloc[-1]
    stop_loss, take_profit = calculate_stop_loss_take_profit(current_price, volatility)

    # Mostrar valores de los indicadores para depuración
    print(f"\nAnálisis para {symbol}:")
    print(f"RSI: {data['rsi'].iloc[-1]}")
    print(f"Upper Band: {data['upper_band'].iloc[-1]}, Lower Band: {data['lower_band'].iloc[-1]}")
    print(f"MACD: {data['macd'].iloc[-1]}, Signal: {data['signal'].iloc[-1]}")
    print(f"EMA: {data['ema'].iloc[-1]}")

    # Lógica de compra/venta
    if (data['rsi'].iloc[-1] < 25 and current_price < data['lower_band'].iloc[-1]) or (data['macd'].iloc[-1] > data['signal'].iloc[-1] and current_price > data['ema'].iloc[-1]):
        operation = f"Comprar {symbol}"
        print(operation)
        send_telegram_message(f"{operation} - RSI: {data['rsi'].iloc[-1]}, Precio: {current_price}, Stop-Loss: {stop_loss}, Take-Profit: {take_profit}")
        update_position(symbol, "Comprar", current_price)
    elif (data['rsi'].iloc[-1] > 75 and current_price > data['upper_band'].iloc[-1]) or (data['macd'].iloc[-1] < data['signal'].iloc[-1] and current_price < data['ema'].iloc[-1]):
        operation = f"Vender {symbol}"
        print(operation)
        send_telegram_message(f"{operation} - RSI: {data['rsi'].iloc[-1]}, Precio: {current_price}, Stop-Loss: {stop_loss}, Take-Profit: {take_profit}")
        update_position(symbol, "Vender", current_price)

# Ejecutar estrategia para cada par
for symbol in symbols:
    trading_strategy(symbol)

# Verificar conexión
account_info = client.get_account()
print(account_info)