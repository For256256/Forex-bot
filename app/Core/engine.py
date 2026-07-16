"""
موتور اصلی ربات با پشتیبانی چند حساب هم‌زمان و چند جفت‌ارز هم‌زمان در هر حساب.

ساختار:
- هر حساب (Account) یک اتصال broker مستقل دارد.
- هر جفت‌ارز فعال در آن حساب، یک تسک async جدا اجرا می‌کند (چرخه مستقل بررسی سیگنال).
- تمام تسک‌های یک حساب از همان یک اتصال broker استفاده می‌کنند (بدون لاگین تکراری).
"""
import asyncio
import traceback
from collections import deque
from datetime import datetime, timezone

from app.core.strategy import compute_signal, StrategyParams
from app.core.risk import calculate_lot_size, daily_loss_exceeded
from app.core.broker import build_broker, BrokerError
from app.core import config_store


def _params_from_symbol_cfg(cfg: dict) -> StrategyParams:
    return StrategyParams(
        atr_period=cfg.get("atr_period", 10),
        st_factor=cfg.get("st_factor", 3.0),
        ema_fast=cfg.get("ema_fast", 50),
        ema_slow=cfg.get("ema_slow", 200),
        rsi_period=cfg.get("rsi_period", 14),
        rsi_buy_level=cfg.get("rsi_buy_level", 55),
        rsi_sell_level=cfg.get("rsi_sell_level", 45),
        sl_atr_mult=cfg.get("sl_atr_mult", 2.0),
        tp_atr_mult=cfg.get("tp_atr_mult", 4.0),
    )


class AccountManager:
    """یک حساب معاملاتی + همه جفت‌ارزهای فعالش."""

    def __init__(self, account_cfg: dict):
        self.cfg = account_cfg
        self.broker = None
        self.running = False
        self.error = None
        self.logs = deque(maxlen=300)
        self.symbol_state = {}       # symbol -> آخرین سیگنال/وضعیت
        self.tasks = {}               # symbol -> asyncio.Task
        self.account_info = {"balance": 0, "equity": 0, "currency": "USD"}
        self.start_of_day_balance = None

    def log(self, message: str, level: str = "info", symbol: str = None):
        self.logs.append({
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "level": level,
            "symbol": symbol,
            "message": message,
        })

    async def start(self):
        if self.running:
            return
        self.error = None
        self.broker = build_broker(
            self.cfg["trading_mode"], self.cfg.get("metaapi_token", ""), self.cfg.get("metaapi_account_id", "")
        )
        try:
            await self.broker.connect()
        except BrokerError as e:
            self.error = str(e)
            self.log(f"خطا در اتصال: {e}", "error")
            return
        except Exception as e:
            self.error = str(e)
            self.log(f"خطای غیرمنتظره در اتصال: {e}", "error")
            return

        self.running = True
        self.log(f"حساب «{self.cfg['name']}» متصل شد (حالت: {self.cfg['trading_mode']})", "success")

        for symbol_cfg in self.cfg.get("symbols", []):
            if symbol_cfg.get("enabled", True):
                self._spawn_symbol_task(symbol_cfg)

    async def stop(self):
        self.running = False
        for task in self.tasks.values():
            task.cancel()
        self.tasks = {}
        self.log(f"حساب «{self.cfg['name']}» متوقف شد.", "warning")

    def _spawn_symbol_task(self, symbol_cfg: dict):
        symbol = symbol_cfg["symbol"]
        if symbol in self.tasks and not self.tasks[symbol].done():
            return  # از قبل در حال اجراست
        self.symbol_state.setdefault(symbol, {"signal": None, "positions": []})
        self.tasks[symbol] = asyncio.create_task(self._symbol_loop(symbol_cfg))

    def add_or_update_symbol(self, symbol_cfg: dict):
        """برای افزودن جفت‌ارز جدید به یک حساب که همین الان در حال اجراست."""
        symbol = symbol_cfg["symbol"]
        if symbol in self.tasks:
            self.tasks[symbol].cancel()
        if self.running and symbol_cfg.get("enabled", True):
            self._spawn_symbol_task(symbol_cfg)

    def remove_symbol(self, symbol: str):
        if symbol in self.tasks:
            self.tasks[symbol].cancel()
            del self.tasks[symbol]
        self.symbol_state.pop(symbol, None)

    async def _symbol_loop(self, symbol_cfg: dict):
        symbol = symbol_cfg["symbol"]
        params = _params_from_symbol_cfg(symbol_cfg)
        poll_seconds = self.cfg.get("poll_interval_seconds", 60)

        while self.running:
            try:
                await self._symbol_tick(symbol, symbol_cfg, params)
            except Exception as e:
                self.log(f"خطا در چرخه {symbol}: {e}", "error", symbol)
                self.log(traceback.format_exc()[-400:], "error", symbol)
            await asyncio.sleep(poll_seconds)

    async def _symbol_tick(self, symbol: str, symbol_cfg: dict, params: StrategyParams):
        info = await self.broker.get_account_info()
        self.account_info = info

        if self.start_of_day_balance is None:
            self.start_of_day_balance = info["balance"]

        if daily_loss_exceeded(self.start_of_day_balance, info["equity"], self.cfg.get("max_daily_loss_percent", 5.0)):
            self.log("سقف ضرر روزانه حساب رد شد — معامله جدیدی گرفته نمی‌شود.", "warning", symbol)
            return

        positions = await self.broker.get_open_positions(symbol)
        self.symbol_state[symbol]["positions"] = positions

        df = await self.broker.get_candles(symbol, symbol_cfg.get("timeframe", "1h"), 500)
        result = compute_signal(df, params)
        self.symbol_state[symbol]["signal"] = result

        if result.signal == "none":
            return

        if len(positions) >= self.cfg.get("max_open_positions", 1):
            self.log(f"سیگنال {result.signal} برای {symbol} رد شد (سقف پوزیشن باز).", "warning", symbol)
            return

        lot = calculate_lot_size(
            info["balance"], result.close, result.stop_loss, symbol,
            self.cfg.get("risk_percent", 1.0), symbol_cfg.get("pip_value_per_lot"),
        )
        if lot <= 0:
            self.log(f"حجم محاسبه‌شده برای {symbol} صفر بود.", "warning", symbol)
            return

        order = await self.broker.place_order(
            side=result.signal, symbol=symbol, volume=lot,
            stop_loss=result.stop_loss, take_profit=result.take_profit,
        )
        self.log(
            f"{symbol}: سفارش {result.signal.upper()} ثبت شد | حجم={lot} | ورود={result.close:.5f} "
            f"SL={result.stop_loss:.5f} TP={result.take_profit:.5f}",
            "success", symbol,
        )

    def get_status(self) -> dict:
        symbols_status = {}
        for symbol, state in self.symbol_state.items():
            sig = state.get("signal")
            symbols_status[symbol] = {
                "running": symbol in self.tasks and not self.tasks[symbol].done(),
                "positions": state.get("positions", []),
                "signal": None if not sig else {
                    "signal": sig.signal,
                    "close": sig.close,
                    "rsi": round(sig.rsi, 2),
                    "ema_fast": round(sig.ema_fast, 5),
                    "ema_slow": round(sig.ema_slow, 5),
                    "stop_loss": sig.stop_loss,
                    "take_profit": sig.take_profit,
                },
            }
        return {
            "id": self.cfg["id"],
            "name": self.cfg["name"],
            "mode": self.cfg["trading_mode"],
            "running": self.running,
            "error": self.error,
            "account": self.account_info,
            "symbols": symbols_status,
            "logs": list(self.logs)[-50:],
        }


class BotManager:
    """نگه‌دارنده تمام حساب‌ها (تک‌تک AccountManager ها)."""

    def __init__(self):
        self.accounts: dict[str, AccountManager] = {}

    def sync_from_config(self):
        """با فایل accounts.json هماهنگ می‌شود: حساب جدید اضافه، حذف‌شده‌ها را پاک می‌کند."""
        cfgs = {a["id"]: a for a in config_store.list_accounts()}

        for acc_id in list(self.accounts.keys()):
            if acc_id not in cfgs:
                asyncio.create_task(self.accounts[acc_id].stop())
                del self.accounts[acc_id]

        for acc_id, cfg in cfgs.items():
            if acc_id not in self.accounts:
                self.accounts[acc_id] = AccountManager(cfg)
            else:
                self.accounts[acc_id].cfg = cfg  # به‌روزرسانی تنظیمات (بدون قطع اتصال)

    async def start_account(self, account_id: str):
        self.sync_from_config()
        mgr = self.accounts.get(account_id)
        if mgr:
            await mgr.start()

    async def stop_account(self, account_id: str):
        mgr = self.accounts.get(account_id)
        if mgr:
            await mgr.stop()

    async def start_all(self):
        self.sync_from_config()
        for mgr in self.accounts.values():
            if mgr.cfg.get("enabled", True):
                await mgr.start()

    async def stop_all(self):
        for mgr in self.accounts.values():
            await mgr.stop()

    def refresh_symbols(self, account_id: str):
        """بعد از افزودن/حذف جفت‌ارز از config، اگر حساب در حال اجراست، تسک‌ها را هماهنگ کن."""
        self.sync_from_config()
        mgr = self.accounts.get(account_id)
        if not mgr or not mgr.running:
            return
        active_symbols = {s["symbol"] for s in mgr.cfg.get("symbols", []) if s.get("enabled", True)}
        for symbol in list(mgr.tasks.keys()):
            if symbol not in active_symbols:
                mgr.remove_symbol(symbol)
        for symbol_cfg in mgr.cfg.get("symbols", []):
            if symbol_cfg.get("enabled", True):
                mgr.add_or_update_symbol(symbol_cfg)

    def get_status(self) -> dict:
        self.sync_from_config()
        return {acc_id: mgr.get_status() for acc_id, mgr in self.accounts.items()}


bot_manager = BotManager()
