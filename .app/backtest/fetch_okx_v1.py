# fetch_okx.py (updated)
import aiohttp
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import math
import logging

logger = logging.getLogger("fetch_okx")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(ch)


async def fetch_okx_candles(symbol_short: str, bar: str, start: datetime, end: datetime) -> pd.DataFrame:
    """
    Fetch OKX history-candles safely using forward pagination (after).
    symbol_short: 'BTC' -> 'BTC-USDT-SWAP'
    bar: '1m','5m','15m','1H','1D' etc.
    start/end: naive or tz-aware datetimes (we convert to UTC)
    Returns DataFrame with columns: timestamp(open->datetime UTC), open, high, low, close, volume
    """
    inst_id = f"{symbol_short.upper()}-USDT-SWAP"
    url = "https://www.okx.com/api/v5/market/history-candles"
    limit = 300

    # Normalize start/end to UTC timezone-aware datetimes
    if start.tzinfo is None:
        start_utc = start.replace(tzinfo=timezone.utc)
    else:
        start_utc = start.astimezone(timezone.utc)

    if end.tzinfo is None:
        end_utc = end.replace(tzinfo=timezone.utc)
    else:
        end_utc = end.astimezone(timezone.utc)

    # Safety checks
    if start_utc > end_utc:
        raise ValueError("start must be <= end")

    rows: List[list] = []
    # We will use 'after' param to page forward starting from start_utc
    cursor = int(start_utc.timestamp() * 1000) - 1  # after = timestamp(ms) -> start after this ms
    fetched_total = 0

    async with aiohttp.ClientSession() as session:
        while True:
            params = {
                "instId": inst_id,
                "bar": bar,
                "limit": str(limit),
                "after": str(cursor)
            }
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    status = resp.status
                    data = await resp.json()
            except Exception as e:
                logger.exception("HTTP request failed")
                raise RuntimeError(f"Failed to fetch OKX candles: {e}")

            if status != 200:
                logger.warning(f"OKX returned status {status}; response: {data}")
                # In case of rate-limit or API errors, break/raise
                raise RuntimeError(f"OKX HTTP status {status}")

            batch = data.get("data") or []
            logger.info(f"Fetched batch size={len(batch)} (after cursor={cursor})")

            if not batch:
                break

            # OKX returns newest-first when using after? Historically it's newest-first in some endpoints;
            # but we'll append all and deduplicate/sort later. Each item is list: [ts,o,h,l,c,vol,...]
            for item in batch:
                if len(item) < 6:
                    continue
                # take first 6 fields: ts(ms), o,h,l,c,vol
                rows.append(item[:6])
                fetched_total += 1

            # Determine the maximum timestamp in this batch (newest)
            # batch elements may be returned newest-first; convert timestamps and find max
            try:
                batch_ts = [int(x[0]) for x in batch if len(x) >= 1]
                max_ts = max(batch_ts)
                # Move cursor forward to max_ts to avoid re-fetching the same candles.
                # Use max_ts to fetch next candles after this timestamp.
                cursor = max_ts
            except Exception:
                # If parsing fails — break to avoid infinite loop
                break

            # Stop if we've passed 'end'
            if cursor >= int(end_utc.timestamp() * 1000):
                logger.info("Reached or passed end timestamp in paging loop, stopping pagination.")
                break

            # Safety safeguard: if we've fetched way too many records, stop
            if fetched_total > 1000000:
                logger.warning("Too many records fetched, aborting to avoid runaway.")
                break

    if not rows:
        logger.info("No rows fetched from OKX")
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    # Build DataFrame
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["ts"].astype(int), unit="ms", utc=True)
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    # Cast to numeric
    df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)

    # Filter by requested [start_utc, end_utc] inclusive and sort ascending
    df = df[(df["timestamp"] >= pd.to_datetime(start_utc)) & (df["timestamp"] <= pd.to_datetime(end_utc))]
    df = df.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp").reset_index(drop=True)

    logger.info(f"Returning {len(df)} candles for {inst_id} {bar} between {start_utc} and {end_utc}")
    return df
