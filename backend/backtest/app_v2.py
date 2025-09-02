from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
import plotly.graph_objects as go
import asyncio

from fetch_okx import fetch_okx_candles
from backtest import BacktestRunner
from strategy_v1 import SimpleStrategy

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, symbol: str = "BTC", bar: str = "1H", start: str = "", end: str = ""):
    plot_html = None

    if symbol and start and end:
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")

        df = await fetch_okx_candles(symbol, bar, start_dt, end_dt)

        if not df.empty:
            strategy = SimpleStrategy()
            runner = BacktestRunner(strategy, df)
            runner.run()

            fig = go.Figure(data=[go.Candlestick(
                x=df["timestamp"],
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"]
            )])
            fig.update_layout(title=f"{symbol.upper()}-USDT-SWAP ({bar})", xaxis_rangeslider_visible=False)
            plot_html = fig.to_html(full_html=False)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "symbol": symbol,
        "bar": bar,
        "start": start,
        "end": end,
        "plot_html": plot_html
    })
