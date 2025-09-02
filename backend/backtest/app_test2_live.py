"""
Версия с реальными данными из Binance API
"""

import dash
from dash import dcc, html, Input, Output
import json
from datetime import datetime, timedelta
import requests
import pandas as pd

# Инициализация Dash
app = dash.Dash(__name__, external_scripts=[
    "https://unpkg.com/lightweight-charts@4.0.1/dist/lightweight-charts.standalone.production.js"
])

app.layout = html.Div([
    html.H1("График с реальными данными Binance"),
    
    # Выбор символа и интервала
    html.Div([
        html.Label('Выберите символ:'),
        dcc.Dropdown(
            id='symbol-selector',
            options=[
                {'label': 'BTC/USDT', 'value': 'BTCUSDT'},
                {'label': 'ETH/USDT', 'value': 'ETHUSDT'},
                {'label': 'BNB/USDT', 'value': 'BNBUSDT'},
                {'label': 'ADA/USDT', 'value': 'ADAUSDT'},
                {'label': 'DOT/USDT', 'value': 'DOTUSDT'}
            ],
            value='BTCUSDT',
            style={'width': '200px', 'margin': '10px'}
        ),
        
        html.Label('Выберите интервал:'),
        dcc.Dropdown(
            id='interval-selector',
            options=[
                {'label': '1 минута', 'value': '1m'},
                {'label': '5 минут', 'value': '5m'},
                {'label': '15 минут', 'value': '15m'},
                {'label': '1 час', 'value': '1h'},
                {'label': '4 часа', 'value': '4h'},
                {'label': '1 день', 'value': '1d'}
            ],
            value='1h',
            style={'width': '200px', 'margin': '10px'}
        ),
        
        html.Button('Загрузить данные', id='load-data-button', n_clicks=0),
    ], style={'display': 'flex', 'alignItems': 'center', 'margin': '10px'}),
    
    # Статус загрузки
    html.Div(id='status', style={'margin': '10px'}),
    
    # Контейнеры для графиков
    html.Div(id='chart-container', children=[
        html.Div(id='chart', style={'height': '500px', 'width': '100%'}),
        html.Div(id='volume-chart', style={'height': '150px', 'width': '100%', 'marginTop': '20px'}),
    ]),
    
    # Интервал для обновления данных
    dcc.Interval(
        id='interval-component',
        interval=30000,  # 30 секунд
        n_intervals=0,
        disabled=True
    ),
    
    # Хранилище для данных
    dcc.Store(id='data-store'),
])

# Функция для получения данных с Binance
def get_binance_data(symbol, interval, limit=100):
    try:
        # Формируем URL для запроса
        url = f"https://api.binance.com/api/v3/klines"
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        
        # Выполняем запрос
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Преобразуем данные в нужный формат
        ohlc_data = []
        volume_data = []
        
        for candle in data:
            timestamp = candle[0] // 1000  # Конвертируем из мс в секунды
            ohlc_data.append({
                'time': timestamp,
                'open': float(candle[1]),
                'high': float(candle[2]),
                'low': float(candle[3]),
                'close': float(candle[4])
            })
            volume_data.append({
                'time': timestamp,
                'value': float(candle[5]),
                'color': 'green' if float(candle[4]) > float(candle[1]) else 'red'
            })
        
        return json.dumps(ohlc_data), json.dumps(volume_data)
    
    except Exception as e:
        print(f"Ошибка при получении данных: {e}")
        return None, None

@app.callback(
    [Output('data-store', 'data'),
     Output('status', 'children'),
     Output('interval-component', 'disabled')],
    [Input('load-data-button', 'n_clicks'),
     Input('interval-component', 'n_intervals')],
    [dash.dependencies.State('symbol-selector', 'value'),
     dash.dependencies.State('interval-selector', 'value')]
)
def update_data(load_clicks, n_intervals, symbol, interval):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, "Выберите символ и интервал, затем нажмите 'Загрузить данные'", True
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == 'load-data-button' and load_clicks > 0:
        # Загружаем данные при нажатии кнопки
        ohlc_json, volume_json = get_binance_data(symbol, interval)
        if ohlc_json and volume_json:
            return {'ohlc': ohlc_json, 'volume': volume_json}, f"Данные для {symbol} ({interval}) загружены", False
        else:
            return dash.no_update, "Ошибка при загрузке данных", True
    
    elif trigger_id == 'interval-component' and n_intervals > 0:
        # Обновляем данные по интервалу
        ohlc_json, volume_json = get_binance_data(symbol, interval)
        if ohlc_json and volume_json:
            return {'ohlc': ohlc_json, 'volume': volume_json}, f"Данные обновлены #{n_intervals}", dash.no_update
        else:
            return dash.no_update, "Ошибка при обновлении данных", dash.no_update
    
    return dash.no_update, "Выберите символ и интервал, затем нажмите 'Загрузить данные'", True

# Клиентский callback для отрисовки графика
app.clientside_callback(
    """
    function(data) {
        // Очищаем предыдущие графики
        const chartElement = document.getElementById('chart');
        const volumeElement = document.getElementById('volume-chart');
        if (chartElement) chartElement.innerHTML = '';
        if (volumeElement) volumeElement.innerHTML = '';
        
        // Ждем загрузки библиотеки
        if (!data) {
            console.log('Нет данных для отображения');
            return '';
        }
        
        if (typeof LightweightCharts === 'undefined') {
            console.log('LightweightCharts не загружена');
            return '';
        }
        
        try {
            // Парсим данные
            const ohlc = JSON.parse(data.ohlc);
            const volume = JSON.parse(data.volume);
            
            // Проверяем, что данные валидны
            if (ohlc.length === 0 || volume.length === 0) {
                console.log('Данные пусты, пропускаем отрисовку');
                return '';
            }
            
            // Создаем основной график
            if (!chartElement) {
                console.error('Элемент chart не найден');
                return '';
            }
            
            const chart = LightweightCharts.createChart(chartElement, {
                width: chartElement.clientWidth,
                height: chartElement.clientHeight,
                layout: {
                    background: { color: '#ffffff' },
                    textColor: '#333333',
                },
                grid: {
                    vertLines: { color: '#f0f0f0' },
                    horzLines: { color: '#f0f0f0' },
                },
                timeScale: {
                    timeVisible: true,
                    secondsVisible: false,
                    borderColor: '#D1D4DC',
                },
                crosshair: {
                    mode: LightweightCharts.CrosshairMode.Normal,
                }
            });
            
            // Добавляем свечной ряд
            const candleSeries = chart.addCandlestickSeries({
                upColor: '#26a69a',
                downColor: '#ef5350',
                borderVisible: false,
                wickUpColor: '#26a69a',
                wickDownColor: '#ef5350',
            });
            candleSeries.setData(ohlc);
            
            // Создаем график объема
            if (!volumeElement) {
                console.error('Элемент volume-chart не найден');
                return '';
            }
            
            const volumeChart = LightweightCharts.createChart(volumeElement, {
                width: volumeElement.clientWidth,
                height: volumeElement.clientHeight,
                layout: {
                    background: { color: '#ffffff' },
                    textColor: '#333333',
                },
                grid: {
                    vertLines: { color: '#f0f0f0' },
                    horzLines: { color: '#f0f0f0' },
                },
                timeScale: {
                    timeVisible: true,
                    secondsVisible: false,
                    borderColor: '#D1D4DC',
                }
            });
            
            // Добавляем гистограмму объема
            const volumeSeries = volumeChart.addHistogramSeries({
                color: '#26a69a',
                priceFormat: {
                    type: 'volume',
                },
                priceScaleId: '',
            });
            
            // Преобразуем данные объема в нужный формат
            const volumeData = volume.map(item => {
                return {
                    time: item.time,
                    value: item.value,
                    color: item.color === 'green' ? 'rgba(38, 166, 154, 0.5)' : 'rgba(239, 83, 80, 0.5)'
                };
            });
            
            volumeSeries.setData(volumeData);
            
            // Синхронизируем масштабирование
            chart.timeScale().subscribeVisibleTimeRangeChange(range => {
                volumeChart.timeScale().setVisibleRange(range);
            });
            
            // Автоматически скроллим к самым новым данным
            chart.timeScale().scrollToPosition(5, false);
            
        } catch (error) {
            console.error('Ошибка при создании графиков:', error);
        }
        
        return '';
    }
    """,
    Output('chart', 'children'),
    Input('data-store', 'data')
)

if __name__ == '__main__':
    app.run(debug=True)