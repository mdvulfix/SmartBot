"""
Dash-приложение — сервер подготавливает данные, клиент (clientside callback)
инициализирует Lightweight Charts прямо в браузере.
"""

import dash
from dash import dcc, html, Input, Output, State
import pandas as pd
import json
from ta.trend import SMAIndicator
from ta.momentum import RSIIndicator
import yfinance as yf

# Инициализация Dash (подключаем lightweight-charts через external_scripts)
app = dash.Dash(__name__, external_scripts=[
    "https://cdn.jsdelivr.net/npm/lightweight-charts/dist/lightweight-charts.standalone.production.js"
])


app.layout = html.Div([
    html.H1("Биржевой график с TradingView Lightweight Charts"),
    html.Div([
        dcc.Input(id='ticker-input', value='AAPL', type='text',
                  placeholder='Введите тикер (например, AAPL)', style={'marginRight': '10px', 'padding': '5px'}),
        dcc.Dropdown(id='interval-dropdown',
                     options=[
                         {'label': '1 день', 'value': '1d'},
                         {'label': '5 дней', 'value': '5d'},
                         {'label': '1 месяц', 'value': '1mo'},
                         {'label': '1 год', 'value': '1y'}
                     ],
                     value='1mo', style={'width': '200px', 'display': 'inline-block', 'marginRight': '10px'}),
        html.Button('Обновить график', id='update-button', n_clicks=0, style={'padding': '5px 10px'})
    ], style={'marginBottom': '20px'}),

    dcc.Loading(id="loading", type="circle",
                children=html.Div(id='chart-container', children=[
                    # статично создаём контейнеры для графиков — clientside callback найдёт их по id
                    html.Div(id='chart', style={'height': '60vh', 'width': '100%'}),
                    html.Div(id='rsi-chart', style={'height': '20vh', 'width': '100%', 'marginTop': '10px'}),
                ], style={'height': '80vh', 'width': '100%'})),

    # Stores — наполняет сервер, клиент читает их
    dcc.Store(id='candlestick-store'),
    dcc.Store(id='sma-store'),
    dcc.Store(id='rsi-store'),
    dcc.Store(id='volume-store'),

    # Хранит текст ошибки (сервер -> клиент)
    html.Div(id='error-message', style={'display': 'none'}),

    # Невидимый триггер-выход для clientside_callback (он будет возвращать no_update, но нужен Output)
    html.Div(id='clientside-trigger', style={'display': 'none'})
])


def map_period_to_yf(period_value):
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
    if isinstance(df.columns, pd.MultiIndex):
        new_columns = []
        for col in df.columns:
            parts = [str(p) for p in col if p is not None and str(p) != ""]
            new_columns.append("_".join(parts) if parts else "")
        df.columns = new_columns
    return df


def extract_column_name(df, possible_names):
    for name in possible_names:
        for col in df.columns:
            if name.lower() in str(col).lower():
                return col
    return None


def float_or_none(x):
    try:
        if x is None:
            return None
        val = float(x)
        if pd.isna(val):
            return None
        return val
    except Exception:
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
        data = flatten_multiindex_columns(data)
        print(f"Колонки после обработки: {list(data.columns)}")
        df = data.reset_index()
        date_col = df.columns[0]
        print(f"Колонка с датой: {date_col}")

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

        open_col = extract_column_name(df, ['Open', 'open'])
        high_col = extract_column_name(df, ['High', 'high'])
        low_col = extract_column_name(df, ['Low', 'low'])
        close_col = extract_column_name(df, ['Close', 'close', 'Adj Close', 'AdjClose'])
        volume_col = extract_column_name(df, ['Volume', 'volume'])
        print(f"Найденные колонки: Open={open_col}, High={high_col}, Low={low_col}, Close={close_col}, Volume={volume_col}")

        required_cols = [open_col, high_col, low_col, close_col]
        for col in required_cols:
            if col is None or col not in df.columns:
                error_msg = f"Не найдена необходимая колонка: {col}"
                print(error_msg)
                return None, None, None, None, error_msg

        df_ohlc = df[['time', open_col, high_col, low_col, close_col]].copy()
        df_ohlc.columns = ['time', 'open', 'high', 'low', 'close']

        if volume_col and volume_col in df.columns:
            df_vol = df[['time', volume_col]].copy()
            df_vol.columns = ['time', 'volume']
        else:
            df_vol = None

        close_vals = pd.to_numeric(df[close_col], errors='coerce')
        try:
            df['SMA50'] = SMAIndicator(close_vals, window=50).sma_indicator()
        except Exception as e:
            print(f"SMA calculation error: {e}")
            df['SMA50'] = pd.NA
        try:
            df['RSI'] = RSIIndicator(close_vals, window=14).rsi()
        except Exception as e:
            print(f"RSI calculation error: {e}")
            df['RSI'] = pd.NA

        # sanitize
        ohlc_clean = []
        for row in df_ohlc.to_dict('records'):
            t = str(row.get('time', ''))
            o = float_or_none(row.get('open'))
            h = float_or_none(row.get('high'))
            l = float_or_none(row.get('low'))
            c = float_or_none(row.get('close'))
            if t and o is not None and h is not None and l is not None and c is not None:
                ohlc_clean.append({'time': t, 'open': o, 'high': h, 'low': l, 'close': c})
        print(f"OHLC cleaned: {len(ohlc_clean)} rows (from {len(df_ohlc)})")

        volume_clean = []
        if df_vol is not None:
            for row in df_vol.to_dict('records'):
                t = str(row.get('time', ''))
                v = float_or_none(row.get('volume'))
                if t and v is not None:
                    volume_clean.append({'time': t, 'value': v})
        print(f"Volume cleaned: {len(volume_clean)} rows")

        sma_clean = []
        for row in df[['time', 'SMA50']].to_dict('records'):
            t = str(row.get('time', ''))
            v = float_or_none(row.get('SMA50'))
            if t and v is not None:
                sma_clean.append({'time': t, 'value': v})
        print(f"SMA cleaned: {len(sma_clean)} rows")

        rsi_clean = []
        for row in df[['time', 'RSI']].to_dict('records'):
            t = str(row.get('time', ''))
            v = float_or_none(row.get('RSI'))
            if t and v is not None:
                rsi_clean.append({'time': t, 'value': v})
        print(f"RSI cleaned: {len(rsi_clean)} rows")

        ohlc_json = json.dumps(ohlc_clean, default=str)
        sma_json = json.dumps(sma_clean, default=str)
        rsi_json = json.dumps(rsi_clean, default=str)
        volume_json = json.dumps(volume_clean, default=str)

        return ohlc_json, sma_json, rsi_json, volume_json, ""

    except Exception as e:
        error_msg = f"Ошибка при загрузке данных: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return None, None, None, None, error_msg


# CLIENTSIDE CALLBACK: выполняется в браузере; инициализирует LC.
app.clientside_callback(
    """
    function(ohlc_json, sma_json, rsi_json, vol_json, error_msg) {
        if (error_msg) {
            console.warn('Server error:', error_msg);
            return window.dash_clientside.no_update;
        }

        function parseMaybe(s) {
            if (!s) return [];
            if (typeof s === 'string') {
                try { return JSON.parse(s); } catch(e) { console.warn('JSON parse failed', e); return []; }
            }
            return s;
        }

        var ohlc = parseMaybe(ohlc_json);
        var sma = parseMaybe(sma_json);
        var rsi = parseMaybe(rsi_json);
        var vol = parseMaybe(vol_json);

        function initAttempt(attempt) {
            attempt = attempt || 0;
            if (typeof LightweightCharts === 'undefined') {
                console.log('LC not loaded, attempt', attempt);
                if (attempt < 60) setTimeout(function(){ initAttempt(attempt+1); }, 200);
                else console.error('LightweightCharts failed to load after many attempts');
                return;
            }

            console.log('LightweightCharts object:', LightweightCharts);
            console.log('typeof createChart:', typeof LightweightCharts.createChart);

            var chartEl = document.getElementById('chart');
            var rsiEl = document.getElementById('rsi-chart');
            if (!chartEl || !rsiEl) {
                console.error('Chart elements not found in DOM');
                return;
            }

            chartEl.innerHTML = '';
            rsiEl.innerHTML = '';

            function coerceList(arr, fields) {
                if (!Array.isArray(arr)) return [];
                var out = [];
                for (var i=0;i<arr.length;i++){
                    try {
                        var it = arr[i];
                        if (!it) continue;
                        var obj = { time: it.time ? String(it.time) : null };
                        var bad = false;
                        for (var j=0;j<fields.length;j++){
                            var f = fields[j];
                            var val = it[f];
                            if (val === undefined || val === null || val === '') { bad = true; break; }
                            var n = Number(val);
                            if (!Number.isFinite(n)) { bad = true; break; }
                            obj[f] = n;
                        }
                        if (!bad && obj.time) out.push(obj);
                    } catch(e){ continue; }
                }
                return out;
            }

            var ohlc_coerced = coerceList(ohlc, ['open','high','low','close']);
            var vol_coerced = coerceList(vol, ['value']);
            var sma_coerced = coerceList(sma, ['value']);
            var rsi_coerced = coerceList(rsi, ['value']);
            console.log('Data lengths after coercion:', ohlc_coerced.length, sma_coerced.length, rsi_coerced.length, vol_coerced.length);

            if (ohlc_coerced.length === 0) {
                console.error('No valid OHLC rows — nothing to draw');
                return;
            }

            try {
                var chart = LightweightCharts.createChart(chartEl, {
                    layout: { background: { type: 'solid', color: '#000000' }, textColor: '#d1d4dc' },
                    grid: { vertLines: { color: '#334158' }, horzLines: { color: '#334158' } },
                    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
                    timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#2B2B43' },
                    width: chartEl.clientWidth,
                    height: chartEl.clientHeight
                });

                console.log('Chart object after createChart:', chart);
                console.log('addCandlestickSeries exists?', typeof chart.addCandlestickSeries);

                // Если API поддерживает свечи, используем их, иначе fallback на линию (close)
                if (typeof chart.addCandlestickSeries === 'function') {
                    var candleSeries = chart.addCandlestickSeries({
                        upColor: '#26a69a', downColor: '#ef5350',
                        borderUpColor: '#26a69a', borderDownColor: '#ef5350',
                        wickUpColor: '#26a69a', wickDownColor: '#ef5350',
                    });
                    candleSeries.setData(ohlc_coerced);
                    console.log('candleSeries.setData executed (candles drawn)');
                } else {
                    console.warn('addCandlestickSeries not available on chart — falling back to line chart of close prices');
                    // prepare close series
                    var closeSeriesData = ohlc_coerced.map(function(x){ return { time: x.time, value: x.close }; });
                    var lineSeries = chart.addLineSeries({ color: '#4caf50', lineWidth: 2 });
                    lineSeries.setData(closeSeriesData);
                    console.log('Fallback line (close) set');
                }

                if (sma_coerced && sma_coerced.length > 0) {
                    var smaSeries = chart.addLineSeries({ color: 'orange', lineWidth: 2 });
                    smaSeries.setData(sma_coerced);
                    console.log('SMA set');
                }

                if (vol_coerced && vol_coerced.length > 0 && typeof chart.addHistogramSeries === 'function') {
                    var volSeries = chart.addHistogramSeries({ priceFormat: { type: 'volume' }, scaleMargins: { top: 0.8, bottom: 0 }});
                    volSeries.setData(vol_coerced);
                    console.log('Volume set');
                } else if (vol_coerced && vol_coerced.length > 0) {
                    console.warn('Histogram series not available — skipping volume');
                }

                // RSI chart
                var rsiChart = LightweightCharts.createChart(rsiEl, {
                    layout: { background: { type: 'solid', color: '#000000' }, textColor: '#d1d4dc' },
                    grid: { vertLines: { color: '#334158' }, horzLines: { color: '#334158' } },
                    timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#2B2B43' },
                    width: rsiEl.clientWidth,
                    height: rsiEl.clientHeight
                });
                var rsiSeries = rsiChart.addLineSeries({ color: 'purple', lineWidth: 2 });
                if (rsi_coerced && rsi_coerced.length > 0) {
                    rsiSeries.setData(rsi_coerced);
                }

                // lines
                try {
                    rsiSeries.createPriceLine({ price: 70, color: 'red', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed });
                    rsiSeries.createPriceLine({ price: 30, color: 'green', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed });
                } catch(e){}

                chart.timeScale().subscribeVisibleTimeRangeChange(function(range){
                    try { rsiChart.timeScale().setVisibleRange(range); } catch(e) {}
                });
                rsiChart.timeScale().subscribeVisibleTimeRangeChange(function(range){
                    try { chart.timeScale().setVisibleRange(range); } catch(e) {}
                });

                // resize
                function handleResize() {
                    try {
                        chart.resize(chartEl.clientWidth, chartEl.clientHeight);
                        rsiChart.resize(rsiEl.clientWidth, rsiEl.clientHeight);
                    } catch (e) {}
                }
                window.addEventListener('resize', handleResize);
                setTimeout(handleResize, 10);
                console.log('Charts initialized');
            } catch (err) {
                console.error('Error creating charts:', err);
            }
        }

        initAttempt(0);
        return window.dash_clientside.no_update;
    }
    """,
    Output('clientside-trigger', 'children'),
    [Input('candlestick-store', 'data'),
     Input('sma-store', 'data'),
     Input('rsi-store', 'data'),
     Input('volume-store', 'data'),
     Input('error-message', 'children')]
)


if __name__ == '__main__':
    app.run(debug=True, dev_tools_hot_reload=False)
