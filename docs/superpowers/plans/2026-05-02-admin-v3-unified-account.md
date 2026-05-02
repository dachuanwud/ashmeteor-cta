# Admin V3 Unified Account Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Binance unified account support to Admin v3 for ETH coin-margined half-hedge execution without breaking existing ordinary accounts.

**Architecture:** Add an `account_type` field to strategy accounts, expose it in the Admin UI, and route coin-margined account/order calls through a small adapter that normalizes ordinary `/dapi` and unified `/papi` responses. Tighten half-hedge scheduling so records must be explicitly running before automated rebalancing can place orders.

**Tech Stack:** Flask, Flask-SQLAlchemy, SQLAlchemy 1.4, ccxt 4.x, AMis JSON UI, Python `unittest`.

---

### Task 1: Strategy Account Type

**Files:**
- Modify: `admin_v3/model.py`
- Modify: `admin_v3/sql/init.sql`
- Modify: `admin_v3/sql/strategy.sql`
- Modify: `admin_v3/functions.py`
- Modify: `admin_v3/templates/admin.html`

- [x] Add `account_type` to `Strategy` with default `standard`.
- [x] Include `account_type` in account creation, account list, binance list, strategy row, and strategy update.
- [x] Add a required UI select with values `standard` and `unified`.
- [x] Run `python3 -m py_compile admin_v3/model.py admin_v3/functions.py`.

### Task 2: Binance Account Adapter

**Files:**
- Create: `admin_v3/binance_account.py`
- Create: `admin_v3/tests/test_binance_account.py`

- [x] Implement `BinanceAccountAdapter` with normalized methods for standard and unified accounts.
- [x] Route standard methods to current `dapi` calls.
- [x] Route unified methods to `papi` calls.
- [x] Add fake-exchange tests for balance normalization, position normalization, and order routing.
- [x] Run `python3 -m unittest discover -s admin_v3/tests -v`.

### Task 3: Half-Hedge Routing And Safety

**Files:**
- Modify: `admin_v3/schedule_task.py`
- Modify: `admin_v3/functions.py`

- [x] Update scheduled `cta_usd_rebalance` to skip half-hedge rows unless `is_running=1`.
- [x] Replace direct coin-margined account/order calls in half-hedge paths with the adapter.
- [x] Keep force-rebalance behavior explicit, but route it through the adapter.
- [x] Run syntax compile and adapter tests.

### Task 4: Deployment Sync

**Files:**
- Git repository and remote server.

- [x] Commit all Admin v3 design and implementation files while leaving unrelated `crypto_cta` changes unstaged.
- [x] Push `main` to GitHub.
- [x] Pull `main` on `43.163.203.195`.
- [x] Apply `ALTER TABLE strategy ADD COLUMN account_type ...` only if the column is missing.
- [x] Restart `admin_v3.service`.
- [x] Verify service status and `/` health.
