import aiohttp
import pandas as pd
from datetime import datetime, timedelta

async def fetch_okx_candles(symbol: str, bar: str, start: datetime, end: datetime):
    """
    Загружает исторические свечи с OKX для бессрочных фьючерсов (USDT-SWAP).
    symbol: 'BTC' -> 'BTC-USDT-SWAP'
    bar: 1m, 5m, 15m, 1H, 1D
    start, end: datetime
    """
    inst_id = f"{symbol.upper()}-USDT-SWAP"
    url = "https://www.okx.com/api/v5/market/history-candles"
    all_data = []

    async with aiohttp.ClientSession() as session:
        current_end = end
        while True:
            params = {
                "instId": inst_id,
                "bar": bar,
                "limit": "300",
                "after": int(current_end.timestamp() * 1000)
            }
            async with session.get(url, params=params) as resp:
                data = await resp.json()
            if not data.get("data"):
                break

            batch = pd.DataFrame(data["data"], columns=[
                "ts", "open", "high", "low", "close", "volume_base", "volume_quote", "volume_usdt", "confirm"
            ])
            batch["timestamp"] = pd.to_datetime(batch["ts"], unit="ms")
            batch = batch.astype({
                "open": float, "high": float, "low": float, "close": float, "volume_base": float
            })
            all_data.append(batch[["timestamp", "open", "high", "low", "close", "volume_base"]])

            oldest_ts = batch["timestamp"].min()
            if oldest_ts <= start:
                break
            current_end = oldest_ts - timedelta(milliseconds=1)

    if not all_data:
        return pd.DataFrame()

    df = pd.concat(all_data, ignore_index=True).sort_values("timestamp")
    return df[df["timestamp"] >= start]
