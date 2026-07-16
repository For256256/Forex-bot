"""
مدیریت فایل config/accounts.json که لیست حساب‌ها و برای هر حساب لیست جفت‌ارزهای
فعال را نگه می‌دارد. این فایل جایگزین تنظیمات تک‌حسابیِ .env شده است.
"""
import json
import os
import threading
import uuid
from copy import deepcopy

CONFIG_PATH = os.getenv("ACCOUNTS_CONFIG_PATH", "config/accounts.json")

_lock = threading.Lock()

DEFAULT_SYMBOL = {
    "symbol": "EURUSD",
    "timeframe": "1h",
    "enabled": True,
    "atr_period": 10,
    "st_factor": 3.0,
    "ema_fast": 50,
    "ema_slow": 200,
    "rsi_period": 14,
    "rsi_buy_level": 55,
    "rsi_sell_level": 45,
    "sl_atr_mult": 2.0,
    "tp_atr_mult": 4.0,
    "pip_value_per_lot": None,  # اگر خالی باشد، به‌صورت خودکار تخمین زده می‌شود
}

DEFAULT_ACCOUNT = {
    "id": None,
    "name": "حساب جدید",
    "trading_mode": "paper",   # paper | live
    "metaapi_token": "",
    "metaapi_account_id": "",
    "risk_percent": 1.0,
    "max_open_positions": 1,
    "max_daily_loss_percent": 5.0,
    "poll_interval_seconds": 60,
    "enabled": True,
    "symbols": [],
}


def _ensure_file():
    os.makedirs(os.path.dirname(CONFIG_PATH) or ".", exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"accounts": []}, f, ensure_ascii=False, indent=2)


def load_config() -> dict:
    _ensure_file()
    with _lock:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)


def save_config(data: dict):
    _ensure_file()
    with _lock:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def list_accounts() -> list:
    return load_config().get("accounts", [])


def add_account(payload: dict) -> dict:
    data = load_config()
    account = deepcopy(DEFAULT_ACCOUNT)
    account.update(payload)
    account["id"] = str(uuid.uuid4())[:8]
    account.setdefault("symbols", [])
    data["accounts"].append(account)
    save_config(data)
    return account


def update_account(account_id: str, payload: dict) -> dict:
    data = load_config()
    for acc in data["accounts"]:
        if acc["id"] == account_id:
            acc.update({k: v for k, v in payload.items() if k != "id" and k != "symbols"})
            save_config(data)
            return acc
    raise KeyError(f"حساب با شناسه {account_id} پیدا نشد")


def delete_account(account_id: str):
    data = load_config()
    data["accounts"] = [a for a in data["accounts"] if a["id"] != account_id]
    save_config(data)


def add_symbol(account_id: str, payload: dict) -> dict:
    data = load_config()
    for acc in data["accounts"]:
        if acc["id"] == account_id:
            symbol_cfg = deepcopy(DEFAULT_SYMBOL)
            symbol_cfg.update(payload)
            acc["symbols"] = [s for s in acc["symbols"] if s["symbol"] != symbol_cfg["symbol"]]
            acc["symbols"].append(symbol_cfg)
            save_config(data)
            return symbol_cfg
    raise KeyError(f"حساب با شناسه {account_id} پیدا نشد")


def remove_symbol(account_id: str, symbol: str):
    data = load_config()
    for acc in data["accounts"]:
        if acc["id"] == account_id:
            acc["symbols"] = [s for s in acc["symbols"] if s["symbol"] != symbol]
            save_config(data)
            return
    raise KeyError(f"حساب با شناسه {account_id} پیدا نشد")


def toggle_symbol(account_id: str, symbol: str, enabled: bool):
    data = load_config()
    for acc in data["accounts"]:
        if acc["id"] == account_id:
            for s in acc["symbols"]:
                if s["symbol"] == symbol:
                    s["enabled"] = enabled
                    save_config(data)
                    return
    raise KeyError("نماد یا حساب پیدا نشد")


def migrate_from_env_if_needed():
    """اگر accounts.json خالی است ولی .env تنظیمات تک‌حسابی قدیمی دارد، آن را منتقل کن."""
    from app.config import settings

    data = load_config()
    if data.get("accounts"):
        return  # قبلاً تنظیم شده، کاری نکن

    if not settings.METAAPI_TOKEN and not settings.METAAPI_ACCOUNT_ID:
        return  # چیزی برای مهاجرت نیست

    account = deepcopy(DEFAULT_ACCOUNT)
    account["id"] = "legacy"
    account["name"] = "حساب اصلی (منتقل‌شده از .env)"
    account["trading_mode"] = settings.TRADING_MODE
    account["metaapi_token"] = settings.METAAPI_TOKEN
    account["metaapi_account_id"] = settings.METAAPI_ACCOUNT_ID
    account["risk_percent"] = settings.RISK_PERCENT
    account["max_open_positions"] = settings.MAX_OPEN_POSITIONS
    account["max_daily_loss_percent"] = settings.MAX_DAILY_LOSS_PERCENT
    account["poll_interval_seconds"] = settings.POLL_INTERVAL_SECONDS

    symbol_cfg = deepcopy(DEFAULT_SYMBOL)
    symbol_cfg.update({
        "symbol": settings.SYMBOL,
        "timeframe": settings.TIMEFRAME,
        "atr_period": settings.ATR_PERIOD,
        "st_factor": settings.ST_FACTOR,
        "ema_fast": settings.EMA_FAST,
        "ema_slow": settings.EMA_SLOW,
        "rsi_period": settings.RSI_PERIOD,
        "rsi_buy_level": settings.RSI_BUY_LEVEL,
        "rsi_sell_level": settings.RSI_SELL_LEVEL,
        "sl_atr_mult": settings.SL_ATR_MULT,
        "tp_atr_mult": settings.TP_ATR_MULT,
    })
    account["symbols"] = [symbol_cfg]

    data["accounts"] = [account]
    save_config(data)
