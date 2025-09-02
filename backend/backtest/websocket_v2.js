// assets/websocket.js

// ========== Глобальные переменные ==========
window.ws = null;
window.isConnected = false;
window.currentSymbol = 'BTC-USDT';
window.currentTimeframe = '1H';
window.charts = null;

window._resizeObserver = null;
window._timeRangeUnsub = null;
window._reconnectTimer = null;

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
    const ru = {'1 минута':'1m','1 мин':'1m','1м':'1m','5 минут':'5m','5 мин':'5m','15 минут':'15m','15 мин':'15m','1 час':'1H','1ч':'1H','4 часа':'4H','4 ч':'4H','1 день':'1D','1д':'1D'};
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
    } catch (e) { return '/'; }
}

function readDropdownValue(elem) {
    if (!elem) return null;
    const sel = elem.querySelector('select'); if (sel && sel.value) return sel.value;
    const input = elem.querySelector('input'); if (input && input.value) return input.value;
    const dv = elem.querySelector('[data-value]')?.dataset?.value; if (dv) return dv;
    const opt = elem.querySelector('[aria-selected="true"], .is-selected, .Select-value');
    if (opt) return opt.dataset?.value || opt.textContent?.trim() || null;
    const txt = elem.textContent?.trim(); return txt || null;
}

function updateStatus(message) {
    const statusElement = document.getElementById('status');
    if (statusElement) statusElement.textContent = message;
    console.log('[STATUS]', message);
}

function handleError(error, context) {
    console.error(`Ошибка в ${context}:`, error);
    updateStatus(`Ошибка: ${error && error.message ? error.message : error}`);
}

// ========== Инициализация графиков ==========
function initCharts(ohlcData, volumeData) {
    const chartElement = document.getElementById('chart');
    const volumeElement = document.getElementById('volume-chart');
    if (!chartElement || !volumeElement) { console.error('Элементы графиков не найдены'); return null; }
    chartElement.innerHTML = ''; volumeElement.innerHTML = '';
    if (typeof LightweightCharts === 'undefined') { console.error('LightweightCharts не загружена'); return null; }

    try {
        const rectChart = chartElement.getBoundingClientRect();
        const rectVol = volumeElement.getBoundingClientRect();
        const chartWidth = Math.max(1, Math.floor(rectChart.width || chartElement.clientWidth || 800));
        const chartHeight = Math.max(200, Math.floor(rectChart.height || 400));
        const volHeight = Math.max(100, Math.floor(rectVol.height || 150));

        const chart = LightweightCharts.createChart(chartElement, {
            width: chartWidth, height: chartHeight,
            layout: { background: { color: '#ffffff' }, textColor: '#333333' },
            grid: { vertLines: { color: '#f0f0f0' }, horzLines: { color: '#f0f0f0' } },
            timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#D1D4DC' },
            crosshair: { mode: LightweightCharts.CrosshairMode.Normal }
        });

        const candleSeries = chart.addCandlestickSeries({
            upColor: '#26a69a', downColor: '#ef5350', borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350'
        });
        candleSeries.setData(ohlcData || []);

        const volumeChart = LightweightCharts.createChart(volumeElement, {
            width: chartWidth, height: volHeight,
            layout: { background: { color: '#ffffff' }, textColor: '#333333' },
            grid: { vertLines: { color: '#f0f0f0' }, horzLines: { color: '#f0f0f0' } },
            timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#D1D4DC' }
        });

        const volumeSeries = volumeChart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: '', scaleMargins: { top: 0.85, bottom: 0 } });
        volumeSeries.setData(volumeData || []);

        if (window._timeRangeUnsub && typeof window._timeRangeUnsub === 'function') {
            try { window._timeRangeUnsub(); } catch (e) {}
            window._timeRangeUnsub = null;
        }

        const unsubA = chart.timeScale().subscribeVisibleTimeRangeChange(range => {
            try { volumeChart.timeScale().setVisibleRange(range); } catch (e) {}
        });
        const unsubB = volumeChart.timeScale().subscribeVisibleTimeRangeChange(range => {
            try { chart.timeScale().setVisibleRange(range); } catch (e) {}
        });
        window._timeRangeUnsub = () => {
            try { chart.timeScale().unsubscribeVisibleTimeRangeChange(unsubA); } catch (e) {}
            try { volumeChart.timeScale().unsubscribeVisibleTimeRangeChange(unsubB); } catch (e) {}
        };

        if (window._resizeObserver) { try { window._resizeObserver.disconnect(); } catch (e) {} window._resizeObserver = null; }
        window._resizeObserver = new ResizeObserver(entries => {
            for (const entry of entries) {
                const w = Math.max(1, Math.floor(entry.contentRect.width || chartElement.clientWidth));
                const hChart = Math.max(200, Math.floor(document.getElementById('chart').getBoundingClientRect().height || 400));
                const hVol = Math.max(100, Math.floor(document.getElementById('volume-chart').getBoundingClientRect().height || 150));
                try { chart.resize(w, hChart); volumeChart.resize(w, hVol); } catch (e) {}
            }
        });
        const parent = chartElement.parentElement || chartElement;
        try { window._resizeObserver.observe(parent); } catch (e) {}

        try { chart.timeScale().scrollToRealTime(); } catch (e) {}

        return { chart, volumeChart, candleSeries, volumeSeries };
    } catch (error) {
        console.error('Ошибка при создании графиков:', error);
        return null;
    }
}

// ========== WebSocket подключение ==========
function connectWebSocket(symbol, timeframe, candleSeries, volumeSeries) {
    if (window.ws) {
        try { window.ws.onopen = window.ws.onmessage = window.ws.onerror = window.ws.onclose = null; window.ws.close(); } catch (e) {}
        window.ws = null; window.isConnected = false;
    }
    if (!symbol || !timeframe) { updateStatus('Не задан символ или таймфрейм'); return; }

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

    function scheduleReconnect() {
        if (window._reconnectTimer) { clearTimeout(window._reconnectTimer); window._reconnectTimer = null; }
        const backoff = Math.min(60000, 1000 * Math.pow(2, Math.min(reconnectAttempts, 6)));
        const jitter = Math.floor(Math.random() * 500);
        const delay = backoff + jitter;
        console.log(`[WS] планируем reconnect через ${delay}ms (attempt ${reconnectAttempts})`);
        window._reconnectTimer = setTimeout(() => { reconnectAttempts++; doConnect(); }, delay);
    }

    function doConnect() {
        if (currentIndex >= wsUrls.length) { currentIndex = 0; reconnectAttempts++; }
        const wsUrl = wsUrls[currentIndex];
        console.log(`[WS] Попытка подключения: ${wsUrl}`);
        updateStatus(`Подключение к ${wsUrl}...`);

        try {
            window.ws = new WebSocket(wsUrl);

            window.ws.onopen = function() {
                console.log('[WS] open', wsUrl);
                window.isConnected = true; reconnectAttempts = 0;
                updateStatus(`Подключено к ${symbol} (${timeframe})`);

                const bar = mapTimeframeToOkxBar(timeframe);
                const channel = `candle${bar}`;

                // Формируем аргумент подписки
                const subscribeArg = { channel: channel, instId: symbol };

                // Если это business endpoint, иногда требует instType (например SPOT/SWAP/FUTURES)
                try {
                    if (wsUrl.includes('/business')) {
                        // по умолчанию пробуем SPOT — если нужно, сервер вернёт ошибку и мы переключимся
                        subscribeArg.instType = 'SPOT';
                    }
                } catch (e) {}

                // Важно: НЕ отправляем top-level 'id' — OKX business может вернуть 60033 (Parameter id error)
                const subscribeMessage = { op: "subscribe", args: [ subscribeArg ] };

                try {
                    window.ws.send(JSON.stringify(subscribeMessage));
                    console.log('[WS] отправлен subscribe:', subscribeMessage);
                } catch (e) {
                    console.error('[WS] не удалось отправить subscribe', e);
                }
            };

            window.ws.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);

                    if (data.event === 'subscribe' || data.event === 'error') {
                        console.log('[WS] subscribe response:', data);
                        if (data.event === 'error') {
                            console.error('[WS] subscribe error:', data);
                            const msg = (data.msg || '').toLowerCase();
                            if (msg.includes('wrong url') || msg.includes('wrong channel') || msg.includes('parameter') || (data.code && String(data.code).startsWith('6'))) {
                                console.warn('[WS] Ошибка подписки указывает на некорректный endpoint/channel/params — переключаемся');
                                try { window.ws.close(); } catch (e) {}
                                currentIndex++;
                                scheduleReconnect();
                            }
                        }
                        return;
                    }

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
                                        color: close >= open ? 'rgba(38, 166, 154, 0.5)' : 'rgba(239, 83, 80, 0.5)'
                                    });
                                } catch (err) {
                                    console.error('[WS] update series error:', err);
                                }
                            }
                        });
                    }
                } catch (error) {
                    console.error('[WS] Ошибка обработки сообщения:', error, event && event.data);
                }
            };

            window.ws.onerror = function(err) {
                console.error('[WS] onerror', err);
                currentIndex++;
                scheduleReconnect();
            };

            window.ws.onclose = function(ev) {
                console.log('[WS] onclose', ev && ev.code, ev && ev.reason);
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

function disconnectWebSocket() {
    if (window.ws) {
        try { window.ws.close(); } catch (e) {}
        window.ws = null;
    }
    window.isConnected = false;
    updateStatus('Отключено');
    if (window._reconnectTimer) { clearTimeout(window._reconnectTimer); window._reconnectTimer = null; }
}

// ========== UI и инициализация ==========
function initializeApp() {
    try {
        const checkElements = setInterval(() => {
            const connectButton = document.getElementById('connect-button');
            const disconnectButton = document.getElementById('disconnect-button');
            const symbolSelector = document.getElementById('symbol-selector');
            const timeframeSelector = document.getElementById('timeframe-selector');

            if (connectButton && disconnectButton && symbolSelector && timeframeSelector) {
                clearInterval(checkElements);

                const initialSymbol = readDropdownValue(symbolSelector) || 'BTC-USDT';
                const initialTimeframe = readDropdownValue(timeframeSelector) || '1H';
                window.currentSymbol = initialSymbol;
                window.currentTimeframe = initialTimeframe;

                console.log('Инициализация приложения:', { symbol: window.currentSymbol, timeframe: window.currentTimeframe });

                connectButton.addEventListener('click', function() {
                    if (window.isConnected) { updateStatus('Уже подключено'); return; }
                    if (!window.currentSymbol || !window.currentTimeframe) { handleError('Не выбраны символ или таймфрейм', 'подключение'); return; }

                    updateStatus('Загрузка исторических данных...');

                    const rawSymbol = window.currentSymbol;
                    const rawTimeframe = window.currentTimeframe;
                    const normalizedSymbol = normalizeSymbol(rawSymbol);
                    const normalizedTimeframe = normalizeTimeframe(rawTimeframe);
                    console.log('[normalize] rawSymbol=', rawSymbol, '->', normalizedSymbol, 'rawTimeframe=', rawTimeframe, '->', normalizedTimeframe);

                    const prefix = getDashRequestsPathnamePrefix();
                    const base = prefix === '/' ? '' : prefix;
                    const apiUrl = `${base}/api/historical-data/${encodeURIComponent(normalizedSymbol)}/${encodeURIComponent(normalizedTimeframe)}`;
                    console.log('[fetch] apiUrl =', apiUrl);

                    fetch(apiUrl)
                        .then(response => {
                            console.log('[fetch] status:', response.status, 'content-type:', response.headers.get('content-type'));
                            if (!response.ok) { return response.text().then(text => { throw new Error(`HTTP ${response.status} - ${text}`); }); }
                            const ct = (response.headers.get('content-type') || '').toLowerCase();
                            if (!ct.includes('application/json')) {
                                return response.text().then(text => { console.error('[fetch] Non-JSON response body:', text); throw new Error('Non-JSON response from /api/historical-data. See console for body.'); });
                            }
                            return response.json();
                        })
                        .then(data => {
                            if (data.error) { handleError(data.error, 'загрузка исторических данных'); return; }
                            window.charts = initCharts(data.ohlc, data.volume);
                            if (window.charts) {
                                connectWebSocket(normalizedSymbol, normalizedTimeframe, window.charts.candleSeries, window.charts.volumeSeries);
                            } else {
                                updateStatus('Ошибка инициализации графиков');
                            }
                        })
                        .catch(error => { handleError(error, 'загрузка исторических данных'); });
                });

                disconnectButton.addEventListener('click', function() {
                    if (window.isConnected) { disconnectWebSocket(); } else { updateStatus('Не подключено'); }
                });

                const updateSelectValues = () => {
                    const sym = readDropdownValue(symbolSelector);
                    const tf = readDropdownValue(timeframeSelector);
                    if (sym) window.currentSymbol = sym;
                    if (tf) window.currentTimeframe = tf;
                    console.log('Обновление значений (raw):', { symbol: window.currentSymbol, timeframe: window.currentTimeframe });
                };

                const observer = new MutationObserver(updateSelectValues);
                observer.observe(symbolSelector, { childList: true, subtree: true, attributes: true });
                observer.observe(timeframeSelector, { childList: true, subtree: true, attributes: true });

                symbolSelector.addEventListener('click', updateSelectValues);
                timeframeSelector.addEventListener('click', updateSelectValues);
            }
        }, 100);
    } catch (error) { handleError(error, 'инициализация приложения'); }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else { initializeApp(); }
