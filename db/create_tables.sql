-- Creación de tablas para monitoreo y registro de indicadores
-- Ejecutar este script en la consola SQL de Supabase

-- Tabla para almacenar indicadores técnicos
CREATE TABLE IF NOT EXISTS public.indicators (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    timeframe VARCHAR NOT NULL,
    close_price DECIMAL(20, 8) NOT NULL,
    -- Indicadores técnicos
    rsi DECIMAL(10, 4),
    macd DECIMAL(10, 4),
    macd_signal DECIMAL(10, 4),
    macd_hist DECIMAL(10, 4),
    ema_short DECIMAL(20, 8),
    ema_long DECIMAL(20, 8),
    bb_upper DECIMAL(20, 8),
    bb_middle DECIMAL(20, 8),
    bb_lower DECIMAL(20, 8),
    -- Señales de trading (interpretación de indicadores)
    rsi_signal VARCHAR,         -- "buy", "sell", "neutral"
    macd_signal_value VARCHAR,  -- "buy", "sell", "neutral"
    bb_signal VARCHAR,          -- "buy", "sell", "neutral"
    combined_signal VARCHAR,    -- "buy", "sell", "neutral"
    -- Metadatos
    parameters JSONB,           -- Parámetros usados para calcular indicadores
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Restricción: solo una entrada por símbolo, timestamp y timeframe
    UNIQUE(symbol, timestamp, timeframe)
);

-- Índices para búsquedas eficientes
CREATE INDEX IF NOT EXISTS idx_indicators_symbol_timeframe ON public.indicators(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_indicators_timestamp ON public.indicators(timestamp DESC);

-- Tabla para monitoreo de estado del bot
CREATE TABLE IF NOT EXISTS public.bot_status (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    instance_id VARCHAR NOT NULL,          -- ID de la instancia (ej: Cloud Run revision)
    host VARCHAR,                          -- Nombre del host donde se ejecuta
    status VARCHAR NOT NULL,               -- "starting", "running", "error", "stopped"
    last_heartbeat TIMESTAMPTZ NOT NULL,   -- Último latido
    error_message TEXT,                    -- Mensaje de error (si hay)
    memory_usage DECIMAL(10, 2),           -- Uso de memoria en MB
    cpu_usage DECIMAL(5, 2),               -- Uso de CPU en %
    active_since TIMESTAMPTZ,              -- Cuándo se inició
    version VARCHAR,                       -- Versión del bot
    environment VARCHAR,                   -- "production", "development", "testnet"
    metadata JSONB,                        -- Metadata adicional
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Restricción: una entrada por instance_id
    UNIQUE(instance_id)
);

-- Índices para la tabla bot_status
CREATE INDEX IF NOT EXISTS idx_bot_status_last_heartbeat ON public.bot_status(last_heartbeat DESC);

-- Trigger para actualizar updated_at automáticamente
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE 'plpgsql';

CREATE TRIGGER update_bot_status_updated_at
BEFORE UPDATE ON public.bot_status
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Comentarios para documentar las tablas
COMMENT ON TABLE public.indicators IS 'Registro de indicadores técnicos calculados por el bot de trading';
COMMENT ON TABLE public.bot_status IS 'Monitoreo del estado y salud del bot de trading';
