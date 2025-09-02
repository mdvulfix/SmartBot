# run_backtest.py
import argparse
from decimal import Decimal
from models.coin import Coin
from backtest.engine import BacktestEngine
from strategies.sma_strategy import SmaStrategy

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True, help="Path to candles CSV")
    p.add_argument("--fast", type=int, default=20)
    p.add_argument("--slow", type=int, default=50)
    p.add_argument("--size", type=str, default="0.001")
    p.add_argument("--fee", type=str, default="0.0005")
    p.add_argument("--slippage", type=str, default="0.0")
    args = p.parse_args()

    coin = Coin("BTC")
    strat = SmaStrategy(coin, fast=args.fast, slow=args.slow, order_size=Decimal(args.size))
    engine = BacktestEngine(coin, strat, fee_rate=Decimal(args.fee), slippage=Decimal(args.slippage))
    engine.load_csv(args.csv)
    engine.run()
    report = engine.compute_report()
    print("Backtest report:")
    for k,v in report.items():
        print(f"  {k}: {v}")
    print("Trades:", len(engine.trade_history))
    # доп. вывод по сделкам
    for t in engine.trade_history[:50]:
        print(t)

if __name__ == "__main__":
    main()
