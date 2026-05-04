import os
import sys
import tempfile
import unittest
from decimal import Decimal
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import schedule_task
from functions import (calculate_unified_halfset_targets,
                       reconcile_unified_halfset_position,
                       cta_unified_halfset_sync_last_signal,
                       cta_unified_margin_rebalance_run_items)


class _NoopContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeApp:
    def app_context(self):
        return _NoopContext()


class HalfsetExchange:
    def __init__(self,
                 asset='ETH',
                 asset_qty='0.4372623',
                 position_amt='-0.218',
                 step_size='0.000001',
                 min_qty='0.001'):
        self.asset = asset
        self.symbol = f'{asset}USDT'
        self.asset_qty = asset_qty
        self.position_amt = position_amt
        self.step_size = step_size
        self.min_qty = min_qty
        self.orders = []

    def papiGetBalance(self):
        return [{
            'asset': self.asset,
            'totalWalletBalance': self.asset_qty,
            'crossMarginFree': self.asset_qty,
            'crossMarginLocked': '0',
            'crossMarginBorrowed': '0',
            'crossMarginInterest': '0',
            'umWalletBalance': '0',
            'umUnrealizedPNL': '0',
            'cmWalletBalance': '0',
            'cmUnrealizedPNL': '0',
        }]

    def papiGetUmPositionRisk(self, params=None):
        return [{
            'symbol': params.get('symbol', self.symbol),
            'positionAmt': self.position_amt,
        }]

    def fapiPublic_get_exchangeinfo(self):
        return {
            'symbols': [{
                'symbol': self.symbol,
                'status': 'TRADING',
                'filters': [{
                    'filterType': 'MARKET_LOT_SIZE',
                    'minQty': self.min_qty,
                    'stepSize': self.step_size,
                }, {
                    'filterType': 'MIN_NOTIONAL',
                    'notional': '5',
                }],
            }]
        }

    def fapiPublicGetTicker24hr(self, params=None):
        return {'symbol': self.symbol, 'lastPrice': '2500'}

    def papiPostUmOrder(self, params=None):
        self.orders.append(params)
        return {'orderId': 'halfset-order-1', 'params': params}


class HalfsetTargetCalculationTest(unittest.TestCase):
    def test_auto_remaining_signal_targets_match_halfset_formula(self):
        base_qty = Decimal('0.4372623')

        long_targets = calculate_unified_halfset_targets(base_qty, '0.5', 1)
        flat_targets = calculate_unified_halfset_targets(base_qty, '0.5', 0)
        short_targets = calculate_unified_halfset_targets(base_qty, '0.5', -1)

        self.assertEqual(long_targets['half_target_qty'],
                         Decimal('-0.21863115'))
        self.assertEqual(long_targets['cta_target_qty'],
                         Decimal('0.21863115'))
        self.assertEqual(long_targets['total_target_qty'], Decimal('0E-8'))
        self.assertEqual(flat_targets['total_target_qty'],
                         Decimal('-0.21863115'))
        self.assertEqual(short_targets['total_target_qty'],
                         Decimal('-0.43726230'))

    def test_manual_usd_sizing_uses_budget_price_and_trade_ratio(self):
        targets = calculate_unified_halfset_targets(
            Decimal('0.5'),
            '0.5',
            1,
            cta_sizing_mode='manual_usd',
            cta_budget_usd='250',
            cta_trade_ratio='2',
            last_price='2500',
        )

        self.assertEqual(targets['half_target_qty'], Decimal('-0.25'))
        self.assertEqual(targets['cta_target_qty'], Decimal('0.2'))
        self.assertEqual(targets['total_target_qty'], Decimal('-0.05'))


class HalfsetReconcileTest(unittest.TestCase):
    def test_preview_builds_single_total_target_order_without_live_order(self):
        exchange = HalfsetExchange()

        res = reconcile_unified_halfset_position(
            exchange,
            'admin_v3_unified',
            'ETH',
            hedge_ratio='0.5',
            cta_signal=1,
            live_trade_enabled=False,
        )

        self.assertEqual(res['status'], 0)
        self.assertEqual(res['msg'], '完整半套协调预览完成，未真实下单')
        data = res['data']
        self.assertEqual(data['half_target_qty'], Decimal('-0.21863115'))
        self.assertEqual(data['cta_target_qty'], Decimal('0.21863115'))
        self.assertEqual(data['total_target_qty'], Decimal('0E-8'))
        self.assertEqual(data['current_um_position'], Decimal('-0.218'))
        self.assertEqual(data['order']['side'], 'BUY')
        self.assertEqual(data['order']['quantity'], '0.218000')
        self.assertTrue(data['order']['reduceOnly'])
        self.assertEqual(exchange.orders, [])

    def test_execute_routes_the_only_real_order_through_papi_um_order(self):
        exchange = HalfsetExchange(position_amt='-0.218')

        res = reconcile_unified_halfset_position(
            exchange,
            'admin_v3_unified',
            'ETH',
            hedge_ratio='0.5',
            cta_signal=1,
            live_trade_enabled=True,
        )

        self.assertEqual(res['status'], 0)
        self.assertEqual(res['msg'], '完整半套协调执行成功')
        self.assertEqual(len(exchange.orders), 1)
        self.assertEqual(exchange.orders[0]['symbol'], 'ETHUSDT')
        self.assertEqual(exchange.orders[0]['side'], 'BUY')
        self.assertEqual(exchange.orders[0]['quantity'], '0.218000')

    def test_missing_um_symbol_returns_clear_error(self):
        exchange = HalfsetExchange(asset='BTC')
        exchange.fapiPublic_get_exchangeinfo = lambda: {'symbols': []}

        res = reconcile_unified_halfset_position(
            exchange,
            'admin_v3_unified',
            'BTC',
            hedge_ratio='0.5',
            cta_signal=1,
        )

        self.assertEqual(res['status'], 500)
        self.assertIn('BTCUSDT不支持完整半套模式', res['msg'])


class HalfsetExecutionIsolationTest(unittest.TestCase):
    def test_sync_last_signal_recomputes_last_effective_signal_from_klines(self):
        klines = pd.DataFrame({
            'candle_begin_time': pd.date_range('2026-01-01',
                                               periods=5,
                                               freq='4h'),
            'open': [1, 2, 3, 4, 5],
            'high': [1, 2, 3, 4, 5],
            'low': [1, 2, 3, 4, 5],
            'close': [1, 2, 3, 4, 5],
            'volume': [1, 1, 1, 1, 1],
        })
        signal_df = klines.copy()
        signal_df['signal'] = [0, None, 1, None, None]

        class HalfsetItem:
            cta_key = 'ETHUSDT_4h_adapt_bolling_anti_chase_[200,20]'
            strategy = 'admin_v3_unified'
            asset = 'ETH'
            hedge_symbol = 'ETHUSDT'
            interval = '4h'
            cta = 'adapt_bolling_anti_chase'
            period = '[200,20]'

            def to_dict(self):
                return {
                    'cta_key': self.cta_key,
                    'strategy': self.strategy,
                    'asset': self.asset,
                    'hedge_symbol': self.hedge_symbol,
                    'interval': self.interval,
                    'cta': self.cta,
                    'period': self.period,
                }

        with mock.patch('functions.cta_unified_halfset_get_active',
                        return_value=HalfsetItem()), \
                mock.patch('functions.cta_usdt_get_trade_info',
                           return_value={
                               'strategy': 'admin_v3_unified',
                               'symbol': 'ETHUSDT',
                               'interval': '4h',
                               'signal': 0,
                           }), \
                mock.patch('functions.get_kline', return_value=klines), \
                mock.patch('functions.factors.parse_cta_period',
                           return_value=[200, 20]), \
                mock.patch('functions.factors.adapt_bolling_anti_chase',
                           return_value=(signal_df, None)), \
                mock.patch('functions.cta_unified_halfset_handle_cta_signal',
                           return_value={'status': 0}) as handle:
            res = cta_unified_halfset_sync_last_signal(
                object(), {
                    'strategy': 'admin_v3_unified',
                    'asset': 'ETH',
                })

        self.assertEqual(res['status'], 0)
        handle.assert_called_once()
        self.assertEqual(handle.call_args.args[2], 1)

    def test_cta_period_delegates_to_halfset_coordinator_without_direct_cta_order(self):
        klines = pd.DataFrame({
            'candle_begin_time': pd.date_range('2026-01-01', periods=3, freq='4h'),
            'open': [1, 2, 3],
            'high': [1, 2, 3],
            'low': [1, 2, 3],
            'close': [1, 2, 3],
            'volume': [1, 1, 1],
        })
        signal_df = klines.copy()
        signal_df['signal'] = [None, 1, None]

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(
                temp_dir, 'ETHUSDT_4h_adapt_bolling_anti_chase_[200,20].csv')
            klines.to_csv(path, index=False)

            with mock.patch.object(schedule_task.scheduler, 'app', _FakeApp()), \
                    mock.patch.object(schedule_task, 'fapi_path', temp_dir), \
                    mock.patch.object(schedule_task, 'get_kline',
                                      return_value=klines), \
                    mock.patch.object(schedule_task.factors,
                                      'parse_cta_period',
                                      return_value=[200, 20]), \
                    mock.patch.object(schedule_task.factors,
                                      'adapt_bolling_anti_chase',
                                      return_value=(signal_df, None)), \
                    mock.patch.object(schedule_task,
                                      'cta_usdt_get_trade_info',
                                      return_value={
                                          'strategy': 'admin_v3_unified',
                                          'signal': 0,
                                          'net_value': 500,
                                          'trade_ratio': 1,
                                          'position_amount': 0,
                                      }), \
                    mock.patch.object(schedule_task,
                                      'cta_unified_halfset_get_active_by_cta_key',
                                      return_value={
                                          'strategy': 'admin_v3_unified',
                                          'asset': 'ETH',
                                          'hedge_ratio': Decimal('0.5'),
                                          'live_trade_enabled': 1,
                                          'cta_sizing_mode': 'auto_remaining',
                                          'cta_budget_usd': Decimal('0'),
                                          'cta_trade_ratio': Decimal('1'),
                                      }), \
                    mock.patch.object(schedule_task,
                                      'cta_unified_halfset_handle_cta_signal',
                                      return_value={'status': 0}) as handle, \
                    mock.patch.object(schedule_task,
                                      'cta_usdt_open_limit_order') as direct:
                schedule_task.cta_excute_period(
                    object(),
                    'ETHUSDT',
                    '4h',
                    'adapt_bolling_anti_chase',
                    '[200,20]',
                    'unified',
                    pos_infer=True,
                )

        direct.assert_not_called()
        handle.assert_called_once()
        self.assertEqual(handle.call_args.args[2], 1)

    def test_unified_margin_rebalance_delegates_to_halfset_instead_of_legacy_order(self):
        with mock.patch('functions.get_exchange', return_value=object()), \
                mock.patch('functions.cta_unified_halfset_get_active',
                           return_value={
                               'strategy': 'admin_v3_unified',
                               'asset': 'ETH',
                               'hedge_ratio': Decimal('0.5'),
                           }), \
                mock.patch('functions.reconcile_unified_halfset_position',
                           return_value={'status': 0,
                                         'msg': 'coordinated',
                                         'data': {}}) as reconcile, \
                mock.patch('functions.rebalance_unified_margin_asset') as legacy:
            res = cta_unified_margin_rebalance_run_items([{
                'strategy': 'admin_v3_unified',
                'exchange': object(),
            }], [{
                'strategy': 'admin_v3_unified',
                'asset': 'ETH',
                'hedge_ratio': Decimal('0.5'),
                'is_running': 1,
                'live_trade_enabled': 1,
                'hedge_market': 'um',
            }])

        self.assertEqual(res['status'], 0)
        self.assertEqual(res['data']['items'][0]['msg'], 'coordinated')
        reconcile.assert_called_once()
        legacy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
