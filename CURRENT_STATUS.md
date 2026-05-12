# Current Status

Current code status: `DATA_INFRASTRUCTURE_READY`

Evidence status: `DATA_MISSING`

Next milestone: `DATA_READY_VALIDATED`

The repo can validate and load these CSV market-data kinds:

- `quotes`: `timestamp,pair,bid,ask`
- `candles`: `timestamp,pair,open,high,low,close,volume`
- `bidask_candles`: `timestamp,pair,bid_open,bid_high,bid_low,bid_close,ask_open,ask_high,ask_low,ask_close,volume`

The validator supports:

```powershell
python scripts\validate_market_data.py --data <csv> --data-kind <quotes|candles|bidask_candles|auto>
```

The backtest runner recognizes `bidask_candles` and normalizes them into mid-price candles plus a measured close-spread assumption for the existing candle strategy path.

`config/data_manifest.yaml` is supported by the manifest loader for metadata validation and missing-file rejection. A full campaign matrix runner that consumes the manifest end-to-end is still not implemented.

OANDA import support exists at:

```powershell
python scripts\import_oanda_candles.py --instrument EUR_USD --from 2020-01-01T00:00:00Z --to 2025-12-31T23:00:00Z --granularity H1 --output data\historical\EUR_USD_H1_bidask_2020_2025.csv
```

The importer requires `OANDA_API_KEY` and defaults `OANDA_ENV` to `practice`.

No real historical market data is present yet. The expected first real dataset is:

```text
data/historical/EUR_USD_H1_bidask_2020_2025.csv
```

Validation command:

```powershell
python scripts\validate_market_data.py --data data\historical\EUR_USD_H1_bidask_2020_2025.csv --data-kind bidask_candles --expected-interval-minutes 60 --max-spread-pips 10 --output-dir reports\data_validation\EUR_USD_H1_bidask
```

No profitability, strategy-performance, or trading-edge claim can be made until real historical data is added and validated.
