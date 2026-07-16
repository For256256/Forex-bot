"""
پیاده‌سازی پایتونی همان منطق کد Pine Script (SuperTrend + EMA50/200 + RSI14).
ورودی: DataFrame با ستون‌های open, high, low, close (به ترتیب زمانی صعودی).
خروجی: آخرین ردیف به‌همراه سیگنال (buy / sell / none) و سطوح SL/TP.

توجه: پارامترها دیگر از تنظیمات سراسری خوانده نمی‌شوند، بلکه به‌صورت آرگومان
(StrategyParams) داده می‌شوند تا هر جفت‌ارز بتواند تنظیمات مستقل خودش را داشته باشد.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field


@dataclass
class StrategyParams:
    atr_period: int = 10
    st_factor: float = 3.0
    ema_fast: int = 50
    ema_slow: int = 200
    rsi_period: int = 14
    rsi_buy_level: float = 55
    rsi_sell_level: float = 45
    sl_atr_mult: float = 2.0
    tp_atr_mult: float = 4.0


@dataclass
class SignalResult:
    signal: str  # "buy" | "sell" | "none"
    close: float
    atr: float
    stop_loss: float | None
    take_profit: float | None
    ema_fast: float
    ema_slow: float
    rsi: float
    supertrend: float
    direction: int  # 1 = نزولی(فروش) , -1 = صعودی(خرید) — مطابق قرارداد Pine


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _rsi(series: pd.Series, length: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def _atr(df: pd.DataFrame, length: int) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False).mean()


def _supertrend(df: pd.DataFrame, atr: pd.Series, factor: float):
    """پیاده‌سازی استاندارد SuperTrend، معادل ta.supertrend در Pine."""
    hl2 = (df["high"] + df["low"]) / 2
    upper_basic = hl2 + factor * atr
    lower_basic = hl2 - factor * atr

    upper = upper_basic.copy()
    lower = lower_basic.copy()
    close = df["close"]

    for i in range(1, len(df)):
        upper.iat[i] = (
            upper_basic.iat[i]
            if (upper_basic.iat[i] < upper.iat[i - 1] or close.iat[i - 1] > upper.iat[i - 1])
            else upper.iat[i - 1]
        )
        lower.iat[i] = (
            lower_basic.iat[i]
            if (lower_basic.iat[i] > lower.iat[i - 1] or close.iat[i - 1] < lower.iat[i - 1])
            else lower.iat[i - 1]
        )

    direction = pd.Series(index=df.index, dtype=int)
    supertrend = pd.Series(index=df.index, dtype=float)
    direction.iat[0] = 1
    supertrend.iat[0] = upper.iat[0]

    for i in range(1, len(df)):
        if supertrend.iat[i - 1] == upper.iat[i - 1]:
            direction.iat[i] = -1 if close.iat[i] > upper.iat[i] else 1
        else:
            direction.iat[i] = -1 if close.iat[i] > lower.iat[i] else 1
        supertrend.iat[i] = lower.iat[i] if direction.iat[i] == -1 else upper.iat[i]

    return supertrend, direction


def compute_signal(df: pd.DataFrame, params: StrategyParams = None) -> SignalResult:
    params = params or StrategyParams()

    if len(df) < max(params.ema_slow, params.atr_period, params.rsi_period) + 5:
        raise ValueError("داده کافی برای محاسبه اندیکاتورها وجود ندارد")

    ema_fast = _ema(df["close"], params.ema_fast)
    ema_slow = _ema(df["close"], params.ema_slow)
    rsi = _rsi(df["close"], params.rsi_period)
    atr = _atr(df, params.atr_period)
    supertrend, direction = _supertrend(df, atr, params.st_factor)

    i = -1
    close = df["close"].iat[i]
    bull_trend = ema_fast.iat[i] > ema_slow.iat[i]
    bear_trend = ema_fast.iat[i] < ema_slow.iat[i]

    buy = direction.iat[i] < 0 and bull_trend and rsi.iat[i] > params.rsi_buy_level
    sell = direction.iat[i] > 0 and bear_trend and rsi.iat[i] < params.rsi_sell_level

    signal = "buy" if buy else ("sell" if sell else "none")
    sl = tp = None
    if signal == "buy":
        sl = close - atr.iat[i] * params.sl_atr_mult
        tp = close + atr.iat[i] * params.tp_atr_mult
    elif signal == "sell":
        sl = close + atr.iat[i] * params.sl_atr_mult
        tp = close - atr.iat[i] * params.tp_atr_mult

    return SignalResult(
        signal=signal,
        close=close,
        atr=atr.iat[i],
        stop_loss=sl,
        take_profit=tp,
        ema_fast=ema_fast.iat[i],
        ema_slow=ema_slow.iat[i],
        rsi=rsi.iat[i],
        supertrend=supertrend.iat[i],
        direction=int(direction.iat[i]),
    )
