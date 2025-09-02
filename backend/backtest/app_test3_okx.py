# === file: app.py ===

import dash
from dash import dcc, html, Input, Output
import json
import pandas as pd
import requests
from flask import Flask, jsonify
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация Dash
server = Flask(__name__)
app = dash.Dash(__name__, server=server, external_scripts=[
    "https://unpkg.com/lightweight-charts@4.0.1/dist/lightweight-charts.standalone.production.js"
])

# Список доступных символов на OKX
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

app.layout = html.Div([
    html.H1("Real-time OKX Market Data"),
    
    # Выбор символа и таймфрейма
    html.Div([
        html.Label('Выберите символ:'),
        dcc.Dropdown(
            id='symbol-selector',
            options=AVAILABLE_SYMBOLS,
            value='BTC-USDT',
            style={'width': '200px', 'margin': '10px'}
        ),
        
        html.Label('Таймфрейм:'),
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
            style={'width': '200px', 'margin': '10px'}
        ),
        
        html.Button('Подключиться', id='connect-button', n_clicks=0),
        html.Button('Отключиться', id='disconnect-button', n_clicks=0),
    ], style={'display': 'flex', 'alignItems': 'center', 'margin': '10px'}),
    
    # Статус подключения
    html.Div(id='status', style={'margin': '10px', 'fontWeight': 'bold'}),
    
    # Контейнеры для графиков
    html.Div([
        html.Div(id='chart', style={'height': '500px', 'width': '100%'}),
        html.Div(id='volume-chart', style={'height': '150px', 'width': '100%', 'marginTop': '20px'}),
    ]),
    
    # Скрытые элементы для хранения данных
    dcc.Store(id='historical-data'),
    dcc.Store(id='ws-connection-status', data={'connected': False}),
])

# API endpoint для получения исторических данных
@server.route('/api/historical-data/<symbol>/<timeframe>')
def get_historical_data(symbol, timeframe):
    try:
        # Проверяем, доступен ли символ
        if not any(s['value'] == symbol for s in AVAILABLE_SYMBOLS):
            return jsonify({'error': f'Символ {symbol} недоступен'})
        
        # Преобразуем таймфрейм к формату, который понимает OKX API
        timeframe_map = {
            '1m': '1m', '5m': '5m', '15m': '15m',
            '1H': '1H', '4H': '4H', '1D': '1D'
        }
        
        okx_timeframe = timeframe_map.get(timeframe, '1H')
        
        url = "https://www.okx.com/api/v5/market/history-candles"
        params = {
            'instId': symbol,
            'bar': okx_timeframe,
            'limit': 100
        }
        
        logger.info(f"Запрос исторических данных: {params}")
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data['code'] != '0':
            error_msg = data.get('msg', 'Unknown error from OKX API')
            logger.error(f"Ошибка OKX API: {error_msg}")
            return jsonify({'error': error_msg})
        
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
                'color': 'rgba(38, 166, 154, 0.5)' if close_price > open_price else 'rgba(239, 83, 80, 0.5)'
            })
        
        ohlc_list.reverse()
        volume_list.reverse()
        
        logger.info(f"Успешно получено {len(ohlc_list)} свечей для {symbol}")
        return jsonify({'ohlc': ohlc_list, 'volume': volume_list})
        
    except Exception as e:
        logger.error(f"Ошибка при получении исторических данных: {str(e)}")
        return jsonify({'error': str(e)})

# Callback для управления подключением
@app.callback(
    [Output('status', 'children'),
     Output('historical-data', 'data'),
     Output('ws-connection-status', 'data')],
    [Input('connect-button', 'n_clicks'),
     Input('disconnect-button', 'n_clicks')],
    [dash.dependencies.State('symbol-selector', 'value'),
     dash.dependencies.State('timeframe-selector', 'value'),
     dash.dependencies.State('ws-connection-status', 'data')]
)
def manage_connection(connect_clicks, disconnect_clicks, symbol, timeframe, ws_status):
    ctx = dash.callback_context
    if not ctx.triggered:
        return "Нажмите 'Подключиться' для начала", dash.no_update, dash.no_update
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == 'connect-button' and connect_clicks > 0:
        if not ws_status.get('connected', False):
            try:
                response = requests.get(f'http://localhost:8050/api/historical-data/{symbol}/{timeframe}', timeout=10)
                data = response.json()
                
                if 'error' in data:
                    return f"Ошибка: {data['error']}", dash.no_update, dash.no_update
                
                return f"Подключение к {symbol} ({timeframe})...", data, {'connected': True, 'symbol': symbol, 'timeframe': timeframe}
            except Exception as e:
                return f"Ошибка подключения: {str(e)}", dash.no_update, dash.no_update
    
    elif trigger_id == 'disconnect-button' and disconnect_clicks > 0:
        return "Отключено", dash.no_update, {'connected': False}
    
    return dash.no_update, dash.no_update, dash.no_update

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=8050)