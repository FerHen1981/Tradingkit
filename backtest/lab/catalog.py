"""CLI entry point for the dataset catalog.

    python -m backtest.lab.catalog <csv> --symbol NQ [--timeframe 1m] [--dest DIR]

The implementation lives in `datasets.py`; this thin module just exposes it
under the `catalog` name used throughout the docs and the plan.
"""
from .datasets import _main

if __name__ == "__main__":
    _main()
