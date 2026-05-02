import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from functions import (get_account_balance, get_account_margin,
                       get_account_openorders, get_account_positions_list,
                       get_account_today_orders,
                       get_account_management_balance, get_all_account_balance,
                       get_all_account_positions_list, get_dapi_account_balance)


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


if __name__ == '__main__':
    unittest.main()
