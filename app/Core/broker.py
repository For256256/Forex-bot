"""
لایه اتصال به حساب‌های MT5 (مثل آلپاری) از طریق سرویس ابری MetaApi.
هر نمونه از MetaApiBroker متناظر با یک حساب مستقل است، بنابراین چند حساب
می‌توانند هم‌زمان و بدون تداخل به کار خودشان ادامه دهند.

نصب: pip install metaapi-cloud-sdk
مستندات رسمی: https://metaapi.cloud/docs/client/
"""
import pandas as pd
from datetime import datetime, timezone

TIMEFRAME_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d",
}


class BrokerError(Exception):
    pass


class MetaApiBroker:
    """اتصال یک حسابِ مشخص به MetaApi. هر حساب یک نمونه جدا از این کلاس دارد."""

    def __init__(self, token: str, account_id: str):
        self.token = token
        self.account_id = account_id
        self._account = None
        self._connection = None
        self._api = None

    async def connect(self):
        try:
            from metaapi_cloud_sdk import MetaApi
        except ImportError as e:
            raise BrokerError("پکیج metaapi-cloud-sdk نصب نیست. دستور: pip install metaapi-cloud-sdk") from e

        if not self.token or not self.account_id:
            raise BrokerError("توکن یا شناسه حساب MetaApi تنظیم نشده است.")

        self._api = MetaApi(self.token)
        self._account = await self._api.metatrader_account_api.get_account(self.account_id)

        if self._account.state != "DEPLOYED":
            await self._account.deploy()
        await self._account.wait_connected()

        self._connection = self._account.get_rpc_connection()
        await self._connection.connect()
        await self._connection.wait_synchronized()

    async def get_candles(self, symbol: str, timeframe: str, count: int = 500) -> pd.DataFrame:
        tf = TIMEFRAME_MAP.get(timeframe, "1h")
        candles = await self._connection.get_candles(symbol, tf, count)
        if not candles:
            raise BrokerError(f"داده کندلی برای {symbol} دریافت نشد.")

        df = pd.DataFrame(candles)
        df = df.rename(columns={"tickVolume": "volume"})
        df = df.sort_values("time").reset_index(drop=True)
        return df[["time", "open", "high", "low", "close", "volume"]]

    async def get_account_info(self) -> dict:
        info = await self._connection.get_account_information()
        return {
            "balance": info.get("balance", 0.0),
            "equity": info.get("equity", 0.0),
            "currency": info.get("currency", "USD"),
            "leverage": info.get("leverage", 0),
        }

    async def get_open_positions(self, symbol: str = None) -> list:
        positions = await self._connection.get_positions()
        if symbol:
            return [p for p in positions if p.get("symbol") == symbol]
        return positions

    async def place_order(self, side: str, symbol: str, volume: float,
                           stop_loss: float = None, take_profit: float = None) -> dict:
        if side == "buy":
            return await self._connection.create_market_buy_order(symbol, volume, stop_loss, take_profit)
        elif side == "sell":
            return await self._connection.create_market_sell_order(symbol, volume, stop_loss, take_profit)
        raise BrokerError(f"سمت سفارش نامعتبر: {side}")

    async def close_position(self, position_id: str) -> dict:
        return await self._connection.close_position(position_id)


class PaperBroker:
    """
    بروکر شبیه‌سازی‌شده (حالت paper). داده کندل واقعی را از MetaApi می‌گیرد
    (در صورت وجود توکن)، اما سفارش واقعی ارسال نمی‌کند.
    """

    def __init__(self, token: str = "", account_id: str = "", starting_balance: float = 10000.0):
        self.balance = starting_balance
        self.equity = starting_balance
        self.positions = []
        self._data_source = None
        self._token = token
        self._account_id = account_id

    async def connect(self):
        if self._token and self._account_id:
            self._data_source = MetaApiBroker(self._token, self._account_id)
            try:
                await self._data_source.connect()
            except Exception:
                self._data_source = None
        return True

    async def get_candles(self, symbol: str, timeframe: str, count: int = 500) -> pd.DataFrame:
        if self._data_source:
            return await self._data_source.get_candles(symbol, timeframe, count)
        raise BrokerError("برای دریافت داده کندل حتی در حالت paper، توکن و شناسه حساب MetaApi لازم است.")

    async def get_account_info(self) -> dict:
        return {"balance": self.balance, "equity": self.equity, "currency": "USD", "leverage": 100}

    async def get_open_positions(self, symbol: str = None) -> list:
        if symbol:
            return [p for p in self.positions if p["symbol"] == symbol]
        return self.positions

    async def place_order(self, side, symbol, volume, stop_loss=None, take_profit=None):
        position = {
            "id": f"paper-{len(self.positions) + 1}-{symbol}",
            "side": side, "symbol": symbol, "volume": volume,
            "stopLoss": stop_loss, "takeProfit": take_profit,
            "openTime": datetime.now(timezone.utc).isoformat(),
        }
        self.positions.append(position)
        return {"orderId": position["id"], "positionId": position["id"]}

    async def close_position(self, position_id: str):
        self.positions = [p for p in self.positions if p["id"] != position_id]
        return {"positionId": position_id, "closed": True}


def build_broker(trading_mode: str, token: str, account_id: str):
    if trading_mode == "live":
        return MetaApiBroker(token, account_id)
    return PaperBroker(token, account_id)
