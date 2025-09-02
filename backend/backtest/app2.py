# -*- coding: utf-8 -*-
import os
import logging
import requests
import json
import pandas as pd
from datetime import datetime, timedelta
from functools import lru_cache, wraps
from flask import Flask, jsonify, request, Response
import dash
from dash import dcc, html, Input, Output, callback_context
import time
from threading import Lock
import asyncio
import websockets
from collections import deque

# ========== КОНФИГУРАЦИЯ ==========
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
HOST = os.environ.get('HOST', '127.0.0.1')
PORT = int(os.environ.get('PORT', 8050))
CACHE_TIMEOUT = int(os.environ.get('CACHE_TIMEOUT', 30))  # seconds
WS_RECONNECT_MAX_ATTEMPTS = int(os.environ.get('WS_RECONNECT_MAX_ATTEMPTS', 10))
REQUEST_TIMEOUT = int(os.environ.get('REQUEST_TIMEOUT', 10))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ========== ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ ==========
server = Flask(__name__)
app = dash.Dash(
    __name__, 
    server=server, 
    external_scripts=[
        "https://unpkg.com/lightweight-charts@4.0.1/dist/lightweight-charts.standalone.production.js"
    ],
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1.0"}]
)

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ И СОСТОЯНИЯ ==========
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

WS_URLS = [
    "wss://ws.okx.com:8443/ws/v5/business",
    "wss://wsaws.okx.com:8443/ws/v5/business",
    "wss://wspap.okx.com:8443/ws/v5/business",
    "wss://ws.okx.com:8443/ws/v5/public",
    "wss://wsaws.okx.com:8443/ws/v5/public",
    "wss://wspap.okx.com:8443/ws/v5/public"
]

# Глобальные состояния для WebSocket
ws_connections = {}
ws_lock = Lock()
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
@rate_limit(30)  # Максимум 30 запросов в минуту
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
    # Конфигурация для клиентской части
    html.Div(id='_dash-config', style={'display': 'none'}, 
             **{'data-requests-pathname-prefix': '/'}),
    
    # Заголовок
    html.H1("Real-time OKX Market Data", style={'textAlign': 'center', 'marginBottom': '20px'}),
    
    # Панель управления
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
    
    # Кастомные контролы
    html.Div(id='custom-controls-container'),
    
    # Статус
    html.Div(id='status', style={
        'textAlign': 'center', 
        'fontWeight': 'bold', 
        'margin': '10px 0',
        'height': '25px'
    }),
    
    # Графики
    html.Div([
        html.Div(id='chart', style={'height': '500px', 'width': '100%'}),
        html.Div(id='volume-chart', style={'height': '200px', 'width': '100%', 'marginTop': '20px'}),
    ], style={'width': '100%', 'padding': '0 10px'}),
    
    # Скрытые хранилища данных
    dcc.Store(id='historical-data'),
    dcc.Store(id='ws-connection-status', data={'connected': False}),
    dcc.Interval(id='update-interval', interval=1000, disabled=True),
    
    # Скрипт для инициализации клиентской части
    html.Script('''
        // Глобальные состояния
        window.ws = null;
        window.isConnected = false;
        window.currentSymbol = 'BTC-USDT';
        window.currentTimeframe = '1H';
        window.charts = null;
        window._resizeObserver = null;
        window._timeRangeUnsub = null;
        window._reconnectTimer = null;
        window._realtimeInterval = null;
        window._lastUpdateTime = 0;
        window._updateThrottleMs = 100;
        
        // Функция для обновления статуса
        function updateStatus(msg) {
            const el = document.getElementById('status');
            if (el) el.textContent = msg;
            console.log('[STATUS]', msg);
        }
        
        // Функция обработки ошибок
        function handleError(err, context) {
            console.error(`Ошибка в ${context}:`, err);
            updateStatus(`Ошибка: ${err && err.message ? err.message : err}`);
        }
        
        // Нормализация символа
        function normalizeSymbol(raw) {
            if (!raw) return raw;
            let s = String(raw).trim();
            s = s.replace(/[\\/\\uFF0F\\s]+/g, '-');
            s = s.replace(/[^\\w\\-]/g, '-');
            s = s.replace(/-+/g, '-');
            return s.toUpperCase();
        }
        
        // Нормализация таймфрейма
        function normalizeTimeframe(raw) {
            if (!raw) return raw;
            let t = String(raw).trim();
            const ru = {
                '1 минута':'1m','1 мин':'1m','1м':'1m',
                '5 минут':'5m','5 мин':'5m',
                '15 минут':'15m','15 мин':'15m',
                '1 час':'1H','1ч':'1H',
                '4 часа':'4H','4 ч':'4H',
                '1 день':'1D','1д':'1D'
            };
            const lower = t.toLowerCase();
            if (ru[lower]) return ru[lower];
            if (/^\\d+\\s*m(in(ute)?s?)?$/i.test(t)) { const num = t.match(/\\d+/)[0]; return `${num}m`; }
            if (/^\\d+\\s*h(r|our|ours)?$/i.test(t) || /^\\d+H$/i.test(t)) { const num = t.match(/\\d+/)[0]; return `${num}H`; }
            if (/^\\d+m$/i.test(t)) return t.toLowerCase();
            if (/^\\d+h$/i.test(t)) return t.toUpperCase();
            return t;
        }
        
        // Чтение значения из dropdown
        function readDropdownValue(elem) {
            if (!elem) return null;
            const sel = elem.querySelector('select'); if (sel && sel.value) return sel.value;
            const input = elem.querySelector('input'); if (input && input.value) return input.value;
            const dv = elem.querySelector('[data-value]')?.dataset?.value; if (dv) return dv;
            const opt = elem.querySelector('[aria-selected="true"], .is-selected, .Select-value'); 
            if (opt) return opt.dataset?.value || opt.textContent?.trim() || null;
            const txt = elem.textContent?.trim(); return txt || null;
        }
        
        // Инициализация графиков
        function initCharts(ohlcData, volumeData) {
            const chartElement = document.getElementById('chart');
            const volumeElement = document.getElementById('volume-chart');
            if (!chartElement || !volumeElement) { 
                console.error('Элементы графиков не найдены'); 
                return null; 
            }
            
            chartElement.innerHTML = ''; 
            volumeElement.innerHTML = '';
            
            if (typeof LightweightCharts === 'undefined') { 
                console.error('LightweightCharts не загружена'); 
                return null; 
            }

            try {
                const rectChart = chartElement.getBoundingClientRect();
                const rectVol = volumeElement.getBoundingClientRect();
                const chartWidth = Math.max(1, Math.floor(rectChart.width || chartElement.clientWidth || 800));
                const chartHeight = Math.max(200, Math.floor(rectChart.height || 400));
                const volHeight = Math.max(100, Math.floor(rectVol.height || 150));

                const chart = LightweightCharts.createChart(chartElement, {
                    width: chartWidth, 
                    height: chartHeight,
                    layout: { background: { color: '#ffffff' }, textColor: '#333333' },
                    grid: { vertLines: { color: '#f0f0f0' }, horzLines: { color: '#f0f0f0' } },
                    timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#D1D4DC' },
                    crosshair: { mode: LightweightCharts.CrosshairMode.Normal }
                });

                const candleSeries = chart.addCandlestickSeries({
                    upColor: '#26a69a', downColor: '#ef5350', borderVisible: false, 
                    wickUpColor: '#26a69a', wickDownColor: '#ef5350'
                });
                candleSeries.setData(ohlcData || []);

                const volumeChart = LightweightCharts.createChart(volumeElement, {
                    width: chartWidth, 
                    height: volHeight,
                    layout: { background: { color: '#ffffff' }, textColor: '#333333' },
                    grid: { vertLines: { color: '#f0f0f0' }, horzLines: { color: '#f0f0f0' } },
                    timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#D1D4DC' }
                });

                const volumeSeries = volumeChart.addHistogramSeries({
                    priceFormat: { type: 'volume' }, 
                    priceScaleId: '', 
                    scaleMargins: { top: 0.85, bottom: 0 }
                });
                volumeSeries.setData(volumeData || []);

                // Очистка предыдущих подписок
                if (window._timeRangeUnsub && typeof window._timeRangeUnsub === 'function') { 
                    try { window._timeRangeUnsub(); } catch (e){} 
                    window._timeRangeUnsub = null; 
                }

                // Синхронизация масштабирования
                const unsubA = chart.timeScale().subscribeVisibleTimeRangeChange(range => { 
                    try { volumeChart.timeScale().setVisibleRange(range); } catch(e){} 
                });
                
                const unsubB = volumeChart.timeScale().subscribeVisibleTimeRangeChange(range => { 
                    try { chart.timeScale().setVisibleRange(range); } catch(e){} 
                });
                
                window._timeRangeUnsub = () => {
                    try { chart.timeScale().unsubscribeVisibleTimeRangeChange(unsubA); } catch (e) {}
                    try { volumeChart.timeScale().unsubscribeVisibleTimeRangeChange(unsubB); } catch (e) {}
                };

                // Реакция на изменение размера
                if (window._resizeObserver) { 
                    try { window._resizeObserver.disconnect(); } catch (e) {} 
                    window._resizeObserver = null; 
                }
                
                window._resizeObserver = new ResizeObserver(entries => {
                    for (const entry of entries) {
                        const w = Math.max(1, Math.floor(entry.contentRect.width || chartElement.clientWidth));
                        const hChart = Math.max(200, Math.floor(document.getElementById('chart').getBoundingClientRect().height || 400));
                        const hVol = Math.max(100, Math.floor(document.getElementById('volume-chart').getBoundingClientRect().height || 150));
                        try { 
                            chart.resize(w, hChart); 
                            volumeChart.resize(w, hVol); 
                        } catch (e) {}
                    }
                });
                
                const parent = chartElement.parentElement || chartElement;
                try { window._resizeObserver.observe(parent); } catch (e) {}

                // Прокрутка к текущему времени
                try { chart.timeScale().scrollToRealTime(); } catch (e) {}

                return { chart, volumeChart, candleSeries, volumeSeries };
            } catch (error) {
                console.error('Ошибка при создании графиков:', error);
                return null;
            }
        }
        
        // Функция для безопасного обновления графиков с троттлингом
        function safeUpdateCharts(data, candleSeries, volumeSeries) {
            const now = Date.now();
            if (now - window._lastUpdateTime < window._updateThrottleMs) return;
            
            window._lastUpdateTime = now;
            
            try {
                if (data.data && Array.isArray(data.data)) {
                    data.data.forEach(candle => {
                        const rawTs = candle[0];
                        const timestamp = Math.floor(parseInt(rawTs) / 1000);
                        const open = parseFloat(candle[1]); 
                        const high = parseFloat(candle[2]);
                        const low = parseFloat(candle[3]); 
                        const close = parseFloat(candle[4]);
                        const volume = parseFloat(candle[5]);
                        
                        if (candleSeries && volumeSeries) {
                            try {
                                candleSeries.update({ time: timestamp, open, high, low, close });
                                volumeSeries.update({ 
                                    time: timestamp, 
                                    value: volume, 
                                    color: close >= open ? 'rgba(38,166,154,0.5)' : 'rgba(239,83,80,0.5)' 
                                });
                            } catch (err) { 
                                console.error('[WS] Ошибка обновления серий:', err); 
                            }
                        }
                    });
                }
            } catch (error) {
                console.error('[WS] Ошибка обработки сообщения:', error, data);
            }
        }
        
        // Подключение к WebSocket
        function connectWebSocket(symbol, timeframe, candleSeries, volumeSeries) {
            // Очистка предыдущих соединений
            disconnectWebSocket();
            
            if (!symbol || !timeframe) { 
                updateStatus('Не задан символ или таймфрейм'); 
                return; 
            }

            const wsUrls = %s;
            let currentIndex = 0;
            let reconnectAttempts = 0;
            const MAX_RECONNECT_ATTEMPTS = %d;

            function scheduleReconnect() {
                if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
                    updateStatus("Максимальное количество попыток переподключения достигнуто");
                    return;
                }
                
                if (window._reconnectTimer) { 
                    clearTimeout(window._reconnectTimer); 
                    window._reconnectTimer = null; 
                }
                
                const backoff = Math.min(60000, 1000 * Math.pow(2, Math.min(reconnectAttempts, 6)));
                const jitter = Math.floor(Math.random() * 500);
                const delay = backoff + jitter;
                
                console.log(`[WS] Планируем переподключение через ${delay}ms (попытка ${reconnectAttempts})`);
                window._reconnectTimer = setTimeout(() => { 
                    reconnectAttempts++; 
                    doConnect(); 
                }, delay);
            }

            function doConnect() {
                if (currentIndex >= wsUrls.length) { 
                    currentIndex = 0; 
                    reconnectAttempts++; 
                }
                
                const wsUrl = wsUrls[currentIndex];
                console.log(`[WS] Попытка подключения: ${wsUrl}`);
                updateStatus(`Подключение к ${wsUrl}...`);

                try {
                    window.ws = new WebSocket(wsUrl);

                    window.ws.onopen = function() {
                        console.log('[WS] Подключено', wsUrl);
                        window.isConnected = true; 
                        reconnectAttempts = 0;
                        updateStatus(`Подключено к ${symbol} (${timeframe})`);

                        const bar = timeframe; // Уже нормализованный
                        const channel = `candle${bar}`;
                        const subscribeArg = { channel: channel, instId: symbol };

                        if (wsUrl.includes('/business')) {
                            subscribeArg.instType = 'SPOT';
                        }

                        // OKX ожидает {op:"subscribe", args:[{...}]}
                        const subscribeMessage = { op: "subscribe", args: [ subscribeArg ] };

                        try {
                            window.ws.send(JSON.stringify(subscribeMessage));
                            console.log('[WS] Отправлен subscribe:', subscribeMessage);
                        } catch (e) { 
                            console.error('[WS] Не удалось отправить subscribe', e); 
                        }
                    };

                    window.ws.onmessage = function(event) {
                        try {
                            const data = JSON.parse(event.data);
                            if (data.event === 'subscribe' || data.event === 'error') {
                                console.log('[WS] Ответ на subscribe:', data);
                                if (data.event === 'error') {
                                    console.error('[WS] Ошибка subscribe:', data);
                                    const msg = (data.msg || '').toLowerCase();
                                    if (msg.includes('wrong url') || msg.includes('wrong channel') || 
                                        msg.includes('parameter') || (data.code && String(data.code).startsWith('6'))) {
                                        console.warn('[WS] Ошибка подписки - переключаемся на следующий URL');
                                        try { window.ws.close(); } catch (e) {}
                                        currentIndex++; 
                                        scheduleReconnect();
                                    }
                                }
                                return;
                            }

                            // Безопасное обновление с троттлингом
                            safeUpdateCharts(data, candleSeries, volumeSeries);
                        } catch (error) {
                            console.error('[WS] Ошибка обработки сообщения:', error, event && event.data);
                        }
                    };

                    window.ws.onerror = function(err) {
                        console.error('[WS] Ошибка', err);
                        currentIndex++; 
                        scheduleReconnect();
                    };

                    window.ws.onclose = function(ev) {
                        console.log('[WS] Закрыто', ev && ev.code, ev && ev.reason);
                        window.isConnected = false;
                        updateStatus('Отключено');
                        currentIndex++; 
                        scheduleReconnect();
                    };
                } catch (error) {
                    console.error('[WS] Ошибка создания WebSocket:', error);
                    currentIndex++; 
                    scheduleReconnect();
                }
            }

            doConnect();
        }
        
        // Отключение WebSocket
        function disconnectWebSocket() {
            if (window.ws) {
                try { window.ws.close(); } catch (e) {}
                window.ws = null;
            }
            
            if (window._realtimeInterval) {
                clearInterval(window._realtimeInterval);
                window._realtimeInterval = null;
            }
            
            window.isConnected = false;
            updateStatus('Отключено');
            
            if (window._reconnectTimer) { 
                clearTimeout(window._reconnectTimer); 
                window._reconnectTimer = null; 
            }
        }
        
        // Инициализация кастомных контролов
        function ensureModeControls() {
            let controls = document.getElementById('custom-controls');
            if (controls) return controls;

            // Поиск контейнера для вставки
            const symbolContainer = document.getElementById('symbol-selector')?.closest('div') ||
                                 document.getElementById('connect-button')?.closest('div') ||
                                 document.querySelector('body');

            // Создание контролов
            controls = document.createElement('div');
            controls.id = 'custom-controls';
            controls.style.display = 'flex';
            controls.style.flexWrap = 'wrap';
            controls.style.alignItems = 'center';
            controls.style.gap = '8px';
            controls.style.margin = '10px 0';
            controls.style.justifyContent = 'center';

            // Режимы
            const modeLabel = document.createElement('label');
            modeLabel.textContent = 'Режим:';
            controls.appendChild(modeLabel);

            ['historical','realtime'].forEach(m => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'mode-button';
                btn.dataset.mode = m;
                btn.textContent = m === 'historical' ? 'Исторический' : 'Реальный';
                btn.style.padding = '6px 8px';
                btn.style.cursor = 'pointer';
                btn.style.border = '1px solid #ddd';
                btn.style.borderRadius = '4px';
                btn.style.background = '#f9f9f9';
                if (m === 'historical') btn.style.fontWeight = '700';
                controls.appendChild(btn);
            });

            // Таймфрейм кнопки
            const tfLabel = document.createElement('label');
            tfLabel.textContent = 'Таймфрейм:';
            controls.appendChild(tfLabel);

            const tfOptions = ['1m','5m','15m','1H','4H','1D'];
            tfOptions.forEach(tf => {
                const tbtn = document.createElement('button');
                tbtn.type = 'button';
                tbtn.className = 'tf-button';
                tbtn.dataset.tf = tf;
                tbtn.textContent = tf;
                tbtn.style.padding = '6px 8px';
                tbtn.style.cursor = 'pointer';
                tbtn.style.border = '1px solid #ddd';
                tbtn.style.borderRadius = '4px';
                tbtn.style.background = '#f9f9f9';
                controls.appendChild(tbtn);
                
                if (tf === window.currentTimeframe) tbtn.style.fontWeight = '700';
            });

            // Вставка в DOM
            try {
                if (symbolContainer && symbolContainer.parentElement) {
                    symbolContainer.parentElement.insertBefore(controls, symbolContainer.nextSibling);
                } else {
                    const chartParent = document.getElementById('chart')?.parentElement || document.body;
                    chartParent.insertBefore(controls, document.getElementById('chart'));
                }
            } catch (e) {
                document.body.insertBefore(controls, document.body.firstChild);
            }
            
            // Делегирование событий
            controls.addEventListener('click', function(e) {
                // Обработка кнопок режима
                if (e.target.classList.contains('mode-button')) {
                    document.querySelectorAll('.mode-button').forEach(b => b.style.fontWeight = '400');
                    e.target.style.fontWeight = '700';
                    controls.dataset.mode = e.target.dataset.mode;
                }
                
                // Обработка кнопок таймфрейма
                if (e.target.classList.contains('tf-button')) {
                    document.querySelectorAll('.tf-button').forEach(b => b.style.fontWeight = '400');
                    e.target.style.fontWeight = '700';
                    window.currentTimeframe = e.target.dataset.tf;
                    console.log('[UI] Таймфрейм изменен на', window.currentTimeframe);
                }
            });

            return controls;
        }
        
        // Инициализация приложения
        function initializeApp() {
            try {
                const ctrls = ensureModeControls();
                
                const check = setInterval(() => {
                    const connectButton = document.getElementById('connect-button');
                    const disconnectButton = document.getElementById('disconnect-button');
                    const symbolSelector = document.getElementById('symbol-selector');
                    const timeframeSelector = document.getElementById('timeframe-selector');

                    if (timeframeSelector) {
                        timeframeSelector.style.display = 'none';
                    }

                    if (connectButton && disconnectButton && symbolSelector && timeframeSelector && ctrls) {
                        clearInterval(check);
                        
                        // Установка начальных значений
                        const sVal = readDropdownValue(symbolSelector) || 'BTC-USDT';
                        const tVal = readDropdownValue(timeframeSelector) || '1H';
                        window.currentSymbol = sVal;
                        window.currentTimeframe = normalizeTimeframe(tVal);
                        
                        // Синхронизация кнопок таймфрейма
                        document.querySelectorAll('.tf-button').forEach(b => {
                            if (b.dataset.tf === window.currentTimeframe) {
                                b.style.fontWeight = '700';
                            } else {
                                b.style.fontWeight = '400';
                            }
                        });
                        
                        // Обработчики событий кнопок
                        connectButton.addEventListener('click', () => {
                            if (window.isConnected) { 
                                updateStatus('Уже подключено'); 
                                return; 
                            }
                            
                            const rawSym = readDropdownValue(symbolSelector) || window.currentSymbol;
                            const rawTf = readDropdownValue(timeframeSelector) || window.currentTimeframe;
                            const normalizedSymbol = normalizeSymbol(rawSym);
                            const normalizedTf = normalizeTimeframe(window.currentTimeframe || rawTf);
                            const activeMode = ctrls.dataset.mode || 'historical';
                            
                            updateStatus('Загрузка исторических данных...');
                            
                            // Запрос исторических данных
                            const prefix = '/';
                            const apiUrl = `${prefix}/api/historical-data/${encodeURIComponent(normalizedSymbol)}/${encodeURIComponent(normalizedTf)}`;
                            
                            fetch(apiUrl)
                                .then(response => {
                                    if (!response.ok) {
                                        return response.text().then(text => { throw new Error(text) });
                                    }
                                    return response.json();
                                })
                                .then(data => {
                                    if (data.error) {
                                        handleError(data.error, 'загрузка исторических данных');
                                        return;
                                    }
                                    
                                    let ohlc = data.ohlc || [];
                                    let volume = data.volume || [];
                                    
                                    // Инициализация графиков
                                    window.charts = initCharts(ohlc, volume);
                                    if (!window.charts) {
                                        updateStatus('Ошибка инициализации графиков');
                                        return;
                                    }
                                    
                                    if (activeMode === 'historical') {
                                        updateStatus(`Отображается исторический период (${normalizedSymbol} ${normalizedTf})`);
                                        return;
                                    }
                                    
                                    if (activeMode === 'realtime') {
                                        connectWebSocket(normalizedSymbol, normalizedTf, 
                                                        window.charts.candleSeries, window.charts.volumeSeries);
                                        return;
                                    }
                                })
                                .catch(err => {
                                    handleError(err, 'загрузка исторических данных');
                                });
                        });
                        
                        disconnectButton.addEventListener('click', () => {
                            disconnectWebSocket();
                        });
                    }
                }, 100);
            } catch (error) {
                handleError(error, 'инициализация приложения');
            }
        }
        
        // Запуск приложения после загрузки DOM
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initializeApp);
        } else {
            initializeApp();
        }
    ''' % (json.dumps(WS_URLS), WS_RECONNECT_MAX_ATTEMPTS))
])

# ========== CALLBACKS ==========
@app.callback(
    Output('custom-controls-container', 'children'),
    Input('symbol-selector', 'value'),
    Input('timeframe-selector', 'value')
)
def update_custom_controls(symbol, timeframe):
    """Обновление кастомных контролов при изменении символа/таймфрейма"""
    return "Контролы создаются на клиентской стороне"  

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