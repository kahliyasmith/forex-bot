# Data Import

Current milestone: `DATA_READY_VALIDATED`

First required dataset: `EUR_USD` H1 bid/ask candles from OANDA.

Place the real CSV here:

```text
data/historical/EUR_USD_H1_bidask_2020_2025.csv
```

Required schema:

```csv
timestamp,pair,bid_open,bid_high,bid_low,bid_close,ask_open,ask_high,ask_low,ask_close,volume
```

Requirements:

- Use real historical OANDA data, not synthetic or mock data.
- Use UTC timestamps with explicit timezone, such as `2020-01-02T14:00:00Z`.
- Use `EUR_USD` in the `pair` column. Compact `EURUSD` can be parsed, but canonical repo output uses `EUR_USD`.
- Use H1 candles with no silent resampling unless the resampling method is documented.
- Preserve bid and ask OHLC fields separately.
- Keep spread derivable from ask minus bid for each OHLC point.
- Do not commit large raw CSV files unless explicitly intended.

Validate after placing the file:

```powershell
python scripts\validate_market_data.py --data data\historical\EUR_USD_H1_bidask_2020_2025.csv --data-kind bidask_candles --expected-interval-minutes 60 --max-spread-pips 10 --output-dir reports\data_validation\EUR_USD_H1_bidask
```

If the file is missing, validation is blocked. Do not mark `DATA_READY_VALIDATED` until the real file exists and passes validation.
