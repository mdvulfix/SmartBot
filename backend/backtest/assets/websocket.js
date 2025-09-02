// === file: websocket.js ===
// assets/websocket.js
// Оптимизированная версия с WebWorker и типизированными массивами

// ========== Глобальные состояния ==========
window.ws = null;
window.isConnected = false;
window.currentSymbol = 'BTC-USDT';
window.currentTimeframe = '1H';
window.charts = null;

window._resizeObserver = null;
window._timeRangeUnsub = null;
window._reconnectTimer = null;
window._realtimeInterval = null;
window._dataWorker = null;
window._lastUpdateTime = 0;
window._updateThrottleMs = 100;

// ========== Типизированные массивы для хранения данных ==========
window.ohlcData = {
    time: new Float64Array(1000),
    open: new Float64Array(1000),
    high: new Float64Array(1000),
    low: new Float64Array(1000),
    close: new Float64Array(1000),
    length: 0
};

window.volumeData = {
    time: new Float64Array(1000),
    value: new Float64Array(1000),
    color: new Array(1000),
    length: 0
};

// ========== Web Worker для обработки данных ==========
function initDataWorker() {
    if (window.Worker) {
        // Создаем Web Worker из строки кода
        const workerCode = `
            self.onmessage = function(e) {
                const { type, data } = e.data;
                
                if (type === 'processCandle') {
                    // Обработка свечных данных в воркере
                    const result = processCandleData(data);
                    self.postMessage({ type: 'candleProcessed', data: result });
                } else if (type === 'processHistorical') {
                    // Обработка исторических данных в воркере
                    const result = processHistoricalData(data);
                    self.postMessage({ type: 'historicalProcessed', data: result });
                }
            };
            
            function processCandleData(wsData) {
                if (!wsData.data || !Array.isArray(wsData.data)) return null;
                
                const candles = [];
                
                for (const candle of wsData.data) {
                    candles.push({
                        time: Math.floor(parseInt(candle[0]) / 1000),
                        open: parseFloat(candle[1]),
                        high: parseFloat(candle[2]),
                        low: parseFloat(candle[3]),
                        close: parseFloat(candle[4]),
                        volume: parseFloat(candle[5])
                    });
                }
                
                return candles;
            }
            
            function processHistoricalData(apiData) {
                if (!apiData.ohlc || !apiData.volume) return null;
                
                // Конвертация в типизированные массивы
                const ohlc = {
                    time: new Float64Array(apiData.ohlc.length),
                    open: new Float64Array(apiData.ohlc.length),
                    high: new Float64Array(apiData.ohlc.length),
                    low: new Float64Array(apiData.ohlc.length),
                    close: new Float64Array(apiData.ohlc.length),
                    length: apiData.ohlc.length
                };
                
                const volume = {
                    time: new Float64Array(apiData.volume.length),
                    value: new Float64Array(apiData.volume.length),
                    color: new Array(apiData.volume.length),
                    length: apiData.volume.length
                };
                
                for (let i = 0; i < apiData.ohlc.length; i++) {
                    ohlc.time[i] = apiData.ohlc[i].time;
                    ohlc.open[i] = apiData.ohlc[i].open;
                    ohlc.high[i] = apiData.ohlc[i].high;
                    ohlc.low[i] = apiData.ohlc[i].low;
                    ohlc.close[i] = apiData.ohlc[i].close;
                    
                    volume.time[i] = apiData.volume[i].time;
                    volume.value[i] = apiData.volume[i].value;
                    volume.color[i] = apiData.volume[i].color;
                }
                
                return { ohlc, volume };
            }
        `;
        
        const blob = new Blob([workerCode], { type: 'application/javascript' });
        window._dataWorker = new Worker(URL.createObjectURL(blob));
        
        window._dataWorker.onmessage = function(e) {
            const { type, data } = e.data;
            
            if (type === 'candleProcessed' && data) {
                updateChartsWithTypedArrays(data);
            } else if (type === 'historicalProcessed' && data) {
                window.ohlcData = data.ohlc;
                window.volumeData = data.volume;
                initChartsWithTypedArrays();
            }
        };
    }
}

// ========== Хелперы ==========
function mapTimeframeToOkxBar(tf) {
    const map = { '1m':'1m','5m':'5m','15m':'15m','1H':'1H','4H':'4H','1D':'1D' };
    return map[tf] || '1H';
}

function normalizeSymbol(raw) {
    if (!raw) return raw;
    let s = String(raw).trim();
    s = s.replace(/[\/\uFF0F\s]+/g, '-');
    s = s.replace(/[^\w\-]/g, '-');
    s = s.replace(/-+/g, '-');
    return s.toUpperCase();
}

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
    if (/^\d+\s*m(in(ute)?s?)?$/i.test(t)) { const num = t.match(/\d+/)[0]; return `${num}m`; }
    if (/^\d+\s*h(r|our|ours)?$/i.test(t) || /^\d+H$/i.test(t)) { const num = t.match(/\d+/)[0]; return `${num}H`; }
    if (/^\d+m$/i.test(t)) return t.toLowerCase();
    if (/^\d+h$/i.test(t)) return t.toUpperCase();
    return t;
}

function getDashRequestsPathnamePrefix() {
    try {
        const el = document.getElementById('_dash-config');
        if (!el) return '/';
        const cfg = JSON.parse(el.textContent || el.innerText || '{}');
        const prefix = cfg.requests_pathname_prefix || '/';
        let p = String(prefix);
        if (!p.startsWith('/')) p = '/' + p;
        p = p.replace(/\/+$/, '');
        return p || '/';
    } catch (e) {
        return '/';
    }
}

// Функция для правильного формирования URL
function getApiUrl(endpoint) {
    const prefix = getDashRequestsPathnamePrefix();
    const baseUrl = window.location.origin;
    
    // Убедимся, что префикс начинается и заканчивается правильно
    let cleanPrefix = prefix;
    if (cleanPrefix !== '/') {
        cleanPrefix = cleanPrefix.startsWith('/') ? cleanPrefix : `/${cleanPrefix}`;
        cleanPrefix = cleanPrefix.endsWith('/') ? cleanPrefix : `${cleanPrefix}/`;
    }
    
    // Формируем полный URL
    return `${baseUrl}${cleanPrefix}${endpoint}`;
}

function readDropdownValue(elem) {
    if (!elem) return null;
    const sel = elem.querySelector('select'); if (sel && sel.value) return sel.value;
    const input = elem.querySelector('input'); if (input && input.value) return input.value;
    const dv = elem.querySelector('[data-value]')?.dataset?.value; if (dv) return dv;
    const opt = elem.querySelector('[aria-selected="true"], .is-selected, .Select-value'); if (opt) return opt.dataset?.value || opt.textContent?.trim() || null;
    const txt = elem.textContent?.trim(); return txt || null;
}

function updateStatus(msg) {
    const el = document.getElementById('status');
    if (el) el.textContent = msg;
    console.log('[STATUS]', msg);
}

function handleError(err, context) {
    console.error(`Ошибка в ${context}:`, err);
    updateStatus(`Ошибка: ${err && err.message ? err.message : err}`);
}

// ========== UI: динамически создаём контролы ==========
function ensureModeControls() {
    let controls = document.getElementById('custom-controls');
    if (controls) return controls;

    const symbolContainer = document.getElementById('symbol-selector')?.closest('div') ||
                         document.getElementById('connect-button')?.closest('div') ||
                         document.querySelector('body');

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
        if (e.target.classList.contains('mode-button')) {
            document.querySelectorAll('.mode-button').forEach(b => b.style.fontWeight = '400');
            e.target.style.fontWeight = '700';
            controls.dataset.mode = e.target.dataset.mode;
        }
        
        if (e.target.classList.contains('tf-button')) {
            document.querySelectorAll('.tf-button').forEach(b => b.style.fontWeight = '400');
            e.target.style.fontWeight = '700';
            window.currentTimeframe = e.target.dataset.tf;
            console.log('[UI] Таймфрейм изменен на', window.currentTimeframe);
        }
    });

    return controls;
}

// ========== Charts init с типизированными массивами ==========
function initChartsWithTypedArrays() {
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

        // Конвертация типизированных массивов в формат для графиков
        const ohlcFormatted = [];
        for (let i = 0; i < window.ohlcData.length; i++) {
            ohlcFormatted.push({
                time: window.ohlcData.time[i],
                open: window.ohlcData.open[i],
                high: window.ohlcData.high[i],
                low: window.ohlcData.low[i],
                close: window.ohlcData.close[i]
            });
        }

        const volumeFormatted = [];
        for (let i = 0; i < window.volumeData.length; i++) {
            volumeFormatted.push({
                time: window.volumeData.time[i],
                value: window.volumeData.value[i],
                color: window.volumeData.color[i]
            });
        }

        candleSeries.setData(ohlcFormatted);
        volumeSeries.setData(volumeFormatted);

        // Синхронизация масштабирования
        if (window._timeRangeUnsub && typeof window._timeRangeUnsub === 'function') { 
            try { window._timeRangeUnsub(); } catch (e){} 
            window._timeRangeUnsub = null; 
        }

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

// ========== Обновление графиков с типизированными массивами ==========
function updateChartsWithTypedArrays(candles) {
    if (!window.charts || !candles.length) return;
    
    const now = Date.now();
    if (now - window._lastUpdateTime < window._updateThrottleMs) return;
    
    window._lastUpdateTime = now;
    
    try {
        for (const candle of candles) {
            // Обновление типизированных массивов
            if (window.ohlcData.length >= window.ohlcData.time.length) {
                // Увеличиваем размер массивов при необходимости
                resizeTypedArrays();
            }
            
            const idx = window.ohlcData.length;
            window.ohlcData.time[idx] = candle.time;
            window.ohlcData.open[idx] = candle.open;
            window.ohlcData.high[idx] = candle.high;
            window.ohlcData.low[idx] = candle.low;
            window.ohlcData.close[idx] = candle.close;
            window.ohlcData.length++;
            
            window.volumeData.time[idx] = candle.time;
            window.volumeData.value[idx] = candle.volume;
            window.volumeData.color[idx] = candle.close >= candle.open ? 
                'rgba(38,166,154,0.5)' : 'rgba(239,83,80,0.5)';
            window.volumeData.length++;
            
            // Обновление графиков
            window.charts.candleSeries.update({
                time: candle.time,
                open: candle.open,
                high: candle.high,
                low: candle.low,
                close: candle.close
            });
            
            window.charts.volumeSeries.update({
                time: candle.time,
                value: candle.volume,
                color: candle.close >= candle.open ? 
                    'rgba(38,166,154,0.5)' : 'rgba(239,83,80,0.5)'
            });
        }
    } catch (error) {
        console.error('Ошибка обновления графиков:', error);
    }
}

// ========== Увеличение размера типизированных массивов ==========
function resizeTypedArrays() {
    const newSize = window.ohlcData.time.length * 2;
    
    // Создание новых массивов большего размера
    const newOhlcTime = new Float64Array(newSize);
    const newOhlcOpen = new Float64Array(newSize);
    const newOhlcHigh = new Float64Array(newSize);
    const newOhlcLow = new Float64Array(newSize);
    const newOhlcClose = new Float64Array(newSize);
    
    const newVolumeTime = new Float64Array(newSize);
    const newVolumeValue = new Float64Array(newSize);
    const newVolumeColor = new Array(newSize);
    
    // Копирование старых данных
    newOhlcTime.set(window.ohlcData.time);
    newOhlcOpen.set(window.ohlcData.open);
    newOhlcHigh.set(window.ohlcData.high);
    newOhlcLow.set(window.ohlcData.low);
    newOhlcClose.set(window.ohlcData.close);
    
    newVolumeTime.set(window.volumeData.time);
    newVolumeValue.set(window.volumeData.value);
    newVolumeColor.splice(0, window.volumeData.color.length, ...window.volumeData.color);
    
    // Замена старых массивов новыми
    window.ohlcData.time = newOhlcTime;
    window.ohlcData.open = newOhlcOpen;
    window.ohlcData.high = newOhlcHigh;
    window.ohlcData.low = newOhlcLow;
    window.ohlcData.close = newOhlcClose;
    
    window.volumeData.time = newVolumeTime;
    window.volumeData.value = newVolumeValue;
    window.volumeData.color = newVolumeColor;
}

// ========== WebSocket connection logic ==========
function connectWebSocket(symbol, timeframe, candleSeries, volumeSeries) {
    disconnectWebSocket();
    
    if (!symbol || !timeframe) { 
        updateStatus('Не задан символ или таймфрейм'); 
        return; 
    }

    const wsUrls = [
        "wss://ws.okx.com:8443/ws/v5/business",
        "wss://wsaws.okx.com:8443/ws/v5/business",
        "wss://wspap.okx.com:8443/ws/v5/business",
        "wss://ws.okx.com:8443/ws/v5/public",
        "wss://wsaws.okx.com:8443/ws/v5/public",
        "wss://wspap.okx.com:8443/ws/v5/public"
    ];
    
    let currentIndex = 0;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 10;

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

                const bar = timeframe;
                const channel = `candle${bar}`;
                const subscribeArg = { channel: channel, instId: symbol };

                if (wsUrl.includes('/business')) {
                    subscribeArg.instType = 'SPOT';
                }

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

                    // Отправка данных в Web Worker для обработки
                    if (window._dataWorker) {
                        window._dataWorker.postMessage({
                            type: 'processCandle',
                            data: data
                        });
                    } else {
                        // Fallback: обработка в основном потоке
                        processWebSocketData(data);
                    }
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

// ========== Обработка данных WebSocket (fallback) ==========
function processWebSocketData(data) {
    if (!data.data || !Array.isArray(data.data)) return;
    
    const now = Date.now();
    if (now - window._lastUpdateTime < window._updateThrottleMs) return;
    
    window._lastUpdateTime = now;
    
    try {
        data.data.forEach(candle => {
            const rawTs = candle[0];
            const timestamp = Math.floor(parseInt(rawTs) / 1000);
            const open = parseFloat(candle[1]);
            const high = parseFloat(candle[2]);
            const low = parseFloat(candle[3]);
            const close = parseFloat(candle[4]);
            const volume = parseFloat(candle[5]);
            
            if (window.charts && window.charts.candleSeries && window.charts.volumeSeries) {
                try {
                    window.charts.candleSeries.update({ time: timestamp, open, high, low, close });
                    window.charts.volumeSeries.update({ 
                        time: timestamp, 
                        value: volume, 
                        color: close >= open ? 'rgba(38,166,154,0.5)' : 'rgba(239,83,80,0.5)' 
                    });
                } catch (err) { 
                    console.error('[WS] Ошибка обновления серий:', err); 
                }
            }
        });
    } catch (error) {
        console.error('[WS] Ошибка обработки сообщения:', error, data);
    }
}

// ========== Отключение WebSocket ==========
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

// ========== Инициализация приложения ==========
function initializeApp() {
    try {
        // Инициализация Web Worker
        initDataWorker();
        
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
                    
                    // Запрос исторических данных с правильным URL
                    const apiUrl = getApiUrl(`api/historical-data/${encodeURIComponent(normalizedSymbol)}/${encodeURIComponent(normalizedTf)}`);
                    
                    console.log('[API] Запрос по URL:', apiUrl);
                    
                    fetch(apiUrl)
                        .then(response => {
                            if (!response.ok) {
                                return response.text().then(text => { 
                                    throw new Error(`HTTP ${response.status}: ${text}`) 
                                });
                            }
                            return response.json();
                        })
                        .then(data => {
                            if (data.error) {
                                handleError(data.error, 'загрузка исторических данных');
                                return;
                            }
                            
                            // Отправка данных в Web Worker для обработки
                            if (window._dataWorker) {
                                window._dataWorker.postMessage({
                                    type: 'processHistorical',
                                    data: data
                                });
                            } else {
                                // Fallback: обработка в основном потоке
                                window.charts = initChartsWithTypedArrays();
                                if (!window.charts) {
                                    updateStatus('Ошибка инициализации графиков');
                                    return;
                                }
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

// ========== Запуск приложения ==========
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    initializeApp();
}