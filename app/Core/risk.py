"""
محاسبه حجم معامله (لات) بر اساس درصد ریسک ثابت از موجودی حساب — با پشتیبانی
از چند جفت‌ارز که هرکدام pip size و pip value متفاوتی دارند.

⚠️ محدودیت شناخته‌شده: محاسبه pip value برای جفت‌ارزهایی که USD در آن‌ها نیست
(کراس‌هایی مثل EURGBP) به‌صورت تقریبی است. برای دقت کامل، pip_value_per_lot را
برای آن نماد در accounts.json دستی مقداردهی کنید.
"""

JPY_PAIRS = {"USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "CHFJPY", "CADJPY", "NZDJPY"}
METALS = {"XAUUSD", "XAGUSD"}


def get_pip_size(symbol: str) -> float:
    if symbol in METALS or symbol in JPY_PAIRS or symbol.endswith("JPY"):
        return 0.01
    return 0.0001


def estimate_pip_value_per_lot(symbol: str, current_price: float, manual_override: float = None) -> float:
    """ارزش تقریبی هر پیپ به ازای ۱ لات استاندارد (۱۰۰,۰۰۰ واحد پایه)، بر حسب دلار."""
    if manual_override:
        return manual_override

    contract_size = 100_000
    pip_size = get_pip_size(symbol)

    if symbol in METALS:
        return 1.0  # XAUUSD: هر پیپ (۰.۰۱) در ۱ لات ≈ ۱ دلار

    quote_ccy = symbol[3:6] if len(symbol) >= 6 else "USD"

    if quote_ccy == "USD":
        return pip_size * contract_size

    if symbol.endswith("JPY") or quote_ccy == "JPY":
        if current_price and current_price > 0:
            return (pip_size * contract_size) / current_price
        return 6.5

    return 10.0  # تقریب برای کراس‌های بدون USD — برای دقت بیشتر override بگذارید


def calculate_lot_size(
    balance: float,
    entry_price: float,
    stop_loss_price: float,
    symbol: str,
    risk_percent: float,
    pip_value_override: float = None,
) -> float:
    pip_size = get_pip_size(symbol)
    pip_value_per_lot = estimate_pip_value_per_lot(symbol, entry_price, pip_value_override)

    risk_amount = balance * (risk_percent / 100)
    distance_pips = abs(entry_price - stop_loss_price) / pip_size
    if distance_pips <= 0 or pip_value_per_lot <= 0:
        return 0.0

    lot = risk_amount / (distance_pips * pip_value_per_lot)
    lot = max(0.01, round(lot, 2))
    lot = min(lot, 50.0)
    return lot


def daily_loss_exceeded(start_of_day_balance: float, current_equity: float, max_daily_loss_percent: float) -> bool:
    if start_of_day_balance <= 0:
        return False
    loss_percent = (start_of_day_balance - current_equity) / start_of_day_balance * 100
    return loss_percent >= max_daily_loss_percent
