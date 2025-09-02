# app.py
import uuid
import os
import asyncio
from pathlib import Path
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from decimal import Decimal
import pandas as pd
import plotly.io as pio

# Импорты бэктест-раннера и стратегий из локальной структуры проекта.
# Предполагается, что у тебя в проекте есть:
# - backtest/runner.py (BacktestRunner)
# - strategies/sma_strategy.py (SmaStrategy) или другая стратегия
# - models.coin.Coin
#
# Если пути отличаются — поправь импорты.
from models.coin import Coin
from strategies.sma_strategy import SmaStrategy
from backtest.runner import BacktestRunner

BASE_DIR = Path(__file__).parent.resolve()
UPLOAD_DIR = BASE_DIR / "uploads"
RESULTS_DIR = BASE_DIR / "results"
UPLOAD_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

app = FastAPI()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/results", StaticFiles(directory=str(RESULTS_DIR)), name="results")

# In-memory tasks storage (подходит для прототипа)
TASKS = {}  # task_id -> {"status": "running"/"done"/"error", "result_html": path, "metrics": {...}, "error": str}

async def run_backtest_task(task_id: str, csv_path: str, fast: int, slow: int, size: str):
    """Фоновая корутина, которая запускает BacktestRunner и сохраняет результат как HTML."""
    try:
        # Загружаем CSV через pandas, ожидаем колонки: timestamp,open,high,low,close,volume
        df = pd.read_csv(csv_path)
        candles = []
        for _, r in df.iterrows():
            try:
                ts = pd.to_datetime(r["timestamp"])
            except Exception:
                ts = pd.Timestamp.utcnow()
            candles.append({
                "timestamp": ts.to_pydatetime(),
                "open": Decimal(str(r["open"])),
                "high": Decimal(str(r["high"])),
                "low": Decimal(str(r["low"])),
                "close": Decimal(str(r["close"])),
                "volume": Decimal(str(r.get("volume", 0)))
            })

        coin = Coin("BTC")  # можно расширить выбор монеты из формы
        strategy = SmaStrategy(coin, fast=int(fast), slow=int(slow), order_size=Decimal(size))

        runner = BacktestRunner(candles, coin, strategy, fee_rate=Decimal("0.0005"), slippage=Decimal("0.0"))
        result = await runner.run()  # асинхронный запуск

        # подготовка DataFrame для визуализации
        df_plot = pd.DataFrame(candles).set_index("timestamp").astype(float)
        trades = pd.DataFrame(runner.trade_history)
        # постобработка trades (если пустой DataFrame, помним об этом)
        if not trades.empty:
            trades['timestamp'] = pd.to_datetime(trades['timestamp'])
            trades['price'] = trades['price'].astype(float)
            trades['size'] = trades['size'].astype(float)

        # строим Plotly-диаграмму (candlestick + маркеры сделок)
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df_plot.index, open=df_plot['open'], high=df_plot['high'],
            low=df_plot['low'], close=df_plot['close'], name='Candles'))

        if not trades.empty:
            buys = trades[trades['size'] > 0]
            sells = trades[trades['size'] < 0]
            if not buys.empty:
                fig.add_trace(go.Scatter(x=buys['timestamp'], y=buys['price'],
                                         mode='markers', name='Buys',
                                         marker_symbol='triangle-up', marker_size=9))
            if not sells.empty:
                fig.add_trace(go.Scatter(x=sells['timestamp'], y=sells['price'],
                                         mode='markers', name='Sells',
                                         marker_symbol='triangle-down', marker_size=9))

        fig.update_layout(title=f"Backtest {task_id}", xaxis_rangeslider_visible=False)

        html_path = RESULTS_DIR / f"{task_id}.html"
        pio.write_html(fig, file=str(html_path), auto_open=False)

        TASKS[task_id]['status'] = 'done'
        TASKS[task_id]['result_html'] = f"/results/{task_id}.html"
        # краткие метрики: число сделок и позиция/профит по PositionManager
        TASKS[task_id]['metrics'] = {
            "trades": len(runner.trade_history),
            "positions": {pid: p.to_dict() for pid, p in runner.position_manager.positions.items()}
        }
    except Exception as e:
        TASKS[task_id]['status'] = 'error'
        TASKS[task_id]['error'] = repr(e)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "tasks": TASKS})

@app.post("/start_backtest")
async def start_backtest(request: Request, csv_file: UploadFile = File(...), fast: int = Form(20), slow: int = Form(50), size: str = Form("0.001")):
    # Сохранение файла
    task_id = str(uuid.uuid4())[:8]
    filename = f"{task_id}_{csv_file.filename}"
    out_path = UPLOAD_DIR / filename
    content = await csv_file.read()
    out_path.write_bytes(content)

    TASKS[task_id] = {"status": "running", "result_html": None, "metrics": None, "error": None}
    # Запуск фоновой задачи (не блокирует обработчик)
    asyncio.create_task(run_backtest_task(task_id, str(out_path), fast, slow, size))
    return RedirectResponse(url=f"/", status_code=303)

@app.get("/task/{task_id}", response_class=HTMLResponse)
async def task_status(request: Request, task_id: str):
    task = TASKS.get(task_id)
    if not task:
        return HTMLResponse("Task not found", status_code=404)
    return templates.TemplateResponse("task.html", {"request": request, "task_id": task_id, "task": task})
