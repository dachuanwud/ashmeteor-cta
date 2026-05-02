# Admin v3 Unified Account Design

## Goal

Admin v3 must support Binance unified accounts for the ETH coin-margined half-hedge workflow while preserving existing ordinary Binance account behavior.

The first production target is:

- account type: Binance unified account
- strategy symbol: `ETHUSD_PERP`
- CTA: `adapt_bolling`
- half-hedge module: coin-margined rebalance

## Current State

Admin v3 stores Binance accounts in the `strategy` table and builds a `ccxt.binance` instance for each row. The row does not record account type.

Most Binance calls are direct `fapiPrivate*` and `dapiPrivate*` calls. The coin-margined half-hedge flow in `cta_usd_rebalance` reads `dapiPrivate_get_account`, scans coin wallet balances, reads coin-margined positions, and places coin-margined orders through `dapiPrivate_post_order`.

The half-hedge scheduler runs every 16 minutes. Existing code does not require a half-hedge row to be running before it can rebalance, so creating a row can create real orders later.

## Binance API Boundary

Ordinary coin-margined futures accounts continue to use the existing `/dapi` calls.

Binance unified account support uses Portfolio Margin `/papi` endpoints:

- `GET /papi/v1/account` for unified risk and account status.
- `GET /papi/v1/balance` for consolidated asset balances, including `cmWalletBalance` and `cmUnrealizedPNL`.
- `GET /papi/v1/cm/positionRisk` for coin-margined positions.
- `POST /papi/v1/cm/order` for coin-margined orders.

The implementation uses the existing `ccxt.binance` object because the installed Python 3.12 `ccxt` supports the required `papi*` methods.

## Design

### Account Type

Add `account_type` to `strategy`:

- `standard`: existing ordinary account behavior.
- `unified`: Binance unified account / Portfolio Margin behavior.

The default is `standard` to avoid changing existing accounts.

The Admin v3 strategy account form shows a required account type select. Strategy list and edit APIs return the account type.

### Binance Account Adapter

Create a small adapter module for account-specific Binance operations. It wraps the `ccxt.binance` object and exposes methods used by half-hedge code:

- `get_account()`
- `get_assets()`
- `get_positions()`
- `get_cm_position_map()`
- `get_cm_perp_base_assets()`
- `get_cm_ticker_prices()`
- `place_cm_limit_order()`

`standard` adapters map these methods to existing `/dapi` behavior.

`unified` adapters map these methods to `/papi` behavior and normalize the result into the shape the half-hedge code expects:

- unified balance `cmWalletBalance + cmUnrealizedPNL` becomes `marginBalance`.
- unified position risk `positionAmt` becomes the position map input.
- unified coin-margined order placement calls `papiPostCmOrder`.

### Half-Hedge Safety

`cta_usd_rebalance` only processes rows that are explicitly running. This prevents a newly created unified-account half-hedge record from creating real orders before the user arms it.

Force rebalance endpoints remain explicit actions and still place orders when called. They use the same adapter layer so ordinary and unified accounts share one business rule.

### ETH Half-Hedge Workflow

The intended first run is:

1. Add a Binance strategy account and choose `unified`.
2. Verify account status through read-only `/papi` account and balance calls.
3. Create `ETHUSD_PERP` `adapt_bolling` CTA strategy.
4. Create `ETHUSD_PERP_rebalance` with a small trade ratio such as `0.1` or `0.2`.
5. Keep rebalance stopped during verification.
6. Start or force rebalance only after the user explicitly confirms live trading.

## Error Handling

If a unified account lacks Portfolio Margin permissions or `/papi` access, Admin v3 returns the Binance error and does not fall back to `/dapi`.

If an account type is unknown, Admin v3 treats it as `standard` for backward compatibility in old databases, but the UI only offers `standard` and `unified`.

Order submission keeps the existing limit-order behavior and adds `positionSide=BOTH` unless a future hedge-mode check proves another value is required.

## Testing

The change is verified in four layers:

1. Syntax compile of changed Python files.
2. Unit tests for the adapter normalization logic using fake exchange objects.
3. Regression test that standard account calls still route to `dapi`.
4. Manual production verification through read-only unified account endpoints before any live order.

Live order placement is not part of automated verification.

## Deployment

Database migration:

```sql
ALTER TABLE strategy
  ADD COLUMN account_type varchar(32) NOT NULL DEFAULT 'standard' COMMENT '账户类型: standard普通账户 unified统一账户'
  AFTER is_main;
```

After code is pushed to GitHub, the server pulls the latest `main`, applies the database migration if needed, and restarts `admin_v3.service`.
