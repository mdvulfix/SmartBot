"""
Dash-приложение для отображения биржевых графиков с использованием TradingView Lightweight Charts.
Исправлены стили и улучшена загрузка библиотеки и вставка JS (избегаем f-string с { }).
"""

import dash
from dash import dcc, html, Input, Output, State
import pandas as pd
import json
from ta.trend import SMAIndicator
from ta.momentum import RSIIndicator
import yfinance as yf

# Инициализация Dash
app = dash.Dash(__name__, external_scripts=[
    "https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"
])

app.layout = html.Div([
    html.H1("Биржевой график с TradingView Lightweight Charts"),
    html.Div([
        dcc.Input(
            id='ticker-input',
            value='AAPL',
            type='text',
            placeholder='Введите тикер (например, AAPL)',
            style={'marginRight': '10px', 'padding': '5px'}
        ),
        dcc.Dropdown(
            id='interval-dropdown',
            options=[
                {'label': '1 день', 'value': '1d'},
                {'label': '5 дней', 'value': '5d'},
                {'label': '1 месяц', 'value': '1mo'},
                {'label': '1 год', 'value': '1y'}
            ],
            value='1mo',
            placeholder='Выберите период',
            style={'width': '200px', 'display': 'inline-block', 'marginRight': '10px'}
        ),
        html.Button('Обновить график', id='update-button', n_clicks=0,
                   style={'padding': '5px 10px'})
    ], style={'marginBottom': '20px'}),

    dcc.Loading(
        id="loading",
        type="circle",
        children=html.Div(id='chart-container', style={'height': '800px', 'width': '100%'})
    ),

    dcc.Store(id='candlestick-store'),
    dcc.Store(id='sma-store'),
    dcc.Store(id='rsi-store'),
    dcc.Store(id='volume-store'),

    # Скрытый div для обработки ошибок
    html.Div(id='error-message', style={'display': 'none'})
])

def map_period_to_yf(period_value):
    """Возвращает tuple (period, interval) для yfinance."""
    if period_value == '1d':
        return '1d', '5m'
    if period_value == '5d':
        return '5d', '15m'
    if period_value == '1mo':
        return '1mo', '1d'
    if period_value == '1y':
        return '1y', '1d'
    return '1mo', '1d'

def flatten_multiindex_columns(df):
    """Преобразует MultiIndex колонки в простые строки."""
    if isinstance(df.columns, pd.MultiIndex):
        # Для MultiIndex: объединяем уровни через _
        new_columns = []
        for col in df.columns:
            # безопасно обрабатываем кортежи разной длины
            parts = [str(p) for p in col if p is not None and str(p) != ""]
            new_columns.append("_".join(parts) if parts else "")
        df.columns = new_columns
    return df

def extract_column_name(df, possible_names):
    """Извлекает имя колонки из DataFrame с MultiIndex."""
    for name in possible_names:
        # Проверяем все колонки на соответствие (без учёта регистра)
        for col in df.columns:
            if name.lower() in str(col).lower():
                return col
    return None

@app.callback(
    [Output('candlestick-store', 'data'),
     Output('sma-store', 'data'),
     Output('rsi-store', 'data'),
     Output('volume-store', 'data'),
     Output('error-message', 'children')],
    [Input('update-button', 'n_clicks')],
    [State('ticker-input', 'value'),
     State('interval-dropdown', 'value')]
)
def update_data(n_clicks, ticker, interval_value):
    """Обновление данных при нажатии кнопки"""
    if n_clicks == 0:
        return None, None, None, None, ""

    if not ticker or not str(ticker).strip():
        return None, None, None, None, "Введите тикер."

    try:
        period, yf_interval = map_period_to_yf(interval_value)

        print(f"Загрузка данных: {ticker}, период: {period}, интервал: {yf_interval}")
        data = yf.download(ticker, period=period, interval=yf_interval, progress=False, auto_adjust=True)

        if data is None or data.empty:
            error_msg = "Данные не найдены для указанного тикера / периода."
            print(error_msg)
            return None, None, None, None, error_msg

        print(f"Успешно загружено {len(data)} строк")
        print(f"Колонки до обработки: {list(data.columns)}")

        # Преобразуем MultiIndex колонки в простые строки
        data = flatten_multiindex_columns(data)
        print(f"Колонки после обработки: {list(data.columns)}")

        # Сброс индекса
        df = data.reset_index()

        # Определение имени колонки с датой/временем
        date_col = df.columns[0]
        print(f"Колонка с датой: {date_col}")

        # Форматирование времени
        try:
            if pd.api.types.is_datetime64_any_dtype(df[date_col]):
                if 'm' in yf_interval:
                    df['time'] = df[date_col].dt.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    df['time'] = df[date_col].dt.strftime('%Y-%m-%d')
            else:
                df['time'] = df[date_col].astype(str)
        except Exception as e:
            print(f"Ошибка форматирования времени: {e}")
            df['time'] = df[date_col].astype(str)

        # Извлечение имен колонок
        open_col = extract_column_name(df, ['Open', 'open'])
        high_col = extract_column_name(df, ['High', 'high'])
        low_col = extract_column_name(df, ['Low', 'low'])
        close_col = extract_column_name(df, ['Close', 'close', 'Adj Close', 'AdjClose'])
        volume_col = extract_column_name(df, ['Volume', 'volume'])

        print(f"Найденные колонки: Open={open_col}, High={high_col}, Low={low_col}, Close={close_col}, Volume={volume_col}")

        # Проверка наличия необходимых колонок
        required_cols = [open_col, high_col, low_col, close_col]
        for col in required_cols:
            if col is None or col not in df.columns:
                error_msg = f"Не найдена необходимая колонка: {col}"
                print(error_msg)
                return None, None, None, None, error_msg

        # Подготовка OHLC данных
        df_ohlc = df[['time', open_col, high_col, low_col, close_col]].copy()
        df_ohlc.columns = ['time', 'open', 'high', 'low', 'close']

        # Подготовка Volume данных
        if volume_col and volume_col in df.columns:
            df_vol = df[['time', volume_col]].copy()
            df_vol.columns = ['time', 'volume']
        else:
            df_vol = None

        # Расчет индикаторов
        close_vals = pd.to_numeric(df[close_col], errors='coerce')

        # SMA
        try:
            df['SMA50'] = SMAIndicator(close_vals, window=50).sma_indicator()
        except Exception as e:
            print(f"SMA calculation error: {e}")
            df['SMA50'] = pd.NA

        # RSI
        try:
            df['RSI'] = RSIIndicator(close_vals, window=14).rsi()
        except Exception as e:
            print(f"RSI calculation error: {e}")
            df['RSI'] = pd.NA

        # Подготовка данных для возврата
        ohlc_data = df_ohlc.to_dict('records')
        sma_data = df[['time', 'SMA50']].dropna().rename(columns={'SMA50': 'value'}).to_dict('records')
        rsi_data = df[['time', 'RSI']].dropna().rename(columns={'RSI': 'value'}).to_dict('records')

        if df_vol is not None:
            volume_data = df_vol.rename(columns={'volume': 'value'}).to_dict('records')
        else:
            volume_data = []

        # Сериализация в JSON
        ohlc_json = json.dumps(ohlc_data, default=str)
        sma_json = json.dumps(sma_data, default=str)
        rsi_json = json.dumps(rsi_data, default=str)
        volume_json = json.dumps(volume_data, default=str)

        return ohlc_json, sma_json, rsi_json, volume_json, ""

    except Exception as e:
        error_msg = f"Ошибка при загрузке данных: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return None, None, None, None, error_msg

@app.callback(
    Output('chart-container', 'children'),
    [Input('candlestick-store', 'data'),
     Input('sma-store', 'data'),
     Input('rsi-store', 'data'),
     Input('volume-store', 'data'),
     Input('error-message', 'children')]
)
def update_chart(ohlc_data, sma_data, rsi_data, volume_data, error_msg):
    """Обновление графика при изменении данных"""
    if error_msg:
        return html.Div(error_msg, style={'color': 'red', 'padding': '10px'})

    if not ohlc_data:
        return html.Div("Введите тикер и нажмите 'Обновить график' для загрузки данных.")

    # Если какие-то data == None, заменим на пустые JSON-массивы
    ohlc_js = ohlc_data if ohlc_data else "[]"
    sma_js = sma_data if sma_data else "[]"
    rsi_js = rsi_data if rsi_data else "[]"
    vol_js = volume_data if volume_data else "[]"

    # Шаблон JS — обычная строка (не f-string), безопасная для фигурных скобок.
    script_template = """
    (function() {
        function checkLibraryLoaded() {
            if (typeof LightweightCharts === 'undefined') {
                console.log('LightweightCharts еще не загружен, ожидание...');
                setTimeout(checkLibraryLoaded, 100);
                return;
            }
            console.log('LightweightCharts загружен, инициализируем графики');
            initCharts();
        }

        function initCharts() {
            console.log('Инициализация графиков...');

            const chartElement = document.getElementById('chart');
            const rsiChartElement = document.getElementById('rsi-chart');

            if (!chartElement || !rsiChartElement) {
                console.error('Не найдены элементы для графиков');
                return;
            }

            try {
                const chart = LightweightCharts.createChart(chartElement, {
                    layout: {
                        background: { type: 'solid', color: '#000000' },
                        textColor: '#d1d4dc'
                    },
                    grid: {
                        vertLines: { color: '#334158' },
                        horzLines: { color: '#334158' }
                    },
                    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
                    timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#2B2B43' },
                    width: chartElement.clientWidth,
                    height: chartElement.clientHeight,
                });

                const candleSeries = chart.addCandlestickSeries({
                    upColor: '#26a69a',
                    downColor: '#ef5350',
                    borderUpColor: '#26a69a',
                    borderDownColor: '#ef5350',
                    wickUpColor: '#26a69a',
                    wickDownColor: '#ef5350',
                });

                const ohlcData = __OHLC__;
                console.log('OHLC данные:', Array.isArray(ohlcData) ? ohlcData.length : ohlcData);
                candleSeries.setData(ohlcData);

                const smaData = __SMA__;
                if (smaData && smaData.length > 0) {
                    console.log('SMA данные:', smaData.length);
                    const smaSeries = chart.addLineSeries({ color: 'orange', lineWidth: 2, priceLineVisible: false });
                    smaSeries.setData(smaData);
                }

                const volumeData = __VOL__;
                if (volumeData && volumeData.length > 0) {
                    console.log('Volume данные:', volumeData.length);
                    const volumeSeries = chart.addHistogramSeries({
                        priceFormat: { type: 'volume' },
                        scaleMargins: { top: 0.8, bottom: 0 },
                    });
                    volumeSeries.setData(volumeData);
                }

                const rsiChart = LightweightCharts.createChart(rsiChartElement, {
                    layout: {
                        background: { type: 'solid', color: '#000000' },
                        textColor: '#d1d4dc'
                    },
                    grid: {
                        vertLines: { color: '#334158' },
                        horzLines: { color: '#334158' }
                    },
                    timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#2B2B43' },
                    width: rsiChartElement.clientWidth,
                    height: rsiChartElement.clientHeight,
                });

                const rsiData = __RSI__;
                console.log('RSI данные:', Array.isArray(rsiData) ? rsiData.length : rsiData);
                const rsiSeries = rsiChart.addLineSeries({ color: 'purple', lineWidth: 2, priceLineVisible: false });
                rsiSeries.setData(rsiData);

                try {
                    rsiSeries.createPriceLine({ price: 70, color: 'red', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed });
                    rsiSeries.createPriceLine({ price: 30, color: 'green', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed });
                } catch (e) {
                    console.warn('Не удалось создать линии RSI:', e);
                }

                // Синхронизация timeScale
                chart.timeScale().subscribeVisibleTimeRangeChange((range) => {
                    try { rsiChart.timeScale().setVisibleRange(range); } catch (e) {}
                });
                rsiChart.timeScale().subscribeVisibleTimeRangeChange((range) => {
                    try { chart.timeScale().setVisibleRange(range); } catch (e) {}
                });

                function handleResize() {
                    try {
                        chart.resize(chartElement.clientWidth, chartElement.clientHeight);
                        rsiChart.resize(rsiChartElement.clientWidth, rsiChartElement.clientHeight);
                    } catch (e) {
                        console.error('Ошибка при изменении размера:', e);
                    }
                }

                window.addEventListener('resize', handleResize);
                setTimeout(handleResize, 10);

                console.log('Графики успешно инициализированы');
            } catch (e) {
                console.error('Ошибка при создании графиков:', e);
            }
        }

        checkLibraryLoaded();
    })();
    """

    # Вставляем JSON-строки в шаблон (замена маркеров)
    script_filled = script_template.replace("__OHLC__", ohlc_js).replace("__SMA__", sma_js).replace("__RSI__", rsi_js).replace("__VOL__", vol_js)

    chart_html = html.Div([
        html.Div(id='chart', style={'height': '60vh', 'width': '100%'}),
        html.Div(id='rsi-chart', style={'height': '20vh', 'width': '100%', 'marginTop': '10px'}),
        html.Script(script_filled, type="text/javascript")
    ])

    return chart_html

if __name__ == '__main__':
    app.run(debug=True, dev_tools_hot_reload=False)
