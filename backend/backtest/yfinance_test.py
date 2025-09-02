"""
Тестовый скрипт для проверки загрузки данных из Yahoo Finance.
Запуск: python test_yfinance.py <тикер> <период>
Пример: python test_yfinance.py AAPL 1mo
"""

import sys
import yfinance as yf
import pandas as pd

def test_yfinance_data(ticker, period_value):
    """Тестирует загрузку данных из Yahoo Finance для указанного тикера и периода"""
    
    print(f"Тестирование загрузки данных для тикера: {ticker}, период: {period_value}")
    
    # Маппинг периодов
    period_mapping = {
        '1d': ('1d', '5m'),
        '5d': ('5d', '15m'),
        '1mo': ('1mo', '1d'),
        '1y': ('1y', '1d')
    }
    
    if period_value not in period_mapping:
        print(f"Неизвестный период: {period_value}. Использую '1mo' по умолчанию.")
        period, interval = '1mo', '1d'
    else:
        period, interval = period_mapping[period_value]
    
    print(f"Параметры yfinance: period={period}, interval={interval}")
    
    try:
        # Загрузка данных
        print("Загрузка данных...")
        data = yf.download(ticker, period=period, interval=interval, progress=True, auto_adjust=True)
        
        if data is None:
            print("Данные не получены (None)")
            return False
            
        if data.empty:
            print("Получен пустой DataFrame")
            return False
            
        print(f"Успешно загружено {len(data)} строк данных")
        print("\nИнформация о DataFrame:")
        print(data.info())
        
        print("\nПервые 5 строк:")
        print(data.head())
        
        print("\nПоследние 5 строк:")
        print(data.tail())
        
        print("\nКолонки DataFrame:")
        for i, col in enumerate(data.columns):
            print(f"{i}: {col} (тип: {type(col)})")
            
        # Проверка наличия необходимых колонок
        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        found_cols = []
        missing_cols = []
        
        for col in required_cols:
            if col in data.columns:
                found_cols.append(col)
            else:
                missing_cols.append(col)
                
        print(f"\nНайдены колонки: {found_cols}")
        print(f"Отсутствуют колонки: {missing_cols}")
        
        # Проверка MultiIndex
        if isinstance(data.columns, pd.MultiIndex):
            print("\nВНИМАНИЕ: Колонки представляют собой MultiIndex")
            print("Уровни MultiIndex:")
            for i, level in enumerate(data.columns.levels):
                print(f"Уровень {i}: {level}")
                
            print("Примеры значений колонок:")
            for i, col in enumerate(data.columns[:5]):
                print(f"Колонка {i}: {col} (тип: {type(col)})")
                
        return True
        
    except Exception as e:
        print(f"Ошибка при загрузке данных: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Параметры по умолчанию
    ticker = "AAPL"
    period = "1mo"
    
    # Чтение аргументов командной строки
    if len(sys.argv) > 1:
        ticker = sys.argv[1]
    if len(sys.argv) > 2:
        period = sys.argv[2]
    
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ YAHOO FINANCE DATA LOADING")
    print("=" * 60)
    
    success = test_yfinance_data(ticker, period)
    
    print("=" * 60)
    if success:
        print("ТЕСТ ЗАВЕРШЕН УСПЕШНО")
    else:
        print("ТЕСТ ЗАВЕРШЕН С ОШИБКАМИ")
    print("=" * 60)