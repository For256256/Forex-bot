"""
تنظیمات ربات — همه مقادیر از فایل .env خوانده می‌شوند.
هیچ مقدار حساس (توکن، پسورد) نباید مستقیم در کد نوشته شود.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class Settings:
    # ---- اتصال MetaApi (پل بین MT5 آلپاری و پایتون) ----
    METAAPI_TOKEN: str = os.getenv("METAAPI_TOKEN", "")
    METAAPI_ACCOUNT_ID: str = os.getenv("METAAPI_ACCOUNT_ID", "")

    # ---- نماد و تایم‌فریم ----
    SYMBOL: str = os.getenv("SYMBOL", "EURUSD")
    TIMEFRAME: str = os.getenv("TIMEFRAME", "1h")  # 1m,5m,15m,30m,1h,4h,1d

    # ---- پارامترهای استراتژی (مطابق کد Pine اولیه) ----
    ATR_PERIOD: int = _get_int("ATR_PERIOD", 10)
    ST_FACTOR: float = _get_float("ST_FACTOR", 3.0)
    EMA_FAST: int = _get_int("EMA_FAST", 50)
    EMA_SLOW: int = _get_int("EMA_SLOW", 200)
    RSI_PERIOD: int = _get_int("RSI_PERIOD", 14)
    RSI_BUY_LEVEL: float = _get_float("RSI_BUY_LEVEL", 55)
    RSI_SELL_LEVEL: float = _get_float("RSI_SELL_LEVEL", 45)
    SL_ATR_MULT: float = _get_float("SL_ATR_MULT", 2.0)
    TP_ATR_MULT: float = _get_float("TP_ATR_MULT", 4.0)

    # ---- مدیریت ریسک ----
    RISK_PERCENT: float = _get_float("RISK_PERCENT", 1.0)  # درصد ریسک از موجودی در هر معامله
    MAX_OPEN_POSITIONS: int = _get_int("MAX_OPEN_POSITIONS", 1)
    MAX_DAILY_LOSS_PERCENT: float = _get_float("MAX_DAILY_LOSS_PERCENT", 5.0)  # قطع ربات پس از این ضرر روزانه

    # ---- حالت اجرا ----
    # paper: فقط شبیه‌سازی داخلی بدون ارسال سفارش واقعی
    # live: ارسال سفارش واقعی به حساب متصل‌شده (دمو یا واقعی، بسته به حسابی که در MetaApi ثبت کرده‌اید)
    TRADING_MODE: str = os.getenv("TRADING_MODE", "paper")

    # ---- سرور داشبورد ----
    DASHBOARD_PORT: int = _get_int("DASHBOARD_PORT", 8999)
    DASHBOARD_USER: str = os.getenv("DASHBOARD_USER", "admin")
    DASHBOARD_PASSWORD: str = os.getenv("DASHBOARD_PASSWORD", "")

    # ---- فاصله بررسی سیگنال (ثانیه) ----
    POLL_INTERVAL_SECONDS: int = _get_int("POLL_INTERVAL_SECONDS", 60)


settings = Settings()
