# app.py
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from typing import Optional
import traceback

from fetch_okx import fetch_okx_candles
from chart import plot_backtest

# Простейшая примерная стратегия — оставляю твою логику замены/интеграции
def simple_trades_from_df(df):
    """
    Возвращает список trades примерной структуры:
    {'timestamp': pd.Timestamp, 'price': float, 'side': 'buy'/'sell'}
    Здесь делаем простую демонстрацию: помечаем локальные экстремумы или просто цвет свечи.
    """
    trades = []
    for _, r in df.iterrows():
        if r['close'] > r['open']:
            trades.append({"timestamp": r['timestamp'], "price": float(r['close']), "side": "buy"})
        elif r['close'] < r['open']:
            trades.append({"timestamp": r['timestamp'], "price": float(r['close']), "side": "sell"})
    return trades


app = FastAPI()
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request,
                symbol: Optional[str] = None,
                bar: str = "1H",
                start: Optional[str] = None,
                end: Optional[str] = None):
    """
    Если не заданы symbol/start/end — показываем форму (шаблон),
    иначе загружаем данные и рисуем Plotly-график.
    """
    error = None
    plot_html = None
    df = None

    # Если нет обязательных параметров — показываем форму
    if not (symbol and start and end):
        return templates.TemplateResponse("index.html", {"request": request, "plot_html": None, "error": None,
                                                         "symbol": symbol or "", "bar": bar, "start": start or "", "end": end or ""})

    # Парсим даты
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        # inclusive end: add one day to end_dt so that API 'before' includes that day end
        # but our fetch_okx uses before=end, and filtering afterwards ensures inclusive end
    except Exception as e:
        error = f"Invalid date format: {e}"
        return templates.TemplateResponse("index.html", {"request": request, "plot_html": None, "error": error,
                                                         "symbol": symbol, "bar": bar, "start": start, "end": end})

    # fetch candles
    try:
        df = await fetch_okx_candles(symbol, bar, start_dt, end_dt)
        if df is None or df.empty:
            error = "No data returned for given parameters (check symbol/bar/period)."
            return templates.TemplateResponse("index.html", {"request": request, "plot_html": None, "error": error,
                                                             "symbol": symbol, "bar": bar, "start": start, "end": end})
    except Exception as e:
        tb = traceback.format_exc()
        error = f"Failed to fetch candles: {e}"
        # show more detailed trace for debugging in template
        return templates.TemplateResponse("index.html", {"request": request, "plot_html": None, "error": error + "<pre>" + tb + "</pre>",
                                                         "symbol": symbol, "bar": bar, "start": start, "end": end})

    # Build trades (for now simple placeholder — plug your strategy here)
    trades = simple_trades_from_df(df)

    # Build chart
    try:
        plot_html = plot_backtest(df, trades, f"{symbol.upper()}-USDT-SWAP")
    except Exception as e:
        tb = traceback.format_exc()
        error = f"Failed to render chart: {e}"
        return templates.TemplateResponse("index.html", {"request": request, "plot_html": None, "error": error + "<pre>" + tb + "</pre>",
                                                         "symbol": symbol, "bar": bar, "start": start, "end": end})

    return templates.TemplateResponse("index.html", {"request": request, "plot_html": plot_html, "error": None,
                                                     "symbol": symbol, "bar": bar, "start": start, "end": end})
