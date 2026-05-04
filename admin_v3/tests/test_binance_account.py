import unittest
import os
import sys
from decimal import Decimal

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
            'totalWalletBalance': '2.2',
            'crossMarginFree': '0.4',
            'crossMarginLocked': '0.1',
            'umWalletBalance': '0.2',
            'umUnrealizedPNL': '0.1',
            'cmWalletBalance': '2',
            'cmUnrealizedPNL': '0.5',
        }]

    def papiGetAccount(self):
        self.calls.append(('papi_account', None))
        return {
            'accountStatus': 'NORMAL',
            'accountEquity': '1000',
            'totalAvailableBalance': '900',
        }

    def fapiPrivateV2_get_account(self):
        self.calls.append(('fapi_account', None))
        return {
            'totalMarginBalance': '100',
            'availableBalance': '90',
            'positions': [],
        }

    def papiGetUmPositionRisk(self, params=None):
        self.calls.append(('papi_um_position_risk', params))
        return [{
            'symbol': 'ETHUSDT',
            'positionAmt': '0.1',
        }]

    def fapiPrivateV2_get_positionrisk(self, params=None):
        self.calls.append(('fapi_position_risk', params))
        return [{
            'symbol': 'ETHUSDT',
            'positionAmt': '0.1',
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

    def fapiPrivate_post_order(self, params=None):
        self.calls.append(('fapi_order', params))
        return {'route': 'fapi', 'params': params}

    def private_post_order(self, params=None):
        self.calls.append(('spot_order', params))
        return {'route': 'spot', 'params': params}

    def dapiPrivate_get_openorders(self, params=None):
        self.calls.append(('dapi_open_orders', params))
        return [{'route': 'dapi_open_orders', 'params': params}]

    def fapiPrivate_get_openorders(self, params=None):
        self.calls.append(('fapi_open_orders', params))
        return [{'route': 'fapi_open_orders', 'params': params}]

    def private_get_openorders(self, params=None):
        self.calls.append(('spot_open_orders', params))
        return [{'route': 'spot_open_orders', 'params': params}]

    def dapiPrivate_delete_order(self, params=None):
        self.calls.append(('dapi_cancel', params))
        return {'route': 'dapi_cancel', 'params': params}

    def fapiPrivate_delete_order(self, params=None):
        self.calls.append(('fapi_cancel', params))
        return {'route': 'fapi_cancel', 'params': params}

    def private_delete_order(self, params=None):
        self.calls.append(('spot_cancel', params))
        return {'route': 'spot_cancel', 'params': params}

    def dapiPrivateGetUserTrades(self, params=None):
        self.calls.append(('dapi_trades', params))
        return [{'route': 'dapi_trades', 'params': params}]

    def fapiPrivateGetUserTrades(self, params=None):
        self.calls.append(('fapi_trades', params))
        return [{'route': 'fapi_trades', 'params': params}]

    def privateGetMyTrades(self, params=None):
        self.calls.append(('spot_trades', params))
        return [{'route': 'spot_trades', 'params': params}]

    def papiPostCmOrder(self, params=None):
        self.calls.append(('papi_cm_order', params))
        return {'route': 'papi', 'params': params}

    def papiPostUmOrder(self, params=None):
        self.calls.append(('papi_um_order', params))
        return {'route': 'papi_um', 'params': params}

    def papiPostMarginOrder(self, params=None):
        self.calls.append(('papi_margin_order', params))
        return {'route': 'papi_margin', 'params': params}

    def papiGetCmOpenOrders(self, params=None):
        self.calls.append(('papi_cm_open_orders', params))
        return [{'route': 'papi_cm_open_orders', 'params': params}]

    def papiGetUmOpenOrders(self, params=None):
        self.calls.append(('papi_um_open_orders', params))
        return [{'route': 'papi_um_open_orders', 'params': params}]

    def papiGetMarginOpenOrders(self, params=None):
        self.calls.append(('papi_margin_open_orders', params))
        return [{'route': 'papi_margin_open_orders', 'params': params}]

    def papiDeleteCmOrder(self, params=None):
        self.calls.append(('papi_cm_cancel', params))
        return {'route': 'papi_cm_cancel', 'params': params}

    def papiDeleteUmOrder(self, params=None):
        self.calls.append(('papi_um_cancel', params))
        return {'route': 'papi_um_cancel', 'params': params}

    def papiDeleteMarginOrder(self, params=None):
        self.calls.append(('papi_margin_cancel', params))
        return {'route': 'papi_margin_cancel', 'params': params}

    def papiGetCmUserTrades(self, params=None):
        self.calls.append(('papi_cm_trades', params))
        return [{'route': 'papi_cm_trades', 'params': params}]

    def papiGetUmUserTrades(self, params=None):
        self.calls.append(('papi_um_trades', params))
        return [{'route': 'papi_um_trades', 'params': params}]

    def papiGetMarginMyTrades(self, params=None):
        self.calls.append(('papi_margin_trades', params))
        return [{'route': 'papi_margin_trades', 'params': params}]


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
        self.assertEqual(account['assets'][0]['walletBalance'], '2.2')
        self.assertEqual(account['assets'][0]['marginBalance'], '2.2')
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

    def test_unified_account_reads_account_summary_balance_and_um_positions(self):
        exchange = FakeExchange()
        adapter = make_binance_account_adapter(exchange, ACCOUNT_TYPE_UNIFIED)

        summary = adapter.get_account_summary()
        balances = adapter.get_balance_assets()
        positions = adapter.get_um_position_risk()

        self.assertEqual(summary['accountStatus'], 'NORMAL')
        self.assertEqual(balances[0]['totalWalletBalance'], '2.2')
        self.assertEqual(balances[0]['marginBalance'], '2.5')
        self.assertEqual(positions[0]['symbol'], 'ETHUSDT')
        self.assertIn(('papi_account', None), exchange.calls)
        self.assertIn(('papi_balance', None), exchange.calls)
        self.assertIn(('papi_um_position_risk', {}), exchange.calls)

    def test_unified_account_reads_margin_asset_balance(self):
        exchange = FakeExchange()
        adapter = make_binance_account_adapter(exchange, ACCOUNT_TYPE_UNIFIED)

        balance = adapter.get_margin_asset_balance('ETH')

        self.assertEqual(balance['asset'], 'ETH')
        self.assertEqual(balance['total'], Decimal('0.5'))
        self.assertEqual(balance['free'], Decimal('0.4'))
        self.assertEqual(balance['locked'], Decimal('0.1'))
        self.assertIn(('papi_balance', None), exchange.calls)

    def test_standard_account_reads_legacy_summary_and_um_positions(self):
        exchange = FakeExchange()
        adapter = make_binance_account_adapter(exchange, ACCOUNT_TYPE_STANDARD)

        summary = adapter.get_account_summary()
        positions = adapter.get_um_position_risk()

        self.assertEqual(summary['accountStatus'], 'NORMAL')
        self.assertEqual(summary['accountEquity'], '100')
        self.assertEqual(summary['totalAvailableBalance'], '90')
        self.assertEqual(positions[0]['symbol'], 'ETHUSDT')
        self.assertIn(('fapi_account', None), exchange.calls)
        self.assertIn(('fapi_position_risk', {}), exchange.calls)

    def test_unified_account_routes_um_and_margin_orders(self):
        exchange = FakeExchange()
        adapter = make_binance_account_adapter(exchange, ACCOUNT_TYPE_UNIFIED)

        um_order = adapter.place_um_order({'symbol': 'ETHUSDT'})
        margin_order = adapter.place_margin_order({
            'symbol': 'ETHUSDT',
            'side': 'BUY',
        })

        self.assertEqual(um_order['route'], 'papi_um')
        self.assertEqual(margin_order['route'], 'papi_margin')
        self.assertIn(('papi_um_order', {'symbol': 'ETHUSDT'}), exchange.calls)
        self.assertIn(('papi_margin_order', {
            'symbol': 'ETHUSDT',
            'side': 'BUY',
        }), exchange.calls)

    def test_unified_account_routes_open_orders_cancel_and_trades_by_market(self):
        exchange = FakeExchange()
        adapter = make_binance_account_adapter(exchange, ACCOUNT_TYPE_UNIFIED)

        cm_orders = adapter.get_open_orders('cm', {'symbol': 'ETHUSD_PERP'})
        um_cancel = adapter.cancel_order('um', {
            'symbol': 'ETHUSDT',
            'orderId': 1,
        })
        margin_trades = adapter.get_user_trades('margin',
                                                {'symbol': 'ETHUSDT'})

        self.assertEqual(cm_orders[0]['route'], 'papi_cm_open_orders')
        self.assertEqual(um_cancel['route'], 'papi_um_cancel')
        self.assertEqual(margin_trades[0]['route'], 'papi_margin_trades')

    def test_standard_account_routes_um_cm_and_margin_to_legacy_methods(self):
        exchange = FakeExchange()
        adapter = make_binance_account_adapter(exchange, ACCOUNT_TYPE_STANDARD)

        um_order = adapter.place_um_order({'symbol': 'ETHUSDT'})
        margin_order = adapter.place_margin_order({'symbol': 'ETHUSDT'})
        cm_orders = adapter.get_open_orders('cm', {'symbol': 'ETHUSD_PERP'})
        um_cancel = adapter.cancel_order('um', {'symbol': 'ETHUSDT'})
        margin_trades = adapter.get_user_trades('margin',
                                                {'symbol': 'ETHUSDT'})

        self.assertEqual(um_order['route'], 'fapi')
        self.assertEqual(margin_order['route'], 'spot')
        self.assertEqual(cm_orders[0]['route'], 'dapi_open_orders')
        self.assertEqual(um_cancel['route'], 'fapi_cancel')
        self.assertEqual(margin_trades[0]['route'], 'spot_trades')


if __name__ == '__main__':
    unittest.main()
