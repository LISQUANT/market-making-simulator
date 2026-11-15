# Market Data Export Package

Clean, high-precision, multi-asset historical market data package with broker execution metadata and spreads.

---

## 1. Directory Structure

```text
zenith_data_export/
├── market_data/            # Cleaned canonical Parquet files (14 symbols, M1 resolution)
│   ├── EURUSD.parquet
│   ├── GBPJPY.parquet
│   ├── GBPUSD.parquet
│   ├── GER40.parquet
│   ├── HK50.parquet
│   ├── JP225.parquet
│   ├── UK100.parquet
│   ├── US100.parquet
│   ├── US30.parquet
│   ├── US500.parquet
│   ├── USDCAD.parquet
│   ├── USDJPY.parquet
│   ├── USOIL.parquet
│   └── XAUUSD.parquet
├── metadata/               # Symbol contract specs, broker spreads, commissions & session times
│   ├── symbols_metadata.json
│   └── symbols_metadata.yaml
├── load_data.py            # Zero-dependency helper script to load M1 & resample (M5, M15, M30, H1, H4, D1)
└── README.md               # This documentation
```

---

## 2. Dataset Specifications

* **Resolution**: Canonical **M1 (1-minute)** continuous bars.
* **Timestamp**: UTC-naive `DatetimeIndex`, named `time`, strictly sorted ascending, duplicates eliminated.
* **Columns**:
  * `open`: float64 (Price open)
  * `high`: float64 (Price high)
  * `low`: float64 (Price low)
  * `close`: float64 (Price close)
  * `volume`: float64 (Tick volume)
  * `spread`: float64 (**Exact nominal spread in price units** per asset)
* **Compression**: Zstandard (zstd level 9) compression, partitioned for fast PyArrow / pandas predicate pushdown filtering.
* **Price Corrections**: Historical 2015 10x Dukascopy feed multiplier on `US30` has been normalized; price history is 100% continuous from 2015 to 2026.

---

## 3. Symbol Coverage & Execution Profiles

| Symbol | Asset Class | Years | Total Rows | Spread (Price) | Spread (Pips) | Contract Size | Tick Size |
|---|---|---|---|---|---|---|---|
| **EURUSD** | Forex | 2015–2026 | 4,414,564 | `0.00012` | 1.2 | 100,000 | 0.00001 |
| **GBPUSD** | Forex | 2015–2026 | 4,187,709 | `0.00018` | 1.8 | 100,000 | 0.00001 |
| **USDJPY** | Forex | 2015–2026 | 4,412,925 | `0.015` | 1.5 | 100,000 | 0.001 |
| **GBPJPY** | Forex | 2015–2026 | 4,233,033 | `0.025` | 2.5 | 100,000 | 0.001 |
| **USDCAD** | Forex | 2015–2026 | 4,224,664 | `0.00015` | 1.5 | 100,000 | 0.00001 |
| **XAUUSD** | Metals | 2015–2026 | 4,195,789 | `0.25` | 25.0 | 100 | 0.01 |
| **US30** | Index | 2015–2026 | 3,656,965 | `2.5` | 250.0 | 1 | 0.01 |
| **US100** | Index | 2015–2026 | 3,609,654 | `2.0` | 200.0 | 1 | 0.01 |
| **US500** | Index | 2015–2026 | 3,421,473 | `0.5` | 5.0 | 1 | 0.1 |
| **GER40** | Index | 2015–2026 | 3,464,876 | `1.5` | 15.0 | 1 | 0.1 |
| **UK100** | Index | 2015–2026 | 3,446,244 | `1.5` | 15.0 | 1 | 0.1 |
| **HK50** | Index | 2013–2026 | 2,918,813 | `6.5` | 650.0 | 0.1285 | 0.01 |
| **JP225** | Index | 2015–2026 | 3,428,702 | `10.0` | 10.0 | 1 | 1.0 |
| **USOIL** | Energy | 2015–2026 | 3,852,267 | `0.03` | 3.0 | 100 | 0.01 |

---

## 4. How to Use in Your Project

### Option A: Using `load_data.py` (Recommended)

```python
from load_data import load_market_data, get_symbol_metadata

# 1. Load H1 bars for Gold from 2022 onwards (automatically resampled from M1)
df = load_market_data(
    symbol="XAUUSD",
    timeframe="H1",
    date_from="2022-01-01",
    date_to="2026-11-03"
)
print(df.head())
#                      open     high      low    close  volume  spread
# time
# 2022-01-03 00:00:00 1829.4  1830.85  1828.15  1829.95   452.0    0.25

# 2. Get symbol metadata (contract sizes, commissions, tick values)
meta = get_symbol_metadata("XAUUSD")
print(f"Contract Size: {meta['contract_size']}, Spread: {meta['spread_price']}, Comm: {meta['commission_per_lot']}")
```

### Option B: Direct Pandas / PyArrow

```python
import pandas as pd

# Direct Parquet read with filter
df = pd.read_parquet(
    "market_data/EURUSD.parquet",
    filters=[("time", ">=", pd.Timestamp("2023-01-01"))]
)
print(df[['open', 'high', 'low', 'close', 'spread']])
```

### Option C: Direct Polars

```python
import polars as pl

df = pl.scan_parquet("market_data/US100.parquet").filter(
    pl.col("time") >= pl.datetime(2023, 1, 1)
).collect()
print(df.head())
```

---

## 5. Resampling Notice

* Native bars are stored in **UTC**.
* If your new backtesting engine needs MT5 / FTMO candle synchronization (EET/EEST, 5 PM NY daily close), pass `offset_hours=2.0` (or `3.0` during daylight savings) into `resample_bars()`.
