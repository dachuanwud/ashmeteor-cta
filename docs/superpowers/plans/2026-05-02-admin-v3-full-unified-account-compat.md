# Admin V3 Full Unified Account Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Admin v3 support Binance unified Portfolio Margin accounts across read-only views, manual orders, CTA execution, half-hedge, buy/sell coin workflows, and account value jobs while preserving ordinary-account behavior.

**Architecture:** Centralize endpoint selection in `admin_v3/binance_account.py`, keep existing business functions mostly intact, and route each operation by `account_type` plus market type. Implement in small phases so ordinary accounts continue using current `fapi/dapi/sapi` methods and unified accounts use `papi`.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy, ccxt Binance implicit REST methods, unittest, Admin v3 AMis JSON UI.

---

## Files

- Modify: `admin_v3/binance_account.py` for adapter methods and compatibility helpers.
- Modify: `admin_v3/tests/test_binance_account.py` for adapter unit tests.
- Modify: `admin_v3/functions.py` for read-only account routes, manual order wrappers, buy/sell coin wrappers, and unsupported-operation guards.
- Modify: `admin_v3/schedule_task.py` for U 本位 CTA,净值统计, ADL, TPSL routing.
- Modify: `admin_v3/app.py` for passing `account_type` into functions that currently only receive `exchange`.
- Modify: `admin_v3/templates/admin.json` only when a UI action must call a new unified-safe endpoint or display an unsupported message.
- Create when needed: `admin_v3/tests/test_unified_account_routes.py` for function-level routing tests that do not hit Binance.

## Task 1: Expand Binance Account Adapter

**Files:**
- Modify: `admin_v3/binance_account.py`
- Modify: `admin_v3/tests/test_binance_account.py`

- [ ] **Step 1: Write failing adapter tests**

Add tests that assert:

```python
order = adapter.place_um_order({"symbol": "ETHUSDT"})
self.assertEqual(order["route"], "papi_um")

order = adapter.place_margin_order({"symbol": "ETHUSDT", "side": "BUY"})
self.assertEqual(order["route"], "papi_margin")

orders = adapter.get_open_orders("cm", {"symbol": "ETHUSD_PERP"})
self.assertEqual(orders[0]["route"], "papi_cm_open_orders")

cancel = adapter.cancel_order("um", {"symbol": "ETHUSDT", "orderId": 1})
self.assertEqual(cancel["route"], "papi_um_cancel")
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python3 -m unittest admin_v3.tests.test_binance_account -v`

Expected: tests fail because `place_um_order`, `place_margin_order`, `get_open_orders`, and `cancel_order` are missing.

- [ ] **Step 3: Implement adapter methods**

Implement methods:

```python
def place_um_order(self, params):
    if self.is_unified:
        return self.exchange.papiPostUmOrder(params=params)
    return self._call_exchange(("fapiPrivate_post_order", "fapiPrivatePostOrder"), params=params)

def place_margin_order(self, params):
    if self.is_unified:
        return self.exchange.papiPostMarginOrder(params=params)
    return self._call_exchange(("private_post_order", "privatePostOrder"), params=params)

def get_open_orders(self, market_type, params=None):
    params = params or {}
    if self.is_unified and market_type == "um":
        return self.exchange.papiGetUmOpenOrders(params=params)
    if self.is_unified and market_type == "cm":
        return self.exchange.papiGetCmOpenOrders(params=params)
    if self.is_unified and market_type == "margin":
        return self.exchange.papiGetMarginOpenOrders(params=params)
    if market_type == "um":
        return self._call_exchange(("fapiPrivate_get_openorders", "fapiPrivateGetOpenOrders"), params=params)
    if market_type == "cm":
        return self._call_exchange(("dapiPrivate_get_openorders", "dapiPrivateGetOpenOrders"), params=params)
    return self._call_exchange(("private_get_openorders", "privateGetOpenOrders"), params=params)
```

Add matching `cancel_order()` and `get_user_trades()` with the same market-type switch.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python3 -m unittest admin_v3.tests.test_binance_account -v`

Expected: all adapter tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add admin_v3/binance_account.py admin_v3/tests/test_binance_account.py
git commit -m "Expand Binance unified account adapter"
```

## Task 2: Read-Only Unified Account Views

**Files:**
- Modify: `admin_v3/functions.py`
- Modify: `admin_v3/app.py`
- Test: `admin_v3/tests/test_unified_account_routes.py`

- [ ] **Step 1: Write failing tests for balance and positions**

Create fake exchange and assert unified account balance uses `papiGetAccount` and `papiGetBalance`, UM positions use `papiGetUmPositionRisk`, and CM positions use `papiGetCmPositionRisk`.

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m unittest admin_v3.tests.test_unified_account_routes -v`

Expected: tests fail because function-level wrappers do not exist.

- [ ] **Step 3: Implement read-only wrappers**

Add functions:

```python
def get_account_status_by_type(exchange, account_type, market_type="um"):
    account = make_binance_account_adapter(exchange, account_type)
    if account_type == ACCOUNT_TYPE_UNIFIED:
        return account.get_account_summary()
    if market_type == "cm":
        return get_dapi_account_status(exchange)
    return get_account_status(exchange)
```

Wire Flask routes to pass `get_exchange_account_type(binance_list, strategy)`.

- [ ] **Step 4: Run tests and compile**

Run:

```bash
python3 -m unittest discover -s admin_v3/tests -v
python3 -m py_compile admin_v3/app.py admin_v3/functions.py admin_v3/binance_account.py
```

Expected: tests pass and compile exits 0.

- [ ] **Step 5: Commit**

Run:

```bash
git add admin_v3/app.py admin_v3/functions.py admin_v3/tests/test_unified_account_routes.py
git commit -m "Route unified account read-only views"
```

## Task 3: Manual Order And Order Management

**Files:**
- Modify: `admin_v3/functions.py`
- Modify: `admin_v3/app.py`
- Test: `admin_v3/tests/test_unified_account_routes.py`

- [ ] **Step 1: Write failing route tests**

Assert `/strategy/open_order` uses `place_um_order` for unified UM, `/dapi/strategy/open_order` uses `place_cm_order` for unified CM, open orders use `get_open_orders`, and delete order uses `cancel_order`.

- [ ] **Step 2: Implement wrappers**

Add `open_order_by_type()`, `close_order_by_type()`, `delete_order_by_type()`, and `get_openorders_by_type()` that call the adapter for unified accounts and old functions for standard accounts.

- [ ] **Step 3: Run tests**

Run:

```bash
python3 -m unittest discover -s admin_v3/tests -v
python3 -m py_compile admin_v3/app.py admin_v3/functions.py
```

Expected: tests pass and compile exits 0.

- [ ] **Step 4: Commit**

Run:

```bash
git add admin_v3/app.py admin_v3/functions.py admin_v3/tests/test_unified_account_routes.py
git commit -m "Route manual orders through account adapter"
```

## Task 4: U 本位 CTA Unified Routing

**Files:**
- Modify: `admin_v3/schedule_task.py`
- Modify: `admin_v3/functions.py`
- Modify: `admin_v3/app.py`
- Test: `admin_v3/tests/test_unified_account_routes.py`

- [ ] **Step 1: Write failing tests**

Assert U 本位 CTA position check and order execution call `get_um_position_risk` and `place_um_order` when `account_type == "unified"`.

- [ ] **Step 2: Implement U 本位 CTA routing**

Pass account type through `cta_usdt_start`, `cta_usdt_start_all`, `cta_excute_init`, `cta_excute_period`, `cta_check_position`, `cta_usdt_stop_after`, and `cta_usdt_tpsl_close_order`.

- [ ] **Step 3: Run tests**

Run:

```bash
python3 -m unittest discover -s admin_v3/tests -v
python3 -m py_compile admin_v3/app.py admin_v3/functions.py admin_v3/schedule_task.py
```

Expected: tests pass and compile exits 0.

- [ ] **Step 4: Commit**

Run:

```bash
git add admin_v3/app.py admin_v3/functions.py admin_v3/schedule_task.py admin_v3/tests/test_unified_account_routes.py
git commit -m "Support unified account UM CTA"
```

## Task 5: Buy/Sell Coin Unified Workflow

**Files:**
- Modify: `admin_v3/functions.py`
- Modify: `admin_v3/app.py`
- Modify: `admin_v3/templates/admin.json`
- Test: `admin_v3/tests/test_unified_account_routes.py`

- [ ] **Step 1: Write failing tests**

Assert `buy_coin_by_type(exchange, ACCOUNT_TYPE_UNIFIED, "ETH", "quote", "1000")` builds a `papiPostMarginOrder` request with `symbol="ETHUSDT"`, `side="BUY"`, `type="MARKET"`, and `quoteOrderQty="1000"`.

- [ ] **Step 2: Implement unified buy/sell wrappers**

Add:

```python
def buy_coin_by_type(exchange, account_type, asset, mode, num, balance):
    if account_type == ACCOUNT_TYPE_UNIFIED:
        quote_qty = str(num if mode == "quote" else balance)
        return make_binance_account_adapter(exchange, account_type).place_margin_order({
            "symbol": f"{asset}USDT",
            "side": "BUY",
            "type": "MARKET",
            "quoteOrderQty": quote_qty,
            "sideEffectType": "NO_SIDE_EFFECT",
        })
    return dapi_buy_coin_and_transfer(exchange, asset, mode, num, balance)
```

Add `sell_coin_by_type()` similarly with `side="SELL"` and `quantity`.

- [ ] **Step 3: Wire routes and UI**

Pass account type in `/dapi/buy_coin`, `/dapi/sell_coin`, and show a confirm text for unified accounts that says the action uses Portfolio Margin margin order.

- [ ] **Step 4: Run tests and compile**

Run:

```bash
python3 -m unittest discover -s admin_v3/tests -v
python3 -m py_compile admin_v3/app.py admin_v3/functions.py
```

Expected: tests pass and compile exits 0.

- [ ] **Step 5: Commit**

Run:

```bash
git add admin_v3/app.py admin_v3/functions.py admin_v3/templates/admin.json admin_v3/tests/test_unified_account_routes.py
git commit -m "Support unified account buy and sell coin actions"
```

## Task 6: Account Value And Background Jobs

**Files:**
- Modify: `admin_v3/schedule_task.py`
- Modify: `admin_v3/functions.py`
- Test: `admin_v3/tests/test_unified_account_routes.py`

- [ ] **Step 1: Write failing tests**

Assert account value functions skip old fapi/dapi balance readers for unified accounts and use `papiGetAccount` plus `papiGetBalance`.

- [ ] **Step 2: Implement unified net value calculation**

For unified accounts, calculate net value from `accountEquity` and asset rows from `/papi/v1/balance`. Keep ordinary-account SQL table names unchanged.

- [ ] **Step 3: Run tests and compile**

Run:

```bash
python3 -m unittest discover -s admin_v3/tests -v
python3 -m py_compile admin_v3/schedule_task.py admin_v3/functions.py
```

Expected: tests pass and compile exits 0.

- [ ] **Step 4: Commit**

Run:

```bash
git add admin_v3/functions.py admin_v3/schedule_task.py admin_v3/tests/test_unified_account_routes.py
git commit -m "Support unified account value jobs"
```

## Task 7: Server Deploy And Verification

**Files:**
- No code changes.

- [ ] **Step 1: Push main**

Run: `git push origin main`

Expected: GitHub reports `main -> main`.

- [ ] **Step 2: Deploy to server**

Run on server:

```bash
cd /home/ubuntu/ashmeteor-cta
git pull --ff-only origin main
cd admin_v3
/home/ubuntu/admin_v3_venv/bin/python -m unittest discover -s tests -v
/home/ubuntu/admin_v3_venv/bin/python -m py_compile app.py functions.py schedule_task.py binance_account.py
sudo systemctl restart admin_v3.service
systemctl is-active admin_v3.service
```

Expected: tests pass, compile exits 0, service prints `active`.

- [ ] **Step 3: Run only read-only unified verification**

Run a script that calls `/papi/v1/account`, `/papi/v1/balance`, `/papi/v1/um/positionRisk`, and `/papi/v1/cm/positionRisk`. Do not place orders.

Expected: script prints `account_type: unified` and returns account rows without exceptions.

- [ ] **Step 4: Browser visual check**

Open `http://43.163.203.195:5000/login`, log in, inspect the unified account pages, and confirm read-only tables load. Do not click buy, sell, force half, start CTA, or order buttons during verification.
