import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from binance_account import (ACCOUNT_TYPE_STANDARD, ACCOUNT_TYPE_UNIFIED,
                             make_binance_account_adapter,
                             normalize_account_type)


class FakeExchange:
    def __init__(self):
        self.calls = []

    def dapiPrivate_get_account(self):
        self.calls.append(('dapi_account', None))
        return {
            'assets': [{
                'asset': 'ETH',
                'walletBalance': '2',
                'marginBalance': '2.5',
            }],
            'positions': [{
                'symbol': 'ETHUSD_PERP',
                'positionAmt': '-10',
            }],
        }

    def dapiPrivate_get_positionrisk(self, params=None):
        self.calls.append(('dapi_position_risk', params))
        return [{
            'symbol': 'ETHUSD_PERP',
            'positionAmt': '-10',
        }]

    def dapiPrivate_get_adlquantile(self, params=None):
        self.calls.append(('dapi_adl_quantile', params))
        return [{'symbol': 'ETHUSD_PERP'}]

    def papiGetBalance(self):
        self.calls.append(('papi_balance', None))
        return [{
            'asset': 'ETH',
            'cmWalletBalance': '2',
            'cmUnrealizedPNL': '0.5',
        }]

    def papiGetCmPositionRisk(self, params=None):
        self.calls.append(('papi_position_risk', params))
        return [{
            'symbol': 'ETHUSD_PERP',
            'positionAmt': '-10',
        }]

    def papiGetCmAdlQuantile(self, params=None):
        self.calls.append(('papi_cm_adl_quantile', params))
        return [{'symbol': 'ETHUSD_PERP'}]

    def dapiPrivate_post_order(self, params=None):
        self.calls.append(('dapi_order', params))
        return {'route': 'dapi', 'params': params}

    def papiPostCmOrder(self, params=None):
        self.calls.append(('papi_cm_order', params))
        return {'route': 'papi', 'params': params}


class BinanceAccountAdapterTest(unittest.TestCase):
    def test_unknown_account_type_defaults_to_standard(self):
        self.assertEqual(normalize_account_type('old-row'), ACCOUNT_TYPE_STANDARD)

    def test_standard_account_uses_dapi_account_and_order(self):
        exchange = FakeExchange()
        adapter = make_binance_account_adapter(exchange, ACCOUNT_TYPE_STANDARD)

        account = adapter.get_cm_account()
        order = adapter.place_cm_order({'symbol': 'ETHUSD_PERP'})

        self.assertEqual(account['assets'][0]['marginBalance'], '2.5')
        self.assertEqual(order['route'], 'dapi')
        self.assertIn(('dapi_account', None), exchange.calls)

    def test_standard_account_uses_dapi_position_risk_and_adl(self):
        exchange = FakeExchange()
        adapter = make_binance_account_adapter(exchange, ACCOUNT_TYPE_STANDARD)

        positions = adapter.get_cm_position_risk()
        adl = adapter.get_cm_adl_quantile()

        self.assertEqual(positions[0]['symbol'], 'ETHUSD_PERP')
        self.assertEqual(adl[0]['symbol'], 'ETHUSD_PERP')
        self.assertIn(('dapi_position_risk', {}), exchange.calls)
        self.assertIn(('dapi_adl_quantile', {}), exchange.calls)

    def test_unified_account_normalizes_papi_balance_and_order(self):
        exchange = FakeExchange()
        adapter = make_binance_account_adapter(exchange, ACCOUNT_TYPE_UNIFIED)

        account = adapter.get_cm_account()
        order = adapter.place_cm_order({'symbol': 'ETHUSD_PERP'})

        self.assertEqual(account['assets'][0]['asset'], 'ETH')
        self.assertEqual(account['assets'][0]['walletBalance'], '2')
        self.assertEqual(account['assets'][0]['marginBalance'], '2.5')
        self.assertEqual(account['positions'][0]['symbol'], 'ETHUSD_PERP')
        self.assertEqual(order['route'], 'papi')
        self.assertIn(('papi_balance', None), exchange.calls)
        self.assertIn(('papi_position_risk', None), exchange.calls)

    def test_unified_account_uses_papi_cm_position_risk_and_adl(self):
        exchange = FakeExchange()
        adapter = make_binance_account_adapter(exchange, ACCOUNT_TYPE_UNIFIED)

        positions = adapter.get_cm_position_risk()
        adl = adapter.get_cm_adl_quantile()

        self.assertEqual(positions[0]['symbol'], 'ETHUSD_PERP')
        self.assertEqual(adl[0]['symbol'], 'ETHUSD_PERP')
        self.assertIn(('papi_position_risk', {}), exchange.calls)
        self.assertIn(('papi_cm_adl_quantile', {}), exchange.calls)


if __name__ == '__main__':
    unittest.main()
