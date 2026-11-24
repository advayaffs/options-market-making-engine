"""A small options desk trading one fictional stock. Run with Python 3.9+.

One session lasts five trading days, with 78 five-minute intervals per day.
Contracts cover 100 shares. Rates and dividends are zero. All prices are in
dollars. The surface and customer orders are synthetic. Ending P&L marks
open positions at model value and excludes the cost of closing them.
"""

import argparse
import csv
import math
import random
from collections import Counter
from dataclasses import dataclass
from statistics import NormalDist

NORMAL = NormalDist()
LOT = 100
LIMIT = 8                 # contracts per strike, expiry and option type
STEPS_PER_DAY = 78
DT = 1 / (252 * STEPS_PER_DAY)


@dataclass(frozen=True)
class Option:
    strike: int
    expiry_day: int
    kind: str


@dataclass
class Mark:
    price: float
    delta: float
    gamma: float
    vega: float           # per 1.00 change in volatility
    theta: float          # per year of elapsed time
    vol: float


def price_option(option, spot, years, vol):
    """European Black-Scholes value and Greeks, per share."""
    sign = 1 if option.kind == 'call' else -1
    if years <= 0:
        intrinsic = sign * (spot - option.strike)
        delta = sign * (1 if intrinsic > 0 else 0.5 if intrinsic == 0 else 0)
        return Mark(max(0, intrinsic), delta, 0, 0, 0, vol)

    root_t = math.sqrt(years)
    width = vol * root_t
    d1 = math.log(spot / option.strike) / width + width / 2
    d2 = d1 - width
    price = sign * (spot * NORMAL.cdf(sign * d1)
                    - option.strike * NORMAL.cdf(sign * d2))
    density = NORMAL.pdf(d1)
    return Mark(max(0, price), sign * NORMAL.cdf(sign * d1),
                density / (spot * width), spot * density * root_t,
                -spot * density * vol / (2 * root_t), vol)


def mark_chain(chain, spot, atm_vol, step):
    marks = {}
    for option in chain:
        years = option.expiry_day / 252 - step * DT
        moneyness = math.log(option.strike / spot)
        vol = atm_vol - 0.30 * moneyness + 0.035 * math.sqrt(max(0, years))
        marks[option] = price_option(option, spot, years, max(0.05, vol))
    return marks


def quote(mark, inventory):
    # Being long lowers both quotes: buying more gets cheaper, selling gets easier.
    half_spread = 0.025 + 0.012 * mark.price
    center = mark.price - inventory / LIMIT * half_spread
    bid = math.floor((center - half_spread) * 100) / 100
    ask = math.ceil((center + half_spread) * 100) / 100
    return bid if inventory < LIMIT and bid > 0 else None, ask if inventory > -LIMIT else None


def attribute_move(pnl, inventory, shares, old, new, spot_change):
    pnl['Delta'] += shares * spot_change
    for option, contracts in inventory.items():
        units = contracts * LOT
        before, after = old[option], new[option]
        delta = before.delta * spot_change
        gamma = 0.5 * before.gamma * spot_change ** 2
        vega = before.vega * (after.vol - before.vol)
        theta = before.theta * DT
        pnl['Delta'] += units * delta
        pnl['Gamma'] += units * gamma
        pnl['Vega'] += units * vega
        pnl['Theta'] += units * theta
        pnl['Repricing residual'] += units * (after.price - before.price
                                             - delta - gamma - vega - theta)


def simulate(seed, hedge_band, writer=None):
    rng = random.Random(seed)
    chain = [Option(k, days, kind) for k in (95, 100, 105)
             for days in (10, 30) for kind in ('call', 'put')]
    spot, atm_vol = 100.0, 0.22
    marks = mark_chain(chain, spot, atm_vol, 0)
    inventory = Counter()
    pnl = Counter()
    cash = peak = drawdown = 0.0
    shares = fills = hedges = 0

    for step in range(1, 5 * STEPS_PER_DAY + 1):
        option = rng.choice(chain)
        mark = marks[option]
        bid, ask = quote(mark, inventory[option])

        # Some customers have directional information about the upcoming move.
        # The maker only sees the order and its own current quotes.
        shock = rng.gauss(0, 1)
        informed = rng.random() < 0.20
        customer_buys = shock * mark.delta > 0 if informed else rng.random() < 0.5
        tolerance = rng.expovariate(1 / (0.06 + 0.015 * mark.price))
        quantity, fill = 0, None
        if customer_buys and ask is not None and ask <= mark.price + tolerance:
            quantity, fill = -1, ask
        elif not customer_buys and bid is not None and bid >= mark.price - tolerance:
            quantity, fill = 1, bid

        if quantity:
            inventory[option] += quantity
            cash -= quantity * LOT * fill + 0.65
            pnl['Quote edge'] += quantity * LOT * (mark.price - fill)
            pnl['Trading costs'] -= 0.65
            fills += 1

        option_delta = sum(n * LOT * marks[o].delta for o, n in inventory.items())
        net_delta = shares + option_delta
        hedge = -round(net_delta) if abs(net_delta) > hedge_band else 0
        if hedge:
            cost = abs(hedge) * 0.01
            cash -= hedge * spot + cost
            shares += hedge
            pnl['Trading costs'] -= cost
            hedges += 1

        next_spot = spot * math.exp(atm_vol * math.sqrt(DT) * shock - atm_vol ** 2 * DT / 2)
        vol_shock = -0.55 * shock + math.sqrt(1 - 0.55 ** 2) * rng.gauss(0, 1)
        atm_vol += 5 * (0.22 - atm_vol) * DT + 0.30 * math.sqrt(DT) * vol_shock
        atm_vol = min(0.80, max(0.06, atm_vol))
        next_marks = mark_chain(chain, next_spot, atm_vol, step)
        attribute_move(pnl, inventory, shares, marks, next_marks, next_spot - spot)
        option_value = sum(n * LOT * next_marks[o].price for o, n in inventory.items())
        equity = cash + shares * next_spot + option_value
        if not math.isclose(equity, sum(pnl.values()), abs_tol=1e-7):
            raise ArithmeticError(f'Cash and Greek attribution disagree at step {step}')
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
        if writer is not None:
            writer.writerow([step, spot, option.kind, option.strike, option.expiry_day,
                             mark.vol, mark.price, bid, ask, quantity, fill, hedge,
                             shares, next_spot, option_value, cash, equity])
        spot, marks = next_spot, next_marks

    print(f'Seed {seed} | {fills} option fills | {hedges} stock hedges')
    for label in ('Quote edge', 'Delta', 'Gamma', 'Vega', 'Theta',
                  'Repricing residual', 'Trading costs'):
        print(f'{label:20} {pnl[label]:+10.2f}')
    print(f'Ending marked P&L    {equity:+10.2f}')
    print(f'Maximum drawdown     {drawdown:10.2f}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--hedge-band', type=float, default=15,
                        help='hedge when net delta exceeds this many shares (default 15)')
    parser.add_argument('--csv', metavar='PATH', help='write every quote, fill and hedge')
    args = parser.parse_args()
    if not math.isfinite(args.hedge_band) or args.hedge_band < 0:
        parser.error('--hedge-band must be finite and nonnegative')
    if args.csv:
        with open(args.csv, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow('step spot kind strike expiry_day iv fair bid ask maker_contracts '
                            'fill hedge_shares stock_position end_spot end_option_value '
                            'end_cash end_equity'.split())
            simulate(args.seed, args.hedge_band, writer)
    else:
        simulate(args.seed, args.hedge_band)


if __name__ == '__main__':
    main()
