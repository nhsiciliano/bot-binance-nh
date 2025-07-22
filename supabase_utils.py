"""
Módulo para interactuar con la base de datos Supabase
Provee utilidades para conectarse a Supabase y gestionar posiciones/trades
"""
import logging
from datetime import datetime
import json
import time
from typing import Dict, List, Optional, Any, Union
from supabase import create_client, Client
from cloud_config import SUPABASE_URL, SUPABASE_KEY

def get_connection() -> Client:
    """
    Crea y retorna una conexión al cliente Supabase
    
    Returns:
        Cliente de Supabase
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        logging.error("❌ URLs o keys de Supabase no configuradas")
        raise ValueError("URLs o keys de Supabase no configuradas")
    
    try:
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logging.info("✅ Conexión a Supabase establecida correctamente")
        return client
    except Exception as e:
        logging.error(f"❌ Error al conectar con Supabase: {str(e)}")
        raise

def create_position(
    client: Client, 
    symbol: str, 
    side: str, 
    entry_price: float,
    amount: float,
    timestamp: Optional[datetime] = None,
    metadata: Optional[Dict] = None
) -> Dict:
    """
    Crea una nueva posición en la tabla 'positions' de Supabase
    
    Args:
        client: Cliente de Supabase
        symbol: Par de trading (ej. 'BTC/USDT')
        side: Dirección ('buy' o 'sell')
        entry_price: Precio de entrada
        amount: Cantidad
        timestamp: Timestamp de la operación (por defecto usa now())
        metadata: Datos adicionales como JSON
        
    Returns:
        Datos de la posición creada
    """
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    else:
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()
    
    # Preparar los datos para la posición
    position_data = {
        "symbol": symbol,
        "side": side,
        "entry_price": entry_price,
        "amount": amount,
        "timestamp": timestamp,
        "pl": 0,  # P&L inicial en 0
        "exit_price": None,
        "closed_at": None,
        "metadata": json.dumps(metadata) if metadata else None
    }
    
    try:
        # Insertar la posición
        response = client.table('positions').insert(position_data).execute()
        
        if hasattr(response, 'error') and response.error:
            logging.error(f"❌ Error al crear posición en Supabase: {response.error}")
            return {}
        
        created_position = response.data[0] if response.data else {}
        position_id = created_position.get('id')
        
        if position_id:
            logging.info(f"✅ Posición creada con ID: {position_id}")
        else:
            logging.warning("⚠️ Posición creada pero no se pudo obtener el ID")
        
        return created_position
        
    except Exception as e:
        logging.error(f"❌ Excepción al crear posición en Supabase: {str(e)}")
        return {}

def update_position_pl(
    client: Client, 
    position_id: int, 
    current_price: float, 
    close_position: bool = False,
    metadata: Optional[Dict] = None
) -> Dict:
    """
    Actualiza el P&L de una posición existente y opcionalmente la cierra
    
    Args:
        client: Cliente de Supabase
        position_id: ID de la posición a actualizar
        current_price: Precio actual para calcular P&L
        close_position: Si es True, marca la posición como cerrada
        metadata: Datos adicionales a actualizar como JSON
        
    Returns:
        Datos de la posición actualizada
    """
    try:
        # Primero obtenemos la posición actual
        response = client.table('positions').select('*').eq('id', position_id).execute()
        
        if hasattr(response, 'error') and response.error:
            logging.error(f"❌ Error al obtener posición {position_id}: {response.error}")
            return {}
            
        if not response.data:
            logging.error(f"❌ No se encontró la posición con ID {position_id}")
            return {}
            
        position = response.data[0]
        
        # Calcular P&L
        entry_price = position.get('entry_price', 0)
        amount = position.get('amount', 0)
        side = position.get('side', '')
        
        # Cálculo básico de P&L
        if side.lower() == 'buy':
            pl = (current_price - entry_price) * amount
        else:
            pl = (entry_price - current_price) * amount
            
        update_data = {
            "pl": pl
        }
        
        # Si estamos cerrando la posición
        if close_position:
            update_data.update({
                "exit_price": current_price,
                "closed_at": datetime.now().isoformat()
            })
            
        # Actualizar metadatos si es necesario
        if metadata:
            existing_metadata = json.loads(position.get('metadata') or '{}')
            existing_metadata.update(metadata)
            update_data["metadata"] = json.dumps(existing_metadata)
            
        # Actualizar en la base de datos
        response = client.table('positions').update(update_data).eq('id', position_id).execute()
        
        if hasattr(response, 'error') and response.error:
            logging.error(f"❌ Error al actualizar posición {position_id}: {response.error}")
            return {}
            
        updated_position = response.data[0] if response.data else {}
        
        action_type = "cerrada" if close_position else "actualizada"
        logging.info(f"✅ Posición {position_id} {action_type} - P&L: {pl}")
        
        return updated_position
        
    except Exception as e:
        logging.error(f"❌ Excepción al actualizar posición {position_id}: {str(e)}")
        return {}
