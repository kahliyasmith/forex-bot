# Current Status

Status: `DATA_INFRASTRUCTURE_READY`

Evidence status: `DATA_MISSING`

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

No real historical market data is present. No profitability, strategy-performance, or trading-edge claim can be made until real historical data is added and validated.
