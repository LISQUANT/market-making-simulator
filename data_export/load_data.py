#!/usr/bin/env python3
"""
load_data.py - Standalone Market Data Loader & Resampler

Drop this file into your project to load canonical M1 Parquet market data,
apply session timezone adjustments, and resample to any timeframe (M5, M15, M30, H1, H4, D1).

Requirements:
    pip install pandas pyarrow
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
MARKET_DATA_DIR = SCRIPT_DIR / "market_data"
METADATA_DIR = SCRIPT_DIR / "metadata"

RESAMPLE_RULES: Dict[str, str] = {
    "M1": "1min",
    "M5": "5min",
    "M15": "15min",
    "M30": "30min",
    "H1": "1h",
    "H4": "4h",
    "D1": "1d",
    "W1": "W-MON",
    "MN1": "MS",
}


def get_symbol_metadata(symbol: Optional[str] = None) -> Union[Dict[str, Any], Any]:
    """Load metadata dictionary containing contract sizes, tick values, and commissions."""
    meta_path = METADATA_DIR / "symbols_metadata.json"
    if not meta_path.exists():
        return {}
    with open(meta_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if symbol:
        sym_clean = symbol.upper().replace(".CASH", "").strip()
        return data.get(sym_clean, {})
    return data


def resample_bars(
    df: pd.DataFrame,
    timeframe: str = "H1",
    offset_hours: float = 0.0,
) -> pd.DataFrame:
    """
    Resample M1 bars into target timeframe with standard OHLCV aggregation.
    
    Args:
        df: DataFrame with DatetimeIndex and columns ['open', 'high', 'low', 'close', 'volume', 'spread']
        timeframe: Target timeframe ('M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1')
        offset_hours: Timezone offset in hours to align candle open/close boundaries (e.g. 2.0 for EET broker alignment).
    """
    tf = timeframe.upper()
    if tf == "M1":
        return df.copy()

    if tf not in RESAMPLE_RULES:
        raise ValueError(f"Unsupported timeframe: {timeframe}. Supported: {list(RESAMPLE_RULES.keys())}")

    work = df.copy()
    if offset_hours != 0.0:
        work.index = work.index + pd.to_timedelta(offset_hours, unit="h")

    agg_rules: Dict[str, str] = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    if "spread" in work.columns:
        agg_rules["spread"] = "mean"

    resampled = work.resample(RESAMPLE_RULES[tf]).agg(agg_rules)
    resampled = resampled.dropna(subset=["open", "high", "low", "close"])

    if offset_hours != 0.0:
        resampled.index = resampled.index - pd.to_timedelta(offset_hours, unit="h")

    return resampled


def load_market_data(
    symbol: str,
    timeframe: str = "M1",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    offset_hours: Optional[float] = None,
    data_dir: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """
    Load market data for a symbol from canonical Parquet storage.
    
    Args:
        symbol: Canonical ticker (e.g. 'EURUSD', 'XAUUSD', 'US30', 'GER40')
        timeframe: 'M1' (native) or any resampled timeframe ('M5', 'M15', 'M30', 'H1', 'H4', 'D1')
        date_from: Optional filter start timestamp string (e.g. '2020-01-01')
        date_to: Optional filter end timestamp string (e.g. '2026-11-03')
        offset_hours: Session timezone offset in hours. If None, loaded from metadata.
        data_dir: Directory containing <SYMBOL>.parquet files (defaults to ./market_data)
    """
    base_dir = Path(data_dir or MARKET_DATA_DIR)
    sym_clean = symbol.upper().replace(".CASH", "").strip()
    parquet_path = base_dir / f"{sym_clean}.parquet"

    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet file not found: {parquet_path}")

    filters = []
    if date_from:
        filters.append(("time", ">=", pd.Timestamp(date_from)))
    if date_to:
        filters.append(("time", "<=", pd.Timestamp(date_to)))

    if filters:
        df = pd.read_parquet(parquet_path, engine="pyarrow", memory_map=True, filters=filters)
    else:
        df = pd.read_parquet(parquet_path, engine="pyarrow", memory_map=True)

    if df.empty:
        raise ValueError(f"No bars returned for {symbol} with filters date_from={date_from}, date_to={date_to}")

    if "time" in df.columns and not isinstance(df.index, pd.DatetimeIndex):
        df["time"] = pd.to_datetime(df["time"])
        df.set_index("time", inplace=True)
    elif not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    df.index.name = "time"

    # Timezone offset handling
    if offset_hours is None:
        meta = get_symbol_metadata(sym_clean)
        offset_hours = float(meta.get("session_timezone_offset_hours", 0.0))

    if timeframe.upper() != "M1":
        df = resample_bars(df, timeframe=timeframe, offset_hours=offset_hours)

    return df


def main():
    parser = argparse.ArgumentParser(description="Zenith Market Data Loader CLI")
    parser.add_argument("--symbol", "-s", default="XAUUSD", help="Symbol ticker (default: XAUUSD)")
    parser.add_argument("--timeframe", "-t", default="H1", help="Timeframe: M1, M5, M15, M30, H1, H4, D1")
    parser.add_argument("--date-from", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--date-to", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--offset-hours", type=float, default=None, help="Timezone offset hours (default: from metadata)")

    args = parser.parse_args()

    print(f"[*] Loading {args.symbol} {args.timeframe} (from: {args.date_from}, to: {args.date_to})...")
    df = load_market_data(
        symbol=args.symbol,
        timeframe=args.timeframe,
        date_from=args.date_from,
        date_to=args.date_to,
        offset_hours=args.offset_hours,
    )

    meta = get_symbol_metadata(args.symbol)
    print(f"\n[+] Loaded {len(df):,} bars successfully!")
    print(f"  Range:  {df.index[0]} -> {df.index[-1]}")
    print(f"  Cols:   {list(df.columns)}")
    print(f"  Spread: {df['spread'].iloc[-1]} (nominal) | Pip: {meta.get('spread_pips')} pips | Contract Size: {meta.get('contract_size')}")
    print("\n--- HEAD (3) ---")
    print(df.head(3))
    print("\n--- TAIL (3) ---")
    print(df.tail(3))


if __name__ == "__main__":
    main()
