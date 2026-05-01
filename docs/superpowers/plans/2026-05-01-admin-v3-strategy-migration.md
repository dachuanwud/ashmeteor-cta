# Admin V3 Strategy Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the admin_v3 Bollinger-family strategies and DC flash strategy into the crypto_cta factor-module architecture.

**Architecture:** Keep one strategy module per `crypto_cta/factors/<strategy>.py`, each exporting `signal()` and `para_list()`. Share copied formula primitives in `crypto_cta/factors/_admin_v3_utils.py` so signal merging, adaptive Bollinger bands, ATR, WMA, CCI, and stop-loss integration remain consistent.

**Tech Stack:** Python, pandas, numpy, unittest, existing `cta_api.function.process_stop_loss_close`.

---

### Task 1: Migration Behavior Tests

**Files:**
- Create: `crypto_cta/tests/test_admin_v3_strategy_migration.py`

- [ ] **Step 1: Write failing tests**

Cover `adapt_bolling`, `adapt_bolling_reverse`, `dc_flash`, and a representative template strategy such as `mtm_bolling`.

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=. python3 -m unittest crypto_cta.tests.test_admin_v3_strategy_migration -v`
Expected: FAIL because migrated modules do not exist.

### Task 2: Shared Utilities

**Files:**
- Create: `crypto_cta/factors/_admin_v3_utils.py`

- [ ] **Step 1: Implement shared helpers**

Add helpers for WMA, ATR, CCI, signal deduplication, stop-loss wrapping, adaptive Bollinger formatter, and DC flash logic support.

- [ ] **Step 2: Run tests**

Run the migration test file. Expected: still FAIL until factor modules exist.

### Task 3: Strategy Modules

**Files:**
- Create: one module per migrated strategy under `crypto_cta/factors/`.

- [ ] **Step 1: Add thin modules**

Each module delegates formula work to `_admin_v3_utils.py`, then calls `process_stop_loss_close()`.

- [ ] **Step 2: Run tests**

Run existing and new tests. Expected: PASS.

### Task 4: Integration Check

**Files:**
- Existing tests under `crypto_cta/tests/`.

- [ ] **Step 1: Run full test suite**

Run: `PYTHONPATH=. python3 -m unittest discover -s crypto_cta/tests -v`
Expected: PASS.
