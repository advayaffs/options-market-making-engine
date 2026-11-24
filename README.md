# Options Pricing & Market Making Engine

A synthetic options desk with European option pricing, inventory-aware quotes, delta hedging and P&L attribution.

## Overview

The goal is to connect option pricing and Greeks to the cash ledger of a simulated market maker. The desk trades twelve European contracts on a fictional stock: three strikes, two expiries and calls/puts.

## Method

- Use Black–Scholes at zero interest and dividend rates, computing price, delta, gamma, vega and theta per share.
- Construct a synthetic volatility surface from moneyness, tenor and a moving at-the-money volatility level.
- Quote around theoretical value with inventory-dependent skew and position limits; simulate customer flow including an informed component.
- Hedge net delta in shares when its absolute value exceeds the hedge band (15 shares by default).
- Attribute P&L to quote edge, delta, gamma, vega, theta, repricing residual and trading costs. Reconcile the attribution with marked cash and holdings at each step.

The local Greek approximation is ΔV ≈ Δ·ΔS + ½Γ·(ΔS)² + Vega·Δσ + Theta·Δt; the residual captures the difference from full repricing. Contract multiplier: 100 shares.

## Run

```bash
python options_market_maker.py
python options_market_maker.py --seed 7 --hedge-band 15 --csv session.csv
```

## Reproduced results

Five synthetic trading days, 390 five-minute steps, seed 7. The run recorded 209 option fills and 183 stock hedges.

| P&L component | USD |
|---|---:|
| Quote edge | +1,303.48 |
| Delta | −5.43 |
| Gamma | −45.38 |
| Vega | −187.51 |
| Theta | +44.34 |
| Repricing residual | +4.04 |
| Trading costs | −231.76 |
| Ending marked P&L | +881.79 |
| Maximum drawdown | 73.60 |

Attribution components reconcile before display rounding. Ending positions are marked at model value; closing costs are excluded. These figures are not live trading performance.

## Limitations and next steps

The surface and order flow are synthetic. There is no real bid/ask calibration or exchange execution, and model assumptions can materially affect profitability. Next steps: finite-difference Greek checks, realistic volatility surfaces, hedge-band sensitivity and liquidation-cost analysis.

## Requirements and files

Python 3.9+; no third-party dependencies are required.

- `options_market_maker.py` — original project implementation.
- `requirements.txt` — dependency notes.
- `results/` — outputs from the example run, including [terminal output](results/example_run.txt).

The example was rerun using the bundled source. This is a research/educational project; it is not a production system.
