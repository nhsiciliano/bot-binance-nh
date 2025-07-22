"""
Gestor de Supabase para registro y análisis de operaciones del bot de trading
"""

from supabase import create_client
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class SupabaseManager:
    """Maneja la conexión y operaciones con Supabase"""
    
    def __init__(self, supabase_url: str, supabase_key: str):
        """Inicializa la conexión con Supabase
        
        Args:
            supabase_url: URL de tu proyecto Supabase
            supabase_key: API Key de tu proyecto Supabase
        """
        self.supabase = create_client(supabase_url, supabase_key)
        self.initialize_tables()
        print("✅ Conexión con Supabase establecida")
    
    def initialize_tables(self):
        """Verifica que las tablas necesarias existan en Supabase
        
        Nota: Las tablas deben ser creadas manualmente en Supabase con la estructura adecuada
        """
        try:
            # Verificar si podemos acceder a las tablas (esto fallará si no existen)
            self.supabase.table("trades").select("id").limit(1).execute()
            self.supabase.table("positions").select("id").limit(1).execute()
            self.supabase.table("performance").select("id").limit(1).execute()
        except Exception as e:
            print(f"⚠️ Asegúrate de crear las tablas necesarias en Supabase: {e}")
            print("ℹ️ Consulta la documentación para la estructura de tablas requerida")
    
    def log_trade(self, trade_data: Dict) -> Dict:
        """Registra un trade en Supabase
        
        Args:
            trade_data: Datos del trade a registrar
            
        Returns:
            Respuesta de Supabase con el trade registrado
        """
        try:
            # Asegurarse de que timestamp sea un string ISO
            if isinstance(trade_data.get('timestamp'), datetime):
                trade_data['timestamp'] = trade_data['timestamp'].isoformat()
                
            response = self.supabase.table("trades").insert(trade_data).execute()
            return response.data[0] if response.data else {}
        except Exception as e:
            print(f"❌ Error al registrar trade en Supabase: {e}")
            return {}
    
    def update_position(self, position_id: int, position_data: Dict) -> Dict:
        """Actualiza una posición en Supabase
        
        Args:
            position_id: ID de la posición a actualizar
            position_data: Datos actualizados de la posición
            
        Returns:
            Respuesta de Supabase con la posición actualizada
        """
        try:
            response = self.supabase.table("positions").update(position_data).eq("id", position_id).execute()
            return response.data[0] if response.data else {}
        except Exception as e:
            print(f"❌ Error al actualizar posición en Supabase: {e}")
            return {}
    
    def close_position(self, position_id: int, close_data: Dict) -> Dict:
        """Cierra una posición en Supabase
        
        Args:
            position_id: ID de la posición a cerrar
            close_data: Datos del cierre de posición
            
        Returns:
            Respuesta de Supabase
        """
        try:
            # Actualizamos el estado de la posición a "closed" y agregamos datos de cierre
            response = self.supabase.table("positions").update(close_data).eq("id", position_id).execute()
            
            # Registramos también en la tabla de trades si hay profit/loss
            if 'pnl' in close_data:
                close_trade = {
                    'timestamp': datetime.now().isoformat(),
                    'symbol': close_data.get('symbol'),
                    'side': 'sell' if close_data.get('original_side') == 'buy' else 'buy',
                    'amount': close_data.get('amount'),
                    'price': close_data.get('close_price'),
                    'total': close_data.get('total'),
                    'pnl': close_data.get('pnl'),
                    'status': 'closed',
                    'notes': f"Cierre de posición #{position_id}: {close_data.get('reason', 'N/A')}"
                }
                self.log_trade(close_trade)
                
            return response.data[0] if response.data else {}
        except Exception as e:
            print(f"❌ Error al cerrar posición en Supabase: {e}")
            return {}
    
    def log_performance(self, performance_data: Dict) -> Dict:
        """Registra métricas de rendimiento diario
        
        Args:
            performance_data: Datos de rendimiento a registrar
            
        Returns:
            Respuesta de Supabase
        """
        try:
            import logging
            logging.info(f"Enviando datos de performance a Supabase: {performance_data}")
            
            # Asegura que todos los campos numéricos sean float o int
            for key, value in performance_data.items():
                if isinstance(value, (int, float)) and key != 'id':
                    if key in ['total_trades', 'winning_trades', 'losing_trades']:
                        performance_data[key] = int(value)
                    else:
                        performance_data[key] = float(value)
            
            response = self.supabase.table("performance").insert(performance_data).execute()
            return response.data[0] if response.data else {}
        except Exception as e:
            import logging
            logging.error(f"❌ Error al registrar performance en Supabase: {e}")
            logging.error(f"Datos enviados: {performance_data}")
            return {}
    
    def get_active_positions(self) -> List[Dict]:
        """Obtiene las posiciones activas desde Supabase
        
        Returns:
            Lista de posiciones activas
        """
        try:
            # No filtramos por status ya que esta columna no existe
            response = self.supabase.table("positions").select("*").execute()
            return response.data
        except Exception as e:
            import logging
            logging.error(f"❌ Error al obtener posiciones de Supabase: {e}")
            return []
    
    def update_performance_metrics(self) -> Dict:
        """Actualiza las métricas de rendimiento en Supabase
        
        Calcula y registra métricas de rendimiento diarias
        
        Returns:
            Datos de rendimiento registrados
        """
        try:
            today = datetime.now().date().isoformat()
            
            # Obtener datos del día actual si existen
            response = self.supabase.table("performance").select("*").eq("date", today).execute()
            
            # Obtener datos de trades del día
            today_start = f"{today}T00:00:00"
            today_end = f"{today}T23:59:59"
            
            trades = self.supabase.table("trades") \
                    .select("*") \
                    .gte("timestamp", today_start) \
                    .lte("timestamp", today_end) \
                    .execute()
            trades_data = trades.data if hasattr(trades, 'data') else []
            
            # Calcular métricas
            total_trades = len(trades_data)
            winning_trades = len([t for t in trades_data if t.get('pnl', 0) > 0])
            losing_trades = len([t for t in trades_data if t.get('pnl', 0) < 0])
            daily_pnl = sum(t.get('pnl', 0) for t in trades_data)
            
            # Obtener posiciones abiertas
            open_positions = self.get_active_positions()
            
            # Si no hay registro para hoy, crear uno nuevo
            if not response.data:
                performance_data = {
                    "date": today,
                    "total_trades": total_trades,
                    "winning_trades": winning_trades,
                    "losing_trades": losing_trades,
                    "daily_pnl": daily_pnl,
                    "total_balance": 1000.0  # Valor por defecto para total_balance (requerido)
                }
                
                result = self.log_performance(performance_data)
                return result
            else:
                # Actualizar registro existente
                existing = response.data[0]
                # Conservamos el balance anterior si existe, o asignamos un valor por defecto
                previous_balance = existing.get('total_balance', 1000.0)
                
                performance_data = {
                    "total_trades": total_trades,
                    "winning_trades": winning_trades,
                    "losing_trades": losing_trades,
                    "daily_pnl": daily_pnl,
                    "total_balance": previous_balance + daily_pnl  # Actualizamos el balance con el PnL diario
                }
                
                update_response = self.supabase.table("performance") \
                                .update(performance_data) \
                                .eq("id", existing.get('id')) \
                                .execute()
                                
                return update_response.data[0] if update_response.data else {}
                
        except Exception as e:
            print(f"❌ Error al actualizar métricas de rendimiento: {e}")
            return {"error": str(e)}
    
    def get_performance_stats(self, days: int = 30) -> Dict:
        """Obtiene estadísticas de rendimiento de los últimos días
        
        Args:
            days: Número de días para analizar
            
        Returns:
            Estadísticas de rendimiento
        """
        try:
            # Obtener datos de los últimos días
            from_date = (datetime.now() - timedelta(days=days)).date().isoformat()
            
            response = self.supabase.table("performance").select("*").gte("date", from_date).order("date").execute()
            
            if not response.data:
                return {"error": "No hay datos de rendimiento para el período especificado"}
                
            # Calcular métricas
            total_pnl = sum(day.get('daily_pnl', 0) for day in response.data)
            total_trades = sum(day.get('total_trades', 0) for day in response.data)
            winning_trades = sum(day.get('winning_trades', 0) for day in response.data)
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Calcular cambio en balance
            first_day = response.data[0]
            last_day = response.data[-1]
            starting_balance = first_day.get('total_balance', 0)
            ending_balance = last_day.get('total_balance', 0)
            
            return {
                "period_days": days,
                "total_pnl": total_pnl,
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "win_rate": win_rate,
                "starting_balance": starting_balance,
                "ending_balance": ending_balance,
                "return_pct": ((ending_balance / starting_balance) - 1) * 100 if starting_balance > 0 else 0
            }
            
        except Exception as e:
            print(f"❌ Error al obtener estadísticas de Supabase: {e}")
            return {"error": str(e)}
