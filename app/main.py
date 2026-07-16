import secrets
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from pydantic import BaseModel
from typing import Optional

from app.config import settings
from app.core.engine import bot_manager
from app.core import config_store

app = FastAPI(title="فارکس بات")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
security = HTTPBasic()


@app.on_event("startup")
async def on_startup():
    config_store.migrate_from_env_if_needed()
    bot_manager.sync_from_config()


def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    if not settings.DASHBOARD_PASSWORD:
        return True
    ok_user = secrets.compare_digest(credentials.username, settings.DASHBOARD_USER)
    ok_pass = secrets.compare_digest(credentials.password, settings.DASHBOARD_PASSWORD)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="نام کاربری یا رمز عبور اشتباه است",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


class AccountIn(BaseModel):
    name: str
    trading_mode: str = "paper"
    metaapi_token: str = ""
    metaapi_account_id: str = ""
    risk_percent: float = 1.0
    max_open_positions: int = 1
    max_daily_loss_percent: float = 5.0
    poll_interval_seconds: int = 60
    enabled: bool = True


class SymbolIn(BaseModel):
    symbol: str
    timeframe: str = "1h"
    enabled: bool = True
    atr_period: int = 10
    st_factor: float = 3.0
    ema_fast: int = 50
    ema_slow: int = 200
    rsi_period: int = 14
    rsi_buy_level: float = 55
    rsi_sell_level: float = 45
    sl_atr_mult: float = 2.0
    tp_atr_mult: float = 4.0
    pip_value_per_lot: Optional[float] = None


# ---------- صفحه داشبورد ----------
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, _: bool = Depends(require_auth)):
    return templates.TemplateResponse("dashboard.html", {"request": request})


# ---------- وضعیت کلی ----------
@app.get("/api/status")
async def api_status(_: bool = Depends(require_auth)):
    return bot_manager.get_status()


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ---------- مدیریت حساب‌ها ----------
@app.get("/api/accounts")
async def get_accounts(_: bool = Depends(require_auth)):
    return config_store.list_accounts()


@app.post("/api/accounts")
async def create_account(payload: AccountIn, _: bool = Depends(require_auth)):
    account = config_store.add_account(payload.dict())
    bot_manager.sync_from_config()
    return account


@app.put("/api/accounts/{account_id}")
async def edit_account(account_id: str, payload: AccountIn, _: bool = Depends(require_auth)):
    try:
        account = config_store.update_account(account_id, payload.dict())
    except KeyError as e:
        raise HTTPException(404, str(e))
    bot_manager.sync_from_config()
    return account


@app.delete("/api/accounts/{account_id}")
async def remove_account(account_id: str, _: bool = Depends(require_auth)):
    await bot_manager.stop_account(account_id)
    config_store.delete_account(account_id)
    bot_manager.sync_from_config()
    return {"deleted": account_id}


@app.post("/api/accounts/{account_id}/start")
async def start_account(account_id: str, _: bool = Depends(require_auth)):
    await bot_manager.start_account(account_id)
    return bot_manager.get_status().get(account_id)


@app.post("/api/accounts/{account_id}/stop")
async def stop_account(account_id: str, _: bool = Depends(require_auth)):
    await bot_manager.stop_account(account_id)
    return bot_manager.get_status().get(account_id)


@app.post("/api/start-all")
async def start_all(_: bool = Depends(require_auth)):
    await bot_manager.start_all()
    return bot_manager.get_status()


@app.post("/api/stop-all")
async def stop_all(_: bool = Depends(require_auth)):
    await bot_manager.stop_all()
    return bot_manager.get_status()


# ---------- مدیریت جفت‌ارزها در هر حساب ----------
@app.post("/api/accounts/{account_id}/symbols")
async def add_symbol(account_id: str, payload: SymbolIn, _: bool = Depends(require_auth)):
    try:
        symbol_cfg = config_store.add_symbol(account_id, payload.dict())
    except KeyError as e:
        raise HTTPException(404, str(e))
    bot_manager.refresh_symbols(account_id)
    return symbol_cfg


@app.delete("/api/accounts/{account_id}/symbols/{symbol}")
async def delete_symbol(account_id: str, symbol: str, _: bool = Depends(require_auth)):
    try:
        config_store.remove_symbol(account_id, symbol)
    except KeyError as e:
        raise HTTPException(404, str(e))
    bot_manager.refresh_symbols(account_id)
    return {"deleted": symbol}


@app.post("/api/accounts/{account_id}/symbols/{symbol}/toggle")
async def toggle_symbol(account_id: str, symbol: str, enabled: bool, _: bool = Depends(require_auth)):
    try:
        config_store.toggle_symbol(account_id, symbol, enabled)
    except KeyError as e:
        raise HTTPException(404, str(e))
    bot_manager.refresh_symbols(account_id)
    return {"symbol": symbol, "enabled": enabled}
