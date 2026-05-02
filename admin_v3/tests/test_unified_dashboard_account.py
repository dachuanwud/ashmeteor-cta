import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from functions import (get_account_balance, get_account_margin,
                       get_account_positions_list, get_account_today_orders)


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
            'cmWalletBalance': '0',
            'cmUnrealizedPNL': '0',
            'umUnrealizedPNL': '12',
            'totalAvailableBalance': '1100',
        }]

    def papiGetUmUserTrades(self, params=None):
        return []


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


if __name__ == '__main__':
    unittest.main()
