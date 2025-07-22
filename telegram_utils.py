"""
Módulo para enviar mensajes a Telegram
Utiliza las credenciales del bot de Telegram para enviar notificaciones
"""
import logging
import requests
import os
import datetime
import json
from cloud_config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def _send_telegram_message(message, token=None, chat_id=None):
    """
    Función interna para enviar mensajes a Telegram
    """
    if not token:
        token = TELEGRAM_TOKEN
    
    if not chat_id:
        chat_id = TELEGRAM_CHAT_ID
    
    # Si no hay token o chat_id, solo logueamos el mensaje
    if not token or not chat_id:
        logging.warning("⚠️ No se pudo enviar mensaje a Telegram: credenciales no configuradas")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            return True
        else:
            logging.error(f"❌ Error al enviar mensaje a Telegram: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logging.error(f"❌ Excepción al enviar mensaje a Telegram: {str(e)}")
        return False

def send_message(message):
    """
    Envía un mensaje informativo a Telegram
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"<b>[INFO {timestamp}]</b>\n{message}"
    
    return _send_telegram_message(formatted_message)

def send_error_message(message):
    """
    Envía un mensaje de error a Telegram
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"<b>[ERROR {timestamp}]</b>\n❌ {message}"
    
    return _send_telegram_message(formatted_message)

def send_trade_notification(trade_data):
    """
    Envía una notificación de trade a Telegram
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if isinstance(trade_data, dict):
        try:
            symbol = trade_data.get("symbol", "Desconocido")
            side = trade_data.get("side", "Desconocido")
            price = trade_data.get("price", 0)
            amount = trade_data.get("amount", 0)
            cost = trade_data.get("cost", 0)
            
            emoji = "🟢" if side.lower() == "buy" else "🔴"
            
            message = f"""<b>[TRADE {timestamp}]</b>
{emoji} <b>{side.upper()} {symbol}</b>
📊 Precio: {price}
📈 Cantidad: {amount}
💰 Total: {cost}"""
            
            return _send_telegram_message(message)
        except Exception as e:
            logging.error(f"Error formateando datos de trade: {e}")
            return _send_telegram_message(f"<b>[TRADE {timestamp}]</b>\n{json.dumps(trade_data, indent=2)}")
    else:
        return _send_telegram_message(f"<b>[TRADE {timestamp}]</b>\n{str(trade_data)}")
