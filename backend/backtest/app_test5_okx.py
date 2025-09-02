# === file: app.py ===
import os
import logging
import requests
import json
import pandas as pd
from datetime import datetime, timedelta
from functools import lru_cache, wraps
from flask import Flask, jsonify, request
import dash
from dash import dcc, html, Input, Output, callback_context
import time
from threading import Lock
import asyncio

# ========== КОНФИГУРАЦИЯ ==========
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
HOST = os.environ.get('HOST', '127.0.0.1')
PORT = int(os.environ.get('PORT', 8050))
CACHE_TIMEOUT = int(os.environ.get('CACHE_TIMEOUT', 30))
REQUEST_TIMEOUT = int(os.environ.get('REQUEST_TIMEOUT', 10))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ ==========
server = Flask(__name__)
app = dash.Dash(
    __name__, 
    server=server, 
    external_scripts=[
        "https://unpkg.com/lightweight-charts@4.0.1/dist/lightweight-charts.standalone.production.js"
    ]
)

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
AVAILABLE_SYMBOLS = [
    {'label': 'BTC/USDT', 'value': 'BTC-USDT'},
    {'label': 'ETH/USDT', 'value': 'ETH-USDT'},
    {'label': 'OKB/USDT', 'value': 'OKB-USDT'},
    {'label': 'SOL/USDT', 'value': 'SOL-USDT'},
    {'label': 'DOT/USDT', 'value': 'DOT-USDT'},
    {'label': 'XRP/USDT', 'value': 'XRP-USDT'},
    {'label': 'ADA/USDT', 'value': 'ADA-USDT'},
    {'label': 'DOGE/USDT', 'value': 'DOGE-USDT'},
    {'label': 'LTC/USDT', 'value': 'LTC-USDT'},
    {'label': 'AVAX/USDT', 'value': 'AVAX-USDT'}
]

TIMEFRAME_MAP = {
    '1m': '1m', '5m': '5m', '15m': '15m',
    '1H': '1H', '4H': '4H', '1D': '1D'
}

# Кэш для исторических данных
historical_data_cache = {}
cache_lock = Lock()

# ========== ДЕКОРАТОРЫ И ХЕЛПЕРЫ ==========
def rate_limit(max_per_minute):
    """Декоратор для ограничения частоты запросов"""
    lock = Lock()
    last_called = [0.0]
    min_interval = 60.0 / max_per_minute

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with lock:
                elapsed = time.time() - last_called[0]
                left_to_wait = min_interval - elapsed
                if left_to_wait > 0:
                    time.sleep(left_to_wait)
                last_called[0] = time.time()
            return func(*args, **kwargs)
        return wrapper
    return decorator

def cache_response(timeout=CACHE_TIMEOUT):
    """Декоратор для кэширования ответов API"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            with cache_lock:
                if cache_key in historical_data_cache:
                    cached_data, timestamp = historical_data_cache[cache_key]
                    if time.time() - timestamp < timeout:
                        logger.info(f"Возвращаем кэшированные данные для {cache_key}")
                        return cached_data
            
            result = func(*args, **kwargs)
            
            with cache_lock:
                historical_data_cache[cache_key] = (result, time.time())
            
            return result
        return wrapper
    return decorator

# ========== API ROUTES ==========
@server.route('/api/historical-data/<symbol>/<timeframe>', methods=['GET'])
@rate_limit(30)
@cache_response(timeout=CACHE_TIMEOUT)
def get_historical_data(symbol, timeframe):
    """Получение исторических данных с кэшированием и ограничением частоты запросов"""
    logger.info(f"[API] Запрос historical-data: {symbol}, {timeframe}")
    
    try:
        # Валидация параметров
        if not any(s['value'] == symbol for s in AVAILABLE_SYMBOLS):
            return jsonify({'error': f'Символ {symbol} недоступен'}), 400
        
        okx_timeframe = TIMEFRAME_MAP.get(timeframe, '1H')
        if not okx_timeframe:
            return jsonify({'error': f'Таймфрейм {timeframe} не поддерживается'}), 400

        # Запрос к OKX API
        url = "https://www.okx.com/api/v5/market/history-candles"
        params = {
            'instId': symbol,
            'bar': okx_timeframe,
            'limit': 100
        }
        
        logger.info(f"[API] Запрос к OKX: {params}")
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if data.get('code') != '0':
            error_msg = data.get('msg', 'Unknown error from OKX API')
            logger.error(f"[API] OKX error: {error_msg}")
            return jsonify({'error': error_msg}), 502

        # Обработка данных
        ohlc_list = []
        volume_list = []
        
        for candle in data['data']:
            timestamp = int(candle[0]) // 1000
            open_price = float(candle[1])
            high_price = float(candle[2])
            low_price = float(candle[3])
            close_price = float(candle[4])
            vol = float(candle[5])

            ohlc_list.append({
                'time': timestamp,
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price
            })
            
            volume_list.append({
                'time': timestamp,
                'value': vol,
                'color': 'rgba(38, 166, 154, 0.5)' if close_price >= open_price else 'rgba(239, 83, 80, 0.5)'
            })

        # Реверс данных для правильного порядка
        ohlc_list.reverse()
        volume_list.reverse()

        logger.info(f"[API] Возвращено {len(ohlc_list)} свечей для {symbol}")
        return jsonify({'ohlc': ohlc_list, 'volume': volume_list})
        
    except requests.exceptions.Timeout:
        logger.error(f"[API] Timeout при запросе данных для {symbol}/{timeframe}")
        return jsonify({'error': 'Timeout при запросе к бирже'}), 504
    except requests.exceptions.RequestException as e:
        logger.error(f"[API] Ошибка запроса: {str(e)}")
        return jsonify({'error': 'Ошибка при запросе к бирже'}), 502
    except Exception as e:
        logger.exception(f"[API] Неожиданная ошибка: {str(e)}")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

@server.route('/api/health', methods=['GET'])
def health_check():
    """Эндпоинт для проверки здоровья сервиса"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

# ========== LAYOUT DASH ПРИЛОЖЕНИЯ ==========
app.layout = html.Div([
    html.Div(id='_dash-config', style={'display': 'none'}, 
             **{'data-requests-pathname-prefix': '/'}),
    
    html.H1("Real-time OKX Market Data", style={'textAlign': 'center', 'marginBottom': '20px'}),
    
    html.Div([
        html.Div([
            html.Label('Символ:', style={'marginRight': '10px'}),
            dcc.Dropdown(
                id='symbol-selector',
                options=AVAILABLE_SYMBOLS,
                value='BTC-USDT',
                clearable=False,
                style={'width': '150px', 'marginRight': '20px'}
            ),
        ], style={'display': 'flex', 'alignItems': 'center'}),
        
        html.Div([
            html.Label('Таймфрейм:', style={'marginRight': '10px'}),
            dcc.Dropdown(
                id='timeframe-selector',
                options=[
                    {'label': '1 минута', 'value': '1m'},
                    {'label': '5 минут', 'value': '5m'},
                    {'label': '15 минут', 'value': '15m'},
                    {'label': '1 час', 'value': '1H'},
                    {'label': '4 часа', 'value': '4H'},
                    {'label': '1 день', 'value': '1D'}
                ],
                value='1H',
                clearable=False,
                style={'width': '150px', 'marginRight': '20px'}
            ),
        ], style={'display': 'flex', 'alignItems': 'center'}),
        
        html.Button('Подключиться', id='connect-button', n_clicks=0, 
                   style={'marginRight': '10px', 'padding': '8px 16px'}),
        html.Button('Отключиться', id='disconnect-button', n_clicks=0,
                   style={'padding': '8px 16px'}),
    ], style={
        'display': 'flex', 
        'justifyContent': 'center', 
        'alignItems': 'center', 
        'marginBottom': '20px',
        'flexWrap': 'wrap',
        'gap': '15px'
    }),
    
    html.Div(id='custom-controls-container'),
    
    html.Div(id='status', style={
        'textAlign': 'center', 
        'fontWeight': 'bold', 
        'margin': '10px 0',
        'height': '25px'
    }),
    
    html.Div([
        html.Div(id='chart', style={'height': '500px', 'width': '100%'}),
        html.Div(id='volume-chart', style={'height': '200px', 'width': '100%', 'marginTop': '20px'}),
    ], style={'width': '100%', 'padding': '0 10px'}),
    
    dcc.Store(id='historical-data'),
    dcc.Store(id='ws-connection-status', data={'connected': False}),
    dcc.Interval(id='update-interval', interval=1000, disabled=True),
])

# ========== CALLBACKS ==========
@app.callback(
    Output('custom-controls-container', 'children'),
    Input('symbol-selector', 'value'),
    Input('timeframe-selector', 'value')
)
def update_custom_controls(symbol, timeframe):
    """Обновление кастомных контролов при изменении символа/таймфрейма"""
    return ""

@app.callback(
    [Output('status', 'children'),
     Output('historical-data', 'data'),
     Output('update-interval', 'disabled')],
    [Input('connect-button', 'n_clicks'),
     Input('disconnect-button', 'n_clicks'),
     Input('update-interval', 'n_intervals')],
    [Input('symbol-selector', 'value'),
     Input('timeframe-selector', 'value')]
)
def manage_connection(connect_clicks, disconnect_clicks, n_intervals, symbol, timeframe):
    """Управление подключением и обновлением данных"""
    ctx = callback_context
    if not ctx.triggered:
        return "Нажмите 'Подключиться' для начала", None, True
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == 'connect-button' and connect_clicks > 0:
        try:
            response = requests.get(
                f'http://{HOST}:{PORT}/api/historical-data/{symbol}/{timeframe}',
                timeout=REQUEST_TIMEOUT
            )
            data = response.json()
            
            if 'error' in data:
                return f"Ошибка: {data['error']}", None, True
            
            return f"Подключение к {symbol} ({timeframe})...", data, False
        except Exception as e:
            return f"Ошибка подключения: {str(e)}", None, True
    
    elif trigger_id == 'disconnect-button' and disconnect_clicks > 0:
        return "Отключено", None, True
    
    elif trigger_id == 'update-interval' and n_intervals > 0:
        # Периодическое обновление данных в реальном времени
        try:
            response = requests.get(
                f'http://{HOST}:{PORT}/api/historical-data/{symbol}/{timeframe}',
                timeout=REQUEST_TIMEOUT
            )
            data = response.json()
            
            if 'error' in data:
                return f"Ошибка: {data['error']}", None, True
            
            return f"Обновление данных {symbol} ({timeframe})...", data, False
        except Exception as e:
            return f"Ошибка обновления: {str(e)}", None, True
    
    return dash.no_update, dash.no_update, dash.no_update

# ========== ЗАПУСК СЕРВЕРА ==========
if __name__ == '__main__':
    logger.info(f"Запуск приложения на {HOST}:{PORT}, DEBUG={DEBUG}")
    app.run(debug=DEBUG, host=HOST, port=PORT, threaded=True)