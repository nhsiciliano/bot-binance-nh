import pandas as pd

def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> pd.DataFrame:
    """
    Calculates Bollinger Bands and adds them to the DataFrame.

    Args:
        df: DataFrame with at least a 'close' column.
        period: The period for the moving average.
        std_dev: The number of standard deviations for the bands.

    Returns:
        DataFrame with 'bb_upper', 'bb_middle', 'bb_lower' columns.
    """
    df['bb_middle'] = df['close'].rolling(window=period).mean()
    df['bb_std'] = df['close'].rolling(window=period).std()
    df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * std_dev)
    df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * std_dev)
    return df

def get_bb_signal(df: pd.DataFrame) -> str:
    """
    Determines the trading signal based on the latest Bollinger Bands values.

    Args:
        df: DataFrame with Bollinger Bands columns.

    Returns:
        'LONG', 'SHORT', or 'NEUTRAL'.
    """
    latest = df.iloc[-1]
    
    if pd.isna(latest['bb_upper']) or pd.isna(latest['bb_lower']):
        return 'NEUTRAL' # Not enough data to compute bands

    if latest['close'] <= latest['bb_lower']:
        return 'LONG'
    elif latest['close'] >= latest['bb_upper']:
        return 'SHORT'
    else:
        return 'NEUTRAL'
