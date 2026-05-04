import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import ccxt

from functions import (get_account_balance, get_account_margin,
                       get_account_openorders, get_account_positions_list,
                       get_account_today_orders,
                       get_account_management_balance, get_all_account_balance,
                       get_all_account_positions_list, get_dapi_account_balance,
                       get_dapi_account_openorders,
                       get_dapi_account_today_orders,
                       calculate_account_profit_ratio,
                       get_account_v2_overview,
                       get_account_v2_overview_section)


class UnifiedDashboardExchange:
    def papiGetAccount(self):
        return {
            'accountStatus': 'NORMAL',
            'accountEquity': '1200',
            'totalAvailableBalance': '1100',
        }

    def papiGetUmPositionRisk(self, params=None):
        return [{
            'symbol': 'ETHUSDT',
            'positionAmt': '0.5',
            'entryPrice': '3000',
            'notional': '1500',
            'unRealizedProfit': '12',
        }]

    def papiGetBalance(self):
        return [{
            'asset': 'USDT',
            'totalWalletBalance': '1200',
            'umWalletBalance': '1000',
            'cmWalletBalance': '0',
            'cmUnrealizedPNL': '0',
            'umUnrealizedPNL': '12',
            'crossMarginBorrowed': '25',
            'crossMarginInterest': '0.1',
            'totalAvailableBalance': '1100',
        }, {
            'asset': 'ETH',
            'totalWalletBalance': '2.5',
            'umWalletBalance': '0',
            'cmWalletBalance': '2',
            'cmUnrealizedPNL': '0.5',
            'umUnrealizedPNL': '0',
            'totalAvailableBalance': '2',
        }]

    def papiGetUmUserTrades(self, params=None):
        return []

    def papiGetUmOpenOrders(self, params=None):
        return [{'symbol': 'ETHUSDT', 'orderId': '1', 'side': 'BUY'}]

    def papiGetCmPositionRisk(self, params=None):
        return []

    def papiGetCmUserTrades(self, params=None):
        return [{
            'symbol': params['symbol'],
            'realizedPnl': '0.1',
            'side': 'SELL',
            'price': '3000',
            'qty': '1',
            'baseQty': '0.01',
            'commission': '0.0001',
            'commissionAsset': 'ETH',
            'time': '1710000000000',
        }]

    def papiGetCmOpenOrders(self, params=None):
        return [{'symbol': 'ETHUSD_PERP', 'orderId': '2', 'side': 'BUY'}]

    def dapiPublicGetTicker24hr(self):
        return [{'symbol': 'ETHUSD_PERP', 'lastPrice': '3000'}]

    def dapiPublicGetExchangeInfo(self):
        return {
            'symbols': [{
                'contractStatus': 'TRADING',
                'contractType': 'PERPETUAL',
                'baseAsset': 'ETH',
                'quoteAsset': 'USD',
            }]
        }

    def public_get_ticker_price(self, params=None):
        return {'symbol': params['symbol'], 'price': '3000'}


class StandardDashboardExchange:
    def fapiPrivateV2_get_account(self):
        return {
            'totalWalletBalance': '700',
            'totalUnrealizedProfit': '10',
            'totalMarginBalance': '710',
            'availableBalance': '650',
            'assets': [{
                'asset': 'USDT',
                'walletBalance': '700',
                'unrealizedProfit': '10',
                'marginBalance': '710',
                'maxWithdrawAmount': '650',
            }],
            'positions': [{
                'symbol': 'ETHUSDT',
                'positionAmt': '0.2',
                'entryPrice': '3000',
                'notional': '600',
                'unRealizedProfit': '10',
                'positionInitialMargin': '60',
            }],
        }

    def dapiPrivate_get_account(self):
        return {
            'assets': [{
                'asset': 'ETH',
                'walletBalance': '0.1',
                'marginBalance': '0.1',
                'unrealizedProfit': '0',
            }],
            'positions': [],
        }

    def private_get_account(self):
        return {
            'balances': [{
                'asset': 'USDT',
                'free': '50',
                'locked': '0',
            }]
        }

    def sapi_post_asset_get_funding_asset(self):
        return []

    def dapiPublicGetTicker24hr(self, params=None):
        return [{'symbol': 'ETHUSD_PERP', 'lastPrice': '3000'}]

    def public_get_ticker_price(self, params=None):
        return {'symbol': params['symbol'], 'price': '3000'}


class UnifiedCrossMarginEthExchange(UnifiedDashboardExchange):
    def papiGetBalance(self):
        return [{
            'asset': 'ETH',
            'totalWalletBalance': '0.04',
            'crossMarginFree': '0.04',
            'cmWalletBalance': '0',
            'cmUnrealizedPNL': '0',
            'umWalletBalance': '0',
            'umUnrealizedPNL': '0',
        }]


class UnifiedCockpitExchange(UnifiedDashboardExchange):
    def papiGetUmPositionRisk(self, params=None):
        return [{
            'symbol': 'ETHUSDT',
            'positionAmt': '-0.3',
            'entryPrice': '2500',
            'notional': '-750',
            'unRealizedProfit': '8',
        }]

    def papiGetBalance(self):
        return [{
            'asset': 'ETH',
            'totalWalletBalance': '0.5',
            'crossMarginFree': '0.45',
            'crossMarginLocked': '0.05',
            'crossMarginBorrowed': '0',
            'crossMarginInterest': '0',
            'umWalletBalance': '0',
            'umUnrealizedPNL': '0',
            'cmWalletBalance': '0',
            'cmUnrealizedPNL': '0',
        }, {
            'asset': 'USDT',
            'totalWalletBalance': '-25.1',
            'crossMarginFree': '0',
            'crossMarginLocked': '0',
            'crossMarginBorrowed': '25',
            'crossMarginInterest': '0.1',
            'umWalletBalance': '0',
            'umUnrealizedPNL': '0',
            'cmWalletBalance': '0',
            'cmUnrealizedPNL': '0',
        }]


class DapiAuthFailureExchange:
    def dapiPrivateGetUserTrades(self, params=None):
        raise ccxt.AuthenticationError('Invalid API-key, IP, or permissions')


class UnifiedDashboardAccountTest(unittest.TestCase):
    def setUp(self):
        self.exchange = UnifiedDashboardExchange()

    def test_unified_dashboard_account_reads_do_not_require_fapi_methods(self):
        balance = get_account_balance(self.exchange, 'unified')
        positions = get_account_positions_list(self.exchange, 'unified')
        margin = get_account_margin(self.exchange, 'unified')
        today_orders = get_account_today_orders(self.exchange, 'unified')

        self.assertEqual(balance['status'], 0)
        self.assertEqual(balance['data']['items'][0]['wallet_balance'],
                         '1200.00')
        self.assertEqual(positions['data']['items'][0]['symbol'], 'ETHUSDT')
        self.assertEqual(margin['data']['items'][0]['asset'], 'USDT')
        self.assertEqual(today_orders['data']['items'], [])

    def test_all_account_views_accept_unified_accounts(self):
        binance_list = [{
            'strategy': 'admin_v3_unified',
            'account_type': 'unified',
            'exchange': self.exchange,
        }]

        balance = get_all_account_balance(binance_list)
        positions = get_all_account_positions_list(binance_list)

        self.assertEqual(balance['status'], 0)
        self.assertEqual(balance['data']['items'][0]['strategy_name'], '账户汇总')
        self.assertEqual(balance['data']['items'][1]['strategy_name'],
                         'admin_v3_unified')
        self.assertEqual(positions['status'], 0)
        self.assertEqual(positions['data']['items'][0]['symbol'], 'ETHUSDT')

    def test_unified_open_orders_use_papi_adapter(self):
        openorders = get_account_openorders(self.exchange, 'unified')

        self.assertEqual(openorders['status'], 0)
        self.assertEqual(openorders['data']['items'][0]['symbol'], 'ETHUSDT')

    def test_unified_dapi_balance_normalizes_cm_unrealized_pnl(self):
        balance = get_dapi_account_balance(self.exchange, 'unified')

        self.assertEqual(balance['status'], 0)
        self.assertEqual(balance['data']['items'][0]['asset'], 'ETH')
        self.assertEqual(balance['data']['items'][0]['unrealized_profit'], 0.5)

    def test_unified_dapi_balance_uses_total_wallet_for_coin_assets(self):
        balance = get_dapi_account_balance(UnifiedCrossMarginEthExchange(),
                                           'unified')

        self.assertEqual(balance['status'], 0)
        self.assertEqual(balance['data']['items'][0]['asset'], 'ETH')
        self.assertEqual(balance['data']['items'][0]['margin_balance'], 0.04)

    def test_unified_dapi_today_orders_use_papi_adapter(self):
        orders = get_dapi_account_today_orders(self.exchange, 'ETHUSD_PERP',
                                               'unified')

        self.assertEqual(orders['status'], 0)
        self.assertEqual(orders['data']['items'][0]['symbol'], 'ETHUSD_PERP')

    def test_unified_dapi_open_orders_use_papi_adapter(self):
        orders = get_dapi_account_openorders(self.exchange, 'unified')

        self.assertEqual(orders['status'], 0)
        self.assertEqual(orders['data']['items'][0]['symbol'], 'ETHUSD_PERP')

    def test_dapi_today_orders_returns_empty_data_when_exchange_auth_fails(self):
        orders = get_dapi_account_today_orders(DapiAuthFailureExchange(),
                                               'BTCUSD_PERP')

        self.assertEqual(orders['status'], 0)
        self.assertEqual(orders['data']['items'], [])
        self.assertIn('获取币本位当日成交失败', orders['msg'])

    def test_account_management_balance_accepts_unified_accounts(self):
        binance_list = [{
            'strategy': 'admin_v3_unified',
            'account_type': 'unified',
            'exchange': self.exchange,
        }]

        balance = get_account_management_balance(binance_list)

        self.assertEqual(balance['status'], 0)
        self.assertEqual(balance['data']['items'][0]['account_total'],
                         '1200.0')

    def test_account_profit_ratio_uses_principal_not_contract_pnl_only(self):
        self.assertEqual(calculate_account_profit_ratio(1100, 1000), 0.1)
        self.assertEqual(calculate_account_profit_ratio(995, 1000), -0.005)
        self.assertEqual(calculate_account_profit_ratio(1100, 0), 0)

    def test_unified_account_v2_overview_exposes_three_wallets(self):
        overview = get_account_v2_overview(self.exchange, 'admin_v3_unified',
                                           'unified')

        self.assertEqual(overview['status'], 0)
        data = overview['data']
        self.assertEqual(data['account_type'], 'unified')
        wallet_types = [wallet['wallet_type'] for wallet in data['wallets']]
        self.assertEqual(wallet_types, ['UM', 'CM', 'MARGIN_OR_SPOT'])
        self.assertEqual(data['wallets'][0]['wallet_label'], 'U本位')
        self.assertEqual(data['wallets'][1]['wallet_label'], '币本位')
        self.assertEqual(data['wallets'][2]['wallet_label'], '现货/杠杆')
        self.assertEqual(data['positions'][0]['market_type'], 'UM')

    def test_standard_account_v2_overview_keeps_legacy_wallet_shape(self):
        overview = get_account_v2_overview(StandardDashboardExchange(),
                                           'standard_strategy', 'standard')

        self.assertEqual(overview['status'], 0)
        data = overview['data']
        self.assertEqual(data['account_type'], 'standard')
        wallet_types = [wallet['wallet_type'] for wallet in data['wallets']]
        self.assertEqual(wallet_types,
                         ['UM', 'CM', 'MARGIN_OR_SPOT', 'FUNDING', 'SAVING'])
        self.assertEqual(data['wallets'][2]['wallet_label'], '现货')
        self.assertEqual(data['wallets'][0]['equity_usd'], 710.0)
        self.assertEqual(data['wallets'][1]['equity_usd'], 300.0)
        self.assertEqual(data['wallets'][2]['equity_usd'], 50.0)
        self.assertEqual(data['long_exposure_usd'], 600.0)

    def test_account_v2_overview_section_formats_crud_rows(self):
        overview = get_account_v2_overview(self.exchange, 'admin_v3_unified',
                                           'unified')
        wallets = get_account_v2_overview_section(overview, 'wallets')
        summary = get_account_v2_overview_section(overview, 'summary')

        self.assertEqual(wallets['data']['total'], 3)
        self.assertEqual(wallets['data']['items'][0]['wallet_type'], 'UM')
        self.assertEqual(summary['data']['items'][0]['strategy'],
                         'admin_v3_unified')

    def test_account_v2_overview_exposes_wallet_assets_and_margin_debts(self):
        overview = get_account_v2_overview(self.exchange, 'admin_v3_unified',
                                           'unified')

        assets = get_account_v2_overview_section(overview, 'wallet_assets')
        debts = get_account_v2_overview_section(overview, 'margin_debts')

        self.assertEqual(assets['status'], 0)
        eth = [item for item in assets['data']['items']
               if item['asset'] == 'ETH'][0]
        self.assertEqual(eth['margin_or_spot_amount'], 0)
        self.assertEqual(eth['cm_wallet_amount'], 2.0)
        self.assertFalse(eth['is_base_asset_available'])
        usdt_debt = [item for item in debts['data']['items']
                     if item['asset'] == 'USDT'][0]
        self.assertEqual(usdt_debt['borrowed_amount'], 25.0)
        self.assertEqual(usdt_debt['interest_amount'], 0.1)

    def test_account_v2_wallet_assets_mark_cross_margin_eth_as_base_asset(self):
        overview = get_account_v2_overview(UnifiedCrossMarginEthExchange(),
                                           'admin_v3_unified', 'unified')

        assets = get_account_v2_overview_section(overview, 'wallet_assets')
        eth = assets['data']['items'][0]

        self.assertEqual(eth['asset'], 'ETH')
        self.assertEqual(eth['margin_or_spot_amount'], 0.04)
        self.assertTrue(eth['is_base_asset_available'])

    def test_account_v2_dashboard_summarizes_base_debt_hedge_and_cta_overlay(self):
        exposure = {
            'asset': 'ETH',
            'hedge_symbol': 'ETHUSDT',
            'hedge_ratio': 0.5,
            'asset_base_qty': 0.5,
            'target_base_qty': 0.25,
            'current_um_position': -0.3,
            'net_base_exposure': 0.2,
            'position_gap': 0.05,
            'is_running': 1,
            'live_trade_enabled': 1,
            'last_rebalance_time': '2026-05-04 12:00:00',
            'last_msg': '半套执行成功',
        }

        with patch('functions.get_account_v2_strategy_exposures',
                   return_value=[exposure]):
            overview = get_account_v2_overview(UnifiedCockpitExchange(),
                                               'admin_v3_unified', 'unified')

        dashboard = get_account_v2_overview_section(overview, 'dashboard')
        row = dashboard['data']['items'][0]

        self.assertEqual(row['strategy'], 'admin_v3_unified')
        self.assertEqual(row['base_wallet_label'], '现货/杠杆底仓')
        self.assertEqual(row['base_asset'], 'ETH')
        self.assertEqual(row['base_asset_qty'], 0.5)
        self.assertEqual(row['base_asset_usd'], 1500.0)
        self.assertEqual(row['debt_asset'], 'USDT')
        self.assertEqual(row['debt_amount'], 25.1)
        self.assertEqual(row['hedge_market'], 'U本位')
        self.assertEqual(row['hedge_symbol'], 'ETHUSDT')
        self.assertEqual(row['hedge_ratio'], 0.5)
        self.assertEqual(row['target_hedge_qty'], 0.25)
        self.assertEqual(row['current_um_position'], -0.3)
        self.assertEqual(row['cta_overlay_position'], -0.05)
        self.assertEqual(row['net_base_exposure'], 0.2)
        self.assertEqual(row['rebalance_running'], '已启动')
        self.assertEqual(row['live_trade_enabled'], '已开启')
        self.assertEqual(row['position_gap'], 0.05)
        self.assertEqual(row['last_rebalance_time'], '2026-05-04 12:00:00')
        self.assertIn('巡检', row['next_action_hint'])
        self.assertIn('两套逻辑', row['risk_note'])

    def test_account_v2_dashboard_prompts_start_when_base_exists_without_rebalance(self):
        with patch('functions.get_account_v2_strategy_exposures',
                   return_value=[]):
            overview = get_account_v2_overview(UnifiedCockpitExchange(),
                                               'admin_v3_unified', 'unified')

        dashboard = get_account_v2_overview_section(overview, 'dashboard')
        row = dashboard['data']['items'][0]

        self.assertEqual(row['base_asset_qty'], 0.5)
        self.assertEqual(row['rebalance_running'], '未配置')
        self.assertEqual(row['live_trade_enabled'], '关闭')
        self.assertIn('可启动统一账户半套', row['next_action_hint'])


if __name__ == '__main__':
    unittest.main()
