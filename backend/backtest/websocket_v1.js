// === file: websocket.js ===
// assets/websocket.js

// Глобальные переменные для хранения состояния
window.ws = null;
window.isConnected = false;
window.currentSymbol = 'BTC-USDT';
window.currentTimeframe = '1H';
window.charts = null;

// Функция инициализации графиков
function initCharts(ohlcData, volumeData) {
    // Очищаем предыдущие графики
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
        // Создаем основной график
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
        candleSeries.setData(ohlcData);
        
        // Создаем график объема
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
            priceFormat: {
                type: 'volume',
            },
            priceScaleId: '',
        });
        
        volumeSeries.setData(volumeData);
        
        // Синхронизируем масштабирование
        chart.timeScale().subscribeVisibleTimeRangeChange(range => {
            volumeChart.timeScale().setVisibleRange(range);
        });
        
        // Автоматически скроллим к самым новым данным
        chart.timeScale().scrollToPosition(5, false);
        
        return { chart, volumeChart, candleSeries, volumeSeries };
    } catch (error) {
        console.error('Ошибка при создании графиков:', error);
        return null;
    }
}

// Функция подключения к WebSocket
function connectWebSocket(symbol, timeframe, candleSeries, volumeSeries) {
    if (window.ws) {
        window.ws.close();
    }
    
    // Альтернативные WebSocket endpoints OKX
    const wsUrls = [
        "wss://ws.okx.com:8443/ws/v5/public",
        "wss://wsaws.okx.com:8443/ws/v5/public",
        "wss://wspap.okx.com:8443/ws/v5/public"
    ];
    
    let currentWsUrlIndex = 0;
    
    const connect = () => {
        if (currentWsUrlIndex >= wsUrls.length) {
            console.error('Не удалось подключиться ни к одному из WebSocket endpoints');
            updateStatus('Ошибка подключения к WebSocket');
            return;
        }
        
        const wsUrl = wsUrls[currentWsUrlIndex];
        console.log(`Попытка подключения к WebSocket: ${wsUrl}`);
        updateStatus(`Подключение к ${wsUrl}...`);
        
        try {
            window.ws = new WebSocket(wsUrl);
            
            window.ws.onopen = function() {
                console.log('WebSocket подключен');
                window.isConnected = true;
                updateStatus(`Подключено к ${symbol} (${timeframe})`);
                
                // Подписываемся на канал свечей
                const subscribeMessage = {
                    "op": "subscribe",
                    "args": [{
                        "channel": "candles",
                        "instId": symbol
                    }]
                };
                
                window.ws.send(JSON.stringify(subscribeMessage));
                console.log('Отправлен запрос на подписку:', subscribeMessage);
            };
            
            window.ws.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    
                    if (data.event === 'subscribe') {
                        console.log('Успешно подписались на канал:', data);
                    } else if (data.data) {
                        // Обрабатываем данные свечи
                        data.data.forEach(candle => {
                            const timestamp = parseInt(candle[0]) / 1000;
                            const open = parseFloat(candle[1]);
                            const high = parseFloat(candle[2]);
                            const low = parseFloat(candle[3]);
                            const close = parseFloat(candle[4]);
                            const volume = parseFloat(candle[5]);
                            
                            // Обновляем график
                            if (candleSeries && volumeSeries) {
                                candleSeries.update({
                                    time: timestamp,
                                    open: open,
                                    high: high,
                                    low: low,
                                    close: close
                                });
                                
                                volumeSeries.update({
                                    time: timestamp,
                                    value: volume,
                                    color: close > open ? 'rgba(38, 166, 154, 0.5)' : 'rgba(239, 83, 80, 0.5)'
                                });
                            }
                        });
                    }
                } catch (error) {
                    console.error('Ошибка обработки сообщения WebSocket:', error);
                }
            };
            
            window.ws.onerror = function(error) {
                console.error('WebSocket ошибка:', error);
                currentWsUrlIndex++;
                setTimeout(connect, 1000);
            };
            
            window.ws.onclose = function() {
                console.log('WebSocket соединение закрыто');
                window.isConnected = false;
                updateStatus('Отключено');
                
                // Попытка переподключения через 5 секунд
                if (currentWsUrlIndex < wsUrls.length) {
                    setTimeout(connect, 5000);
                }
            };
        } catch (error) {
            console.error('Ошибка создания WebSocket:', error);
            currentWsUrlIndex++;
            setTimeout(connect, 1000);
        }
    };
    
    connect();
}

// Функция отключения от WebSocket
function disconnectWebSocket() {
    if (window.ws) {
        window.ws.close();
        window.ws = null;
    }
    window.isConnected = false;
    updateStatus('Отключено');
}

// Функция обновления статуса
function updateStatus(message) {
    const statusElement = document.getElementById('status');
    if (statusElement) {
        statusElement.textContent = message;
    }
}

// Функция обработки ошибок
function handleError(error, context) {
    console.error(`Ошибка в ${context}:`, error);
    updateStatus(`Ошибка: ${error.message || error}`);
}

// Инициализация при полной загрузке страницы
function initializeApp() {
    try {
        // Ждем пока все элементы будут доступны
        const checkElements = setInterval(() => {
            const connectButton = document.getElementById('connect-button');
            const disconnectButton = document.getElementById('disconnect-button');
            const symbolSelector = document.getElementById('symbol-selector');
            const timeframeSelector = document.getElementById('timeframe-selector');
            
            if (connectButton && disconnectButton && symbolSelector && timeframeSelector) {
                clearInterval(checkElements);
                
                // Устанавливаем начальные значения из атрибутов данных
                const initialSymbol = symbolSelector.querySelector('.Select-value')?.dataset?.value || 'BTC-USDT';
                const initialTimeframe = timeframeSelector.querySelector('.Select-value')?.dataset?.value || '1H';
                
                window.currentSymbol = initialSymbol;
                window.currentTimeframe = initialTimeframe;
                
                console.log('Инициализация приложения:', {
                    symbol: window.currentSymbol,
                    timeframe: window.currentTimeframe
                });
                
                // Обработчики событий для кнопок
                connectButton.addEventListener('click', function() {
                    if (!window.isConnected) {
                        console.log('Клик по подключению:', {
                            symbol: window.currentSymbol,
                            timeframe: window.currentTimeframe
                        });
                        
                        // Проверяем, что символ и таймфрейм выбраны
                        if (!window.currentSymbol || !window.currentTimeframe) {
                            handleError('Не выбраны символ или таймфрейм', 'подключение');
                            return;
                        }
                        
                        updateStatus('Загрузка исторических данных...');
                        
                        // Запрашиваем исторические данные
                        fetch(`/api/historical-data/${window.currentSymbol}/${window.currentTimeframe}`)
                            .then(response => response.json())
                            .then(data => {
                                if (data.error) {
                                    handleError(data.error, 'загрузка исторических данных');
                                    return;
                                }
                                
                                // Инициализируем графики
                                window.charts = initCharts(data.ohlc, data.volume);
                                
                                if (window.charts) {
                                    // Подключаемся к WebSocket
                                    connectWebSocket(window.currentSymbol, window.currentTimeframe, window.charts.candleSeries, window.charts.volumeSeries);
                                } else {
                                    updateStatus('Ошибка инициализации графиков');
                                }
                            })
                            .catch(error => {
                                handleError(error, 'загрузка исторических данных');
                            });
                    }
                });
                
                disconnectButton.addEventListener('click', function() {
                    if (window.isConnected) {
                        disconnectWebSocket();
                    }
                });
                
                // Функция для обновления значений при изменении выпадающих списков
                const updateSelectValues = () => {
                    const symbolValue = symbolSelector.querySelector('.Select-value')?.dataset?.value;
                    const timeframeValue = timeframeSelector.querySelector('.Select-value')?.dataset?.value;
                    
                    if (symbolValue) window.currentSymbol = symbolValue;
                    if (timeframeValue) window.currentTimeframe = timeframeValue;
                    
                    console.log('Обновление значений:', {
                        symbol: window.currentSymbol,
                        timeframe: window.currentTimeframe
                    });
                };
                
                // Наблюдаем за изменениями в выпадающих списках
                const observer = new MutationObserver(updateSelectValues);
                
                // Начинаем наблюдение за изменениями в выпадающих списках
                observer.observe(symbolSelector, { 
                    childList: true, 
                    subtree: true,
                    attributes: true,
                    attributeFilter: ['class', 'data-value']
                });
                
                observer.observe(timeframeSelector, { 
                    childList: true, 
                    subtree: true,
                    attributes: true,
                    attributeFilter: ['class', 'data-value']
                });
                
                // Также обновляем значения при клике на выпадающие списки
                symbolSelector.addEventListener('click', updateSelectValues);
                timeframeSelector.addEventListener('click', updateSelectValues);
            }
        }, 100);
    } catch (error) {
        handleError(error, 'инициализация приложения');
    }
}

// Инициализируем приложение когда страница полностью загружена
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    initializeApp();
}