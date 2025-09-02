"""
Упрощенная версия для проверки отображения графика Lightweight Charts v4.0.1
"""

import dash
from dash import dcc, html, Input, Output
import json
from datetime import datetime

# Инициализация Dash с external_scripts для версии 4.0.1
app = dash.Dash(__name__, external_scripts=[
    "https://unpkg.com/lightweight-charts@4.0.1/dist/lightweight-charts.standalone.production.js"
])

app.layout = html.Div([
    html.H1("Тестовый график Lightweight Charts v4.0.1"),
    html.Button('Показать график', id='update-button', n_clicks=0),
    
    # Контейнеры для графиков
    html.Div(id='chart-container', children=[
        html.Div(id='chart', style={'height': '400px', 'width': '100%'}),
        html.Div(id='rsi-chart', style={'height': '200px', 'width': '100%', 'marginTop': '20px'}),
    ]),
    
    # Хранилище для тестовых данных
    dcc.Store(id='data-store'),
    
    # Скрытый элемент для запуска callback после загрузки страницы
    html.Div(id='page-loaded', style={'display': 'none'}, children='loaded')
])


# Генерируем тестовые данные
def generate_test_data():
    # Простые тестовые данные
    ohlc_data = []
    rsi_data = []
    
    for i in range(100):
        # Конвертируем время в формат, ожидаемый Lightweight Charts
        time = int(datetime(2023, 5, 10 + i//24, i%24).timestamp())
        open_price = 100 + i
        high_price = open_price + 5
        low_price = open_price - 5
        close_price = open_price + (2 if i % 2 == 0 else -2)
        
        ohlc_data.append({
            'time': time,
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price
        })
        
        rsi_value = 50 + (10 if i % 10 < 5 else -10)
        rsi_data.append({
            'time': time,
            'value': rsi_value
        })
    
    return json.dumps(ohlc_data), json.dumps(rsi_data)


@app.callback(
    Output('data-store', 'data'),
    Input('update-button', 'n_clicks'),
    Input('page-loaded', 'children')
)
def update_data(n_clicks, loaded):
    # Генерируем данные при загрузке страницы или нажатии кнопки
    ctx = dash.callback_context
    if not ctx.triggered:
        return None
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger_id == 'update-button' and n_clicks > 0:
        ohlc_json, rsi_json = generate_test_data()
        return {'ohlc': ohlc_json, 'rsi': rsi_json}
    elif trigger_id == 'page-loaded':
        # Автоматически генерируем данные при загрузке страницы
        ohlc_json, rsi_json = generate_test_data()
        return {'ohlc': ohlc_json, 'rsi': rsi_json}
    
    return None


# Клиентский callback для отрисовки графика
app.clientside_callback(
    """
    function(data) {
        // Очищаем предыдущие графики
        const chartElement = document.getElementById('chart');
        const rsiElement = document.getElementById('rsi-chart');
        if (chartElement) chartElement.innerHTML = '';
        if (rsiElement) rsiElement.innerHTML = '';
        
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
            const rsi = JSON.parse(data.rsi);
            
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
                }
            });
            
            // Добавляем свечной ряд (используем альтернативный метод)
            const candleSeries = chart.addCandlestickSeries({
                upColor: '#26a69a',
                downColor: '#ef5350',
                borderVisible: false,
                wickUpColor: '#26a69a',
                wickDownColor: '#ef5350',
            });
            candleSeries.setData(ohlc);
            
            // Создаем график RSI
            if (!rsiElement) {
                console.error('Элемент rsi-chart не найден');
                return '';
            }
            
            const rsiChart = LightweightCharts.createChart(rsiElement, {
                width: rsiElement.clientWidth,
                height: rsiElement.clientHeight,
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
                }
            });
            
            // Добавляем линию RSI (используем альтернативный метод)
            const rsiSeries = rsiChart.addLineSeries({
                color: '#7E57C2',
                lineWidth: 2,
            });
            rsiSeries.setData(rsi);
            
            // Добавляем горизонтальные линии для RSI
            rsiSeries.createPriceLine({
                price: 70,
                color: '#ff5252',
                lineWidth: 1,
                lineStyle: 2, // Dashed
            });
            
            rsiSeries.createPriceLine({
                price: 30,
                color: '#4caf50',
                lineWidth: 1,
                lineStyle: 2, // Dashed
            });
            
            // Синхронизируем масштабирование
            chart.timeScale().subscribeVisibleTimeRangeChange(range => {
                rsiChart.timeScale().setVisibleRange(range);
            });
            
            console.log('Графики успешно созданы!');
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