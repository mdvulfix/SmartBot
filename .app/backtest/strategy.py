def simple_strategy(df):
    """
    Пример тестовой стратегии:
    Покупаем, если close > open (зелёная свеча),
    Продаём, если close < open (красная свеча).
    """
    trades = []
    for i, row in df.iterrows():
        if row['close'] > row['open']:
            trades.append({
                'timestamp': row['timestamp'],
                'price': row['close'],
                'side': 'buy'
            })
        elif row['close'] < row['open']:
            trades.append({
                'timestamp': row['timestamp'],
                'price': row['close'],
                'side': 'sell'
            })
    return trades

    

    
