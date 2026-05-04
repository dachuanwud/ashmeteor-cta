import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from functions import (cta_unified_overlay_deploy,
                       cta_unified_overlay_get_summary,
                       cta_unified_overlay_update_cta,
                       cta_unified_overlay_update_rebalance)


class UnifiedOverlayTest(unittest.TestCase):
    def test_overlay_summary_combines_rebalance_and_cta_state(self):
        overview = {'status': 0, 'data': {'strategy': 'admin_v3_unified'}}
        dashboard = {
            'status': 0,
            'data': {
                'items': [{
                    'strategy': 'admin_v3_unified',
                    'base_asset_qty': 0.5,
                    'base_asset_usd': 1500,
                    'hedge_ratio': 0.5,
                    'target_hedge_qty': 0.25,
                    'current_um_position': -0.3,
                    'net_base_exposure': 0.2,
                    'rebalance_running': '已启动',
                    'live_trade_enabled': '关闭',
                    'next_action_hint': '真实下单关闭，定时巡检只会生成预览',
                }]
            }
        }
        cta = SimpleNamespace(strategy='admin_v3_unified',
                              cta_key='ETHUSDT_4h_adapt_bolling_anti_chase_[200,20]',
                              is_running=1,
                              trade_ratio='1.5',
                              signal=-1,
                              position_amount='-0.12',
                              init_value='50',
                              net_value='51.2',
                              open_tpsl=1,
                              takeprofit_percentage='0.5',
                              takeprofit_drawdown_percentage='0.05',
                              stoploss_percentage='0.2')

        with patch('functions.get_exchange', return_value=object()), \
                patch('functions.get_exchange_account_type',
                      return_value='unified'), \
                patch('functions.get_account_v2_overview',
                      return_value=overview), \
                patch('functions.get_account_v2_overview_section',
                      return_value=dashboard), \
                patch('functions.cta_unified_overlay_find_cta',
                      return_value=cta):
            res = cta_unified_overlay_get_summary([], 'admin_v3_unified',
                                                  'ETH')

        item = res['data']['items'][0]
        self.assertEqual(res['status'], 0)
        self.assertEqual(item['base_asset_qty'], 0.5)
        self.assertEqual(item['rebalance_running'], '已启动')
        self.assertTrue(item['cta_exists'])
        self.assertEqual(item['cta_running'], '已启动')
        self.assertEqual(item['cta_trade_ratio'], '1.5')
        self.assertEqual(item['cta_signal'], -1)
        self.assertEqual(item['cta_position_amount'], '-0.12')
        self.assertEqual(item['recommended_cta_base_qty'], 0.25)
        self.assertEqual(item['recommended_cta_notional_usd'], 750.0)
        self.assertEqual(item['recommended_trade_ratio'], 1.0)
        self.assertEqual(item['recommended_cta_init_value'], 750.0)
        self.assertEqual(item['cta_exposure_if_long'], 0.5)
        self.assertEqual(item['cta_exposure_if_flat'], 0.25)
        self.assertEqual(item['cta_exposure_if_short'], 0.0)
        self.assertIn('剩余半仓', item['cta_overlay_coverage_note'])
        self.assertEqual(item['next_action_hint'], '半套和CTA overlay已配置运行，关注净ETH暴露')

    def test_overlay_summary_recommends_remaining_half_position_size(self):
        overview = {'status': 0, 'data': {'strategy': 'admin_v3_unified'}}
        dashboard = {
            'status': 0,
            'data': {
                'items': [{
                    'strategy': 'admin_v3_unified',
                    'base_asset_qty': 0.4372623,
                    'base_asset_usd': 1000,
                    'hedge_ratio': 0.5,
                    'target_hedge_qty': 0.21863115,
                    'current_um_position': -0.218,
                    'net_base_exposure': 0.2192623,
                    'rebalance_running': '已启动',
                    'live_trade_enabled': '已开启',
                }]
            }
        }

        with patch('functions.get_exchange', return_value=object()), \
                patch('functions.get_exchange_account_type',
                      return_value='unified'), \
                patch('functions.get_account_v2_overview',
                      return_value=overview), \
                patch('functions.get_account_v2_overview_section',
                      return_value=dashboard), \
                patch('functions.cta_unified_overlay_find_cta',
                      return_value=None):
            res = cta_unified_overlay_get_summary([], 'admin_v3_unified',
                                                  'ETH')

        item = res['data']['items'][0]
        self.assertEqual(item['recommended_cta_base_qty'], 0.21863115)
        self.assertEqual(item['recommended_cta_notional_usd'], 500.0)
        self.assertEqual(item['recommended_trade_ratio'], 1.0)
        self.assertEqual(item['recommended_cta_init_value'], 500.0)
        self.assertEqual(item['cta_exposure_if_long'], 0.4372623)
        self.assertEqual(item['cta_exposure_if_flat'], 0.21863115)
        self.assertEqual(item['cta_exposure_if_short'], 0.0)

    def test_overlay_summary_recommends_lower_init_value_for_higher_trade_ratio(self):
        overview = {'status': 0, 'data': {'strategy': 'admin_v3_unified'}}
        dashboard = {
            'status': 0,
            'data': {
                'items': [{
                    'strategy': 'admin_v3_unified',
                    'base_asset_qty': 0.5,
                    'base_asset_usd': 1000,
                    'hedge_ratio': 0.5,
                    'target_hedge_qty': 0.25,
                    'current_um_position': -0.25,
                    'rebalance_running': '已启动',
                }]
            }
        }

        with patch('functions.get_exchange', return_value=object()), \
                patch('functions.get_exchange_account_type',
                      return_value='unified'), \
                patch('functions.get_account_v2_overview',
                      return_value=overview), \
                patch('functions.get_account_v2_overview_section',
                      return_value=dashboard), \
                patch('functions.cta_unified_overlay_find_cta',
                      return_value=None):
            res = cta_unified_overlay_get_summary(
                [], 'admin_v3_unified', 'ETH', recommended_trade_ratio='2')

        item = res['data']['items'][0]
        self.assertEqual(item['recommended_cta_notional_usd'], 500.0)
        self.assertEqual(item['recommended_trade_ratio'], 2.0)
        self.assertEqual(item['recommended_cta_init_value'], 250.0)

    def test_overlay_summary_falls_back_to_safe_default_when_size_is_unknown(self):
        overview = {'status': 0, 'data': {'strategy': 'admin_v3_unified'}}
        dashboard = {
            'status': 0,
            'data': {
                'items': [{
                    'strategy': 'admin_v3_unified',
                    'base_asset_qty': 0,
                    'base_asset_usd': 0,
                    'hedge_ratio': 0.5,
                    'rebalance_running': '已启动',
                }]
            }
        }

        with patch('functions.get_exchange', return_value=object()), \
                patch('functions.get_exchange_account_type',
                      return_value='unified'), \
                patch('functions.get_account_v2_overview',
                      return_value=overview), \
                patch('functions.get_account_v2_overview_section',
                      return_value=dashboard), \
                patch('functions.cta_unified_overlay_find_cta',
                      return_value=None):
            res = cta_unified_overlay_get_summary([], 'admin_v3_unified',
                                                  'ETH')

        item = res['data']['items'][0]
        self.assertEqual(item['recommended_cta_init_value'], 50.0)
        self.assertEqual(item['recommended_cta_base_qty'], 0.0)
        self.assertIn('无法计算推荐投入', item['recommended_cta_sizing_warning'])

    def test_overlay_deploy_creates_recommended_cta_without_starting_it(self):
        with patch('functions.cta_unified_overlay_find_cta',
                   return_value=None), \
                patch('functions.cta_usdt_create_strategy',
                      return_value={'status': 0, 'msg': 'created'}) as create:
            res = cta_unified_overlay_deploy({
                'strategy': 'admin_v3_unified',
            })

        self.assertEqual(res['status'], 0)
        self.assertEqual(res['data']['cta_key'],
                         'ETHUSDT_4h_adapt_bolling_anti_chase_[200,20]')
        payload = create.call_args.args[0]
        self.assertEqual(payload['strategy'], 'admin_v3_unified')
        self.assertEqual(payload['symbol'], 'ETHUSDT')
        self.assertEqual(payload['interval'], '4h')
        self.assertEqual(payload['cta'], 'adapt_bolling_anti_chase')
        self.assertEqual(payload['period'], '[200,20]')
        self.assertEqual(payload['trade_ratio'], '1')

    def test_overlay_deploy_uses_summary_recommendation_when_init_value_is_missing(self):
        summary = {
            'status': 0,
            'data': {
                'items': [{
                    'recommended_cta_init_value': 500.0,
                    'recommended_trade_ratio': 1.0,
                }]
            }
        }
        with patch('functions.cta_unified_overlay_get_summary',
                   return_value=summary), \
                patch('functions.cta_unified_overlay_find_cta',
                      return_value=None), \
                patch('functions.cta_usdt_create_strategy',
                      return_value={'status': 0, 'msg': 'created'}) as create:
            res = cta_unified_overlay_deploy({'strategy': 'admin_v3_unified'},
                                             binance_list=[object()])

        self.assertEqual(res['status'], 0)
        payload = create.call_args.args[0]
        self.assertEqual(payload['init_value'], '500.0')
        self.assertEqual(payload['trade_ratio'], '1.0')

    def test_overlay_deploy_rejects_cta_key_owned_by_other_strategy(self):
        existing = SimpleNamespace(strategy='other_strategy',
                                   cta_key='ETHUSDT_4h_adapt_bolling_anti_chase_[200,20]')

        with patch('functions.cta_unified_overlay_find_cta',
                   return_value=existing), \
                patch('functions.cta_usdt_create_strategy') as create:
            res = cta_unified_overlay_deploy({
                'strategy': 'admin_v3_unified',
            })

        self.assertEqual(res['status'], 500)
        self.assertIn('已属于其他账户', res['msg'])
        create.assert_not_called()

    def test_overlay_update_cta_only_updates_cta_risk_fields(self):
        existing = SimpleNamespace(id=7,
                                   strategy='admin_v3_unified',
                                   cta_key='ETHUSDT_4h_adapt_bolling_anti_chase_[200,20]')

        with patch('functions.cta_unified_overlay_find_cta',
                   return_value=existing), \
                patch('functions.cta_usdt_update_strategy',
                      return_value={'status': 0, 'msg': 'updated'}) as update, \
                patch('functions.rebalance_unified_margin_asset') as rebalance:
            res = cta_unified_overlay_update_cta({
                'strategy': 'admin_v3_unified',
                'trade_ratio': '1.2',
                'takeprofit_percentage': '0.4',
                'takeprofit_drawdown_percentage': '0.04',
                'stoploss_percentage': '0.15',
                'open_tpsl': 1,
            })

        self.assertEqual(res['status'], 0)
        payload = update.call_args.args[0]
        self.assertEqual(payload['id'], 7)
        self.assertEqual(payload['trade_ratio'], '1.2')
        self.assertEqual(payload['takeprofit_percentage'], '0.4')
        rebalance.assert_not_called()

    def test_overlay_update_rebalance_changes_ratio_without_trade(self):
        with patch('functions.cta_unified_margin_rebalance_update_ratio',
                   return_value={'status': 0, 'msg': 'ratio updated'}) as update, \
                patch('functions.rebalance_unified_margin_asset') as rebalance:
            res = cta_unified_overlay_update_rebalance({
                'strategy': 'admin_v3_unified',
                'asset': 'ETH',
                'hedge_ratio': '0.6',
            })

        self.assertEqual(res['status'], 0)
        update.assert_called_once_with('admin_v3_unified', 'ETH', '0.6')
        rebalance.assert_not_called()


if __name__ == '__main__':
    unittest.main()
