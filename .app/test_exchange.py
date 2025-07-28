# === file: test_exchange.py ===
import os
import json
import pytest
import asyncio
import aiohttp
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

from exchange import OkxExchange

# Path to config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "okx_config.json")

@pytest.fixture
def mock_config(tmp_path, monkeypatch):
    """
    Fixture to create a temporary okx_config.json and patch its path.
    """
    config = {
        "api_key": "test_api_key",
        "secret_key": "test_secret_key",
        "passphrase": "test_passphrase",
        "demo": True,
        "symbol": "BTC-USDT",
        "grid_num": 5,
        "grid_step_pct": 1.0,
        "order_amount_usdt": 10,
        "leverage": 10
    }
    config_path = tmp_path / "okx_config.json"
    with open(config_path, 'w') as f:
        json.dump(config, f)
    # Force Exchange to load this config
    monkeypatch.setenv('OKX_CONFIG_PATH', str(config_path))
    return config_path

@pytest.fixture
async def exchange(mock_config, monkeypatch):
    """
    Fixture to instantiate OkxExchange with mocked HTTP session and logger.
    """
    # Patch logger
    monkeypatch.patch('exchange.Utils.get_logger', return_value=MagicMock())
    # Initialize exchange
    ex = OkxExchange()
    # Mock internal session
    ex._session = MagicMock(spec=aiohttp.ClientSession)
    ex._session.closed = False
    ex._session.request = AsyncMock()
    ex._logger = MagicMock()
    yield ex
    await ex.close()

@pytest.mark.asyncio
async def test_get_balance_success(exchange):
    """
    Successful parsing of get_balance with USDT present.
    """
    exchange.request = AsyncMock(return_value=(
        [
            {"accountType": "1", "details": [
                {"ccy": "USDT", "availBal": "1000.12345678"},
                {"ccy": "BTC", "availBal": "0.5"}
            ]}
        ], True
    ))
    balance = await exchange.get_balance("USDT")
    assert balance == Decimal("1000.12345678")
    exchange._logger.info.assert_called_with("Available USDT: 1000.12345678")

@pytest.mark.asyncio
async def test_get_balance_currency_not_found(exchange):
    """
    get_balance returns 0 and logs warning if currency missing.
    """
    exchange.request = AsyncMock(return_value=(
        [
            {"accountType": "1", "details": [
                {"ccy": "BTC", "availBal": "0.5"}
            ]}
        ], True
    ))
    balance = await exchange.get_balance("USDT")
    assert balance == Decimal("0")
    exchange._logger.warning.assert_called_with("Currency USDT not found in balance data")

@pytest.mark.asyncio
async def test_get_balance_api_error(exchange):
    """
    get_balance returns None on API error.
    """
    exchange.request = AsyncMock(return_value=([], False))
    balance = await exchange.get_balance("USDT")
    assert balance is None

@pytest.mark.asyncio
async def test_get_symbol_price_success(exchange):
    """
    get_symbol_price returns correct Decimal price on valid response.
    """
    exchange.request = AsyncMock(return_value=(
        [{"last": "50000.1234", "instId": "BTC-USDT"}], True
    ))
    price = await exchange.get_symbol_price("BTC-USDT")
    assert price == Decimal("50000.1234")

@pytest.mark.asyncio
async def test_get_symbol_price_invalid(exchange):
    """
    get_symbol_price raises ValueError on invalid response.
    """
    exchange.request = AsyncMock(return_value=([], False))
    with pytest.raises(ValueError):
        await exchange.get_symbol_price("BTC-USDT")

@pytest.mark.asyncio
async def test_place_order_success(exchange):
    """
    place_order returns order ID and logs info on success.
    """
    exchange.get_symbol_precision = AsyncMock(return_value=(4, 6))
    exchange.request = AsyncMock(return_value=([
        {"ordId": "1234567890"}
    ], True))

    order_id = await exchange.place_order(
        symbol="BTC-USDT",
        side="buy",
        price=Decimal("50000.1234"),
        size=Decimal("0.001"),
        trade_mode="isolated",
        position_side="long"
    )
    assert order_id == "1234567890"
    exchange._logger.info.assert_called_with("Order placed: 1234567890")
    # Check payload formatting
    payload = exchange.request.call_args[0][2]
    assert payload["px"] == "50000.1234"
    assert payload["sz"] == "0.001000"

@pytest.mark.asyncio
async def test_place_order_failure(exchange):
    """
    place_order returns None and logs error on failure.
    """
    exchange.get_symbol_precision = AsyncMock(return_value=(4, 6))
    exchange.request = AsyncMock(return_value=([], False))
    order_id = await exchange.place_order("BTC-USDT", "buy", Decimal("1"), Decimal("1"))
    assert order_id is None
    exchange._logger.error.assert_called()

@pytest.mark.asyncio
async def test_cancel_order(exchange):
    """
    cancel_order returns True/False based on API ok flag.
    """
    exchange.request = AsyncMock(return_value=([{},], True))
    assert await exchange.cancel_order("BTC-USDT", "id") is True
    exchange.request = AsyncMock(return_value=([], False))
    assert await exchange.cancel_order("BTC-USDT", "id") is False

@pytest.mark.asyncio
async def test_cancel_all_orders(exchange):
    """
    cancel_all_orders filters ordId and logs.
    """
    exchange.request = AsyncMock(return_value=(
        [{"ordId": "1"}, {"ordId": "2"}, {"foo": "bar"}], True
    ))
    ids = await exchange.cancel_all_orders("BTC-USDT")
    assert ids == ["1", "2"]
    exchange._logger.info.assert_called_with("Canceled orders: ['1', '2']")

@pytest.mark.asyncio
async def test_request_logic(exchange):
    """
    request handles retries and returns data, ok.
    """
    # First response: retryable 429, second: success
    resp1 = MagicMock(status=429, headers={"Retry-After": "0"})
    resp1.json = AsyncMock(return_value={})
    resp2 = MagicMock(status=200, headers={}, json=AsyncMock(return_value={"code":"0","data":[1]}))
    # Setup session.request side_effect context managers
    exchange._session.request.side_effect = [
        asyncio.sleep(0) or AsyncMock(__aenter__=AsyncMock(return_value=resp1), __aexit__=AsyncMock()),
        AsyncMock(__aenter__=AsyncMock(return_value=resp2), __aexit__=AsyncMock())
    ]
    data, ok = await exchange.request("GET", "/test", {})
    assert ok is True and data == [1]

@pytest.mark.asyncio
async def test_signature_and_headers(exchange):
    """
    _sign produces correct signature and headers include timestamp, key, passphrase.
    """
    exchange._secret_key = "secret"
    ts = "2023-01-01T00:00:00.000Z"
    sig = exchange._sign(ts, "GET", "/path", "{\"a\":1}")
    assert isinstance(sig, str) and len(sig) > 0
    headers = exchange._headers("GET", "/path", "{\"a\":1}")
    assert "OK-ACCESS-KEY" in headers and "OK-ACCESS-SIGN" in headers

@pytest.mark.asyncio
async def test_context_manager(exchange):
    """
    Exchange supports async context manager.
    """
    async with exchange as ex:
        assert ex is exchange
    exchange._session.close.assert_called()

@pytest.mark.asyncio
async def test_get_symbol_precision(exchange):
    """
    get_symbol_precision parses tickSz and lotSz.
    """
    exchange.request = AsyncMock(return_value=(
        [{"instId":"BTC-USDT","tickSz":"0.0001","lotSz":"0.000001"}], True
    ))
    tick, lot = await exchange.get_symbol_precision("BTC-USDT")
    assert tick == 4 and lot == 6
    # Cached
    assert "BTC-USDT" in exchange._symbol_precision_cache

@pytest.mark.integration
@pytest.mark.asyncio
async def test_okx_connection():
    """
    Integration test: real connection to OKX in demo mode.
    Requires valid credentials in okx_config.json.
    Verifies balance fetch and symbol price.
    """
    # Load real config
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    # Skip if default test config
    if cfg.get("api_key").startswith("test_"):
        pytest.skip("Skipping real connection test without real API credentials")

    async with OkxExchange() as exchange:
        balance = await exchange.get_balance()
        assert isinstance(balance, Decimal), "Balance should be Decimal"
        assert balance >= Decimal("0"), "Balance should be non-negative"

        price = await exchange.get_symbol_price(cfg.get("symbol"))
        assert isinstance(price, Decimal), "Price should be Decimal"
        assert price > Decimal("0"), "Price should be positive"
