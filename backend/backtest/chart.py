# chart.py
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import plotly.io as pio
import pandas as pd
from typing import Optional, List, Dict, Any


def plot_backtest(df: pd.DataFrame, trades: Optional[List[Dict[str, Any]]] = None, symbol: str = "BTC-USDT-SWAP") -> str:
    """
    Возвращает HTML-код Plotly графика (candles + volume + trades).
    df: DataFrame with timestamp, open, high, low, close, volume
    trades: list of dicts with keys: timestamp (datetime-like), price (float), side ('buy'/'sell'), optional text
    """
    # Ensure df timestamps are datetimes
    if df.empty:
        return "<div>No data to plot</div>"

    # create subplot: row1 = price, row2 = volume
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.75, 0.25], vertical_spacing=0.02)

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df["timestamp"],
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Price",
        increasing_line_color='green',
        decreasing_line_color='red',
        showlegend=True
    ), row=1, col=1)

    """
    # Volume as bars in row 2
    fig.add_trace(go.Bar(
        x=df["timestamp"],
        y=df["volume"],
        name="Volume",
        marker=dict(color='rgba(128,128,128,0.6)'),
        showlegend=False
    ), row=2, col=1)

    # Plot trades as markers
    
    if trades:
        buys = [t for t in trades if str(t.get("side", "")).lower() == "buy"]
        sells = [t for t in trades if str(t.get("side", "")).lower() == "sell"]

        if buys:
            fig.add_trace(go.Scatter(
                x=[t["timestamp"] for t in buys],
                y=[t["price"] for t in buys],
                mode="markers",
                marker=dict(symbol="triangle-up", size=10, color="lime"),
                name="Buys",
                hovertemplate="Buy<br>%{x}<br>Price: %{y}<extra></extra>"
            ), row=1, col=1)

        if sells:
            fig.add_trace(go.Scatter(
                x=[t["timestamp"] for t in sells],
                y=[t["price"] for t in sells],
                mode="markers",
                marker=dict(symbol="triangle-down", size=10, color="red"),
                name="Sells",
                hovertemplate="Sell<br>%{x}<br>Price: %{y}<extra></extra>"
            ), row=1, col=1)
    """
    # Layout improvements
    fig.update_layout(
        template="plotly_dark",
        title=f"{symbol} — Candles & Volume",
        xaxis=dict(rangeslider=dict(visible=False)),
        hovermode="x unified",
        height=800,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    # Make axes zoomable (wheel zoom)
    fig.update_xaxes(fixedrange=False)
    fig.update_yaxes(fixedrange=False)

    # Add range selector buttons (1d, 7d, 1m, all)
    fig.update_layout(
        xaxis=dict(
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1d", step="day", stepmode="backward"),
                    dict(count=7, label="7d", step="day", stepmode="backward"),
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(step="all")
                ])
            ),
            rangeslider=dict(visible=False),
            type="date"
        )
    )

    # Return embeddable HTML (no full_html wrapper)
    return pio.to_html(fig, full_html=False, include_plotlyjs=True)
