# WALK_FORWARD_REPORT.md

Status: WALK_FORWARD_EVIDENCE_READY

Classification: WEAK

This report summarizes the first real-data walk-forward validation for `EUR_USD` H1 only. It does not modify strategy logic, does not optimize parameters outside the walk-forward framework, and does not make a profitability claim.

## Data

- File: `data/historical/EUR_USD_H1_bidask_2020_2025.csv`
- Pair: `EUR_USD`
- Timeframe: `H1`
- Data kind: `bidask_candles`
- Validation status: `PASS`
- Validation caveats: `318` missing interval warnings and `817` weekend row warnings were previously triaged in `DATA_WARNING_TRIAGE.md`.
- Generated output directory: `reports/walkforward/EUR_USD_H1_real/`

The raw CSV and generated walk-forward outputs are intentionally not committed.

## Tooling Confirmation

Before this run, `scripts/run_walkforward.py` supported only `candles` and rejected `bidask_candles`. It now accepts `bidask_candles` and normalizes them using the same approach as `scripts/run_backtest.py`: strategy input is converted to mid-price candles, while execution cost reporting uses the measured bid/ask spread.

No strategy logic was changed.

## Command

```powershell
python scripts/run_walkforward.py `
  --config config\bot.yaml `
  --data data\historical\EUR_USD_H1_bidask_2020_2025.csv `
  --data-kind bidask_candles `
  --strategy trend_pullback `
  --slippage-pips 0.2 `
  --commission-per-trade 0 `
  --swap-cost-per-trade 0 `
  --train-window-size 8000 `
  --test-window-size 4000 `
  --step-size 4000 `
  --output-dir reports\walkforward\EUR_USD_H1_real
```

## Window Settings

- Train window size: `8,000` rows
- Test window size: `4,000` rows
- Step size: `4,000` rows
- Number of windows: `7`
- Parameter selection: in-sample grid score of `expectancy - max_drawdown * 100`
- Final out-of-sample periods were not used for selecting their own parameters.
- Parameter grid: existing walk-forward grid defaults from `scripts/run_walkforward.py`

## Cost Assumptions

- Average measured spread paid: `1.6715903311293734` pips
- Slippage: `0.2` pips
- Commission per trade: `0`
- Swap cost per trade: `0`
- Initial balance: `$10,000`
- Units: `10,000`

Swap and commission are still simplified assumptions. This weakens evidence quality until broker-specific costs are modeled.

## Aggregate Out-of-Sample Metrics

| Metric | Value |
| --- | ---: |
| OOS trades | 64 |
| OOS total return | `0.141766821880772010600422912` |
| OOS max drawdown | `0.1372510763520600217135822208` |
| OOS win rate | `0.34375` |
| OOS profit factor | `1.332730762143713888250725232` |
| OOS expectancy | `22.15106591887062665631608009` |
| Average win | `258.1079551234161` |
| Average loss | `-101.4453998549389` |

The aggregate OOS result is positive after the modeled spread and slippage assumptions, but this is not enough to claim a durable edge.

## Window Results

| Window | Test range | Trades | Return | Max DD | Win rate | Profit factor | Expectancy |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `2021-04-15T06:00:00Z` to `2021-12-06T00:00:00Z` | 5 | `0.06175920483443531` | `0.015744422812152818` | `0.6` | `3.831780647469039` | `123.51840966887063` |
| 2 | `2021-12-06T01:00:00Z` to `2022-07-26T18:00:00Z` | 12 | `0.03674909160264475` | `0.07566159033112937` | `0.16666666666666666` | `1.4857033990670048` | `30.62424300220396` |
| 3 | `2022-07-26T19:00:00Z` to `2023-03-17T13:00:00Z` | 10 | `0.015263409668870626` | `0.052185113231790564` | `0.3` | `1.1388086026857402` | `15.263409668870626` |
| 4 | `2023-03-17T14:00:00Z` to `2023-11-07T06:00:00Z` | 8 | `-0.0520922722649035` | `0.06454657164545083` | `0.25` | `0.25855694406365215` | `-65.11534033112937` |
| 5 | `2023-11-07T07:00:00Z` to `2024-06-30T23:00:00Z` | 6 | `-0.07118295419867762` | `0.07118295419867762` | `0.0` | `0.0` | `-118.63825699779603` |
| 6 | `2024-07-01T00:00:00Z` to `2025-02-20T16:00:00Z` | 12 | `0.019314091602644752` | `0.023165130264610707` | `0.4166666666666667` | `1.4200988370658232` | `16.095076335537293` |
| 7 | `2025-02-20T17:00:00Z` to `2025-10-13T07:00:00Z` | 11 | `0.1319562506357577` | `0.027198643457644178` | `0.6363636363636364` | `5.226165398417875` | `119.96022785068881` |

Best return window: window `7`, return `0.1319562506357577`, expectancy `119.96022785068881`.

Worst return window: window `5`, return `-0.07118295419867762`, expectancy `-118.63825699779603`.

## Classification Rationale

Classification is `WEAK`, not `PASS`.

Reasons:

- OOS expectancy is positive after modeled spread and slippage.
- OOS max drawdown is material at about `13.7%`.
- Trade count is only `64`, which is not enough for strong statistical confidence.
- Two of seven OOS windows were negative.
- One OOS window had zero wins.
- This is one pair and one timeframe only.
- Commission and swap are still simplified.
- Validation warnings were triaged as explainable enough to proceed, but the two weekday intraday gaps remain worth re-checking before stronger claims.

This result is useful evidence that the pipeline can run a chronological walk-forward test on real EUR_USD H1 bid/ask data. It is not enough to claim the strategy is profitable or durable.

## Next Blocker

Exact next blocker: evidence is too narrow and trade count is too low for a strong edge claim.

Next work:

- Add more validated pairs and rerun the same walk-forward framework without cherry-picking.
- Add stricter broker-specific commission, swap, margin, and session assumptions.
- Run harsh spread/slippage walk-forward stress tests.
- Re-check the two weekday intraday data gaps or re-fetch those windows from OANDA.
- Add Monte Carlo or bootstrap robustness on OOS trades.
