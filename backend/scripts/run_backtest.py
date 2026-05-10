"""
Runs a full 6-month backtest using the production model.

Usage:
    python -m backend.scripts.run_backtest
    python -m backend.scripts.run_backtest --months 3 --threshold 0.65
"""
import argparse
from backend.ml.model_registry import load_production_model
from backend.ml.backtester import run_backtest

parser = argparse.ArgumentParser()
parser.add_argument("--months", type=int, default=6)
parser.add_argument("--threshold", type=float, default=0.60)
args = parser.parse_args()

print(f"Loading production model...")
model = load_production_model()
if model is None:
    print("No production model found. Run train_initial_model.py first.")
    exit(1)

print(f"Running {args.months}-month backtest at threshold={args.threshold}...")
results = run_backtest(model, months=args.months, threshold=args.threshold)

print("\n=== Backtest Summary ===")
for k, v in results.items():
    print(f"  {k}: {v}")
