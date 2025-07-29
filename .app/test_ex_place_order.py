import asyncio
import json, hmac, base64, hashlib, httpx, math
import os
from pathlib import Path
from datetime import datetime, timezone

BASE_URL = "https://www.okx.com"
ENDPOINT = "/api/v5/trade/order"

def load_okx_config():
    cfg_path = os.path.join(os.path.dirname(__file__), "okx_config.json")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)

async def get_ct_val(inst_id: str = "BTC-USDT-SWAP") -> float:
    url = f"{BASE_URL}/api/v5/public/instruments"
    params = {"instType": "SWAP", "instId": inst_id}
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()["data"]
    if not data:
        raise ValueError(f"{inst_id} not found in public instruments")
    return float(data[0]["ctVal"])

async def place_limit_order_usd(
    price: float = 50_000,
    usd_amount: float = 100,
    inst_id: str = "BTC-USDT-SWAP"
) -> dict:
    cfg = load_okx_config()
    td_mode = cfg.get("td_mode", "cross")
    ct_val = await get_ct_val(inst_id)

    raw_contracts = usd_amount / (price * ct_val)
    contracts = max(1, math.floor(raw_contracts))

    print(f"[DEBUG] ctVal={ct_val}, price={price}, usd_amount={usd_amount}, raw={raw_contracts:.4f}, sz={contracts}")

    body = {
        "instId": inst_id,
        "tdMode": td_mode,
        "side": "buy",
        "ordType": "limit",
        "px": str(price),
        "sz": str(contracts)
    }
    body_str = json.dumps(body, separators=(",",":"))

    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")
    to_sign = ts + "POST" + ENDPOINT + body_str
    sign = base64.b64encode(
        hmac.new(cfg["secret_key"].encode(), to_sign.encode(), hashlib.sha256).digest()
    ).decode()

    headers = {
        "Content-Type": "application/json",
        "OK-ACCESS-KEY": cfg["api_key"],
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": cfg["passphrase"],
    }
    if cfg.get("demo"):
        headers["x-simulated-trading"] = "1"

    async with httpx.AsyncClient() as client:
        resp = await client.post(BASE_URL + ENDPOINT, headers=headers, content=body_str, timeout=10)
    data = resp.json()

    # Если не прошло — выбрасываем понятное исключение
    if data.get("code") != "0":
        # sCode внутри data["data"][0]["sCode"]
        first = data.get("data", [{}])[0]
        raise RuntimeError(
            f"OKX error {first.get('sCode')}: {first.get('sMsg')}. "
            "Проверь, включён ли у API-ключа режим фьючерсов и правильный ли td_mode."
        )

    return data

async def main():
    try:
        result = await place_limit_order_usd(price=50000, usd_amount=100)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"❌ Ошибка при размещении ордера: {e}")

if __name__ == "__main__":
    asyncio.run(main())
