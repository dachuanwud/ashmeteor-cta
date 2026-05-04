import os
import sys
import unittest
from decimal import Decimal
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import functions
from functions import cta_usd_stop_after, cta_usd_sync_position_to_signal


class CmPositionExchange:
    def __init__(self, position_amt='0'):
        self.position_amt = position_amt
        self.orders = []

    def papiGetCmPositionRisk(self, params=None):
        return [{
            'symbol': 'ETHUSD_PERP',
            'positionAmt': self.position_amt,
        }]

    def papiPostCmOrder(self, params=None):
        self.orders.append(params)
        return {'orderId': 'cm-order-1'}


class CtaUsdPositionSyncTest(unittest.TestCase):
    def _trade_info(self):
        return {
            'strategy': 'admin_v3_unified',
            'symbol': 'ETHUSD_PERP',
            'signal': 1,
            'init_value': Decimal('50'),
            'net_value': Decimal('50'),
            'open_price': Decimal('2306.04'),
            'close_price': None,
            'trade_ratio': Decimal('2'),
            'position_amount': Decimal('50'),
            'takeprofit_percentage': Decimal('0.50'),
            'takeprofit_drawdown_percentage': Decimal('0.05'),
            'stoploss_percentage': Decimal('0.05'),
            'open_tpsl': 1,
            'interval': '4h',
        }

    def test_sync_position_uses_actual_exchange_position_not_stale_db_position(self):
        exchange = CmPositionExchange(position_amt='0')

        with mock.patch.object(functions, 'cta_usd_get_trade_info',
                               return_value=self._trade_info()), \
                mock.patch.object(functions, 'cta_usd_get_symbol_db_position',
                                  return_value=Decimal('0')), \
                mock.patch.object(functions, 'get_dapi_exchange_info',
                                  return_value={'ETHUSD_PERP': 2}), \
                mock.patch.object(functions, 'fetch_binance_dapi_ticker_data',
                                  return_value=2300.0), \
                mock.patch.object(functions, 'cta_usd_update_trade_info') as update_info, \
                mock.patch.object(functions.time, 'sleep'), \
                mock.patch.object(functions, 'send_wechat'):
            res = cta_usd_sync_position_to_signal(
                exchange,
                'ETHUSD_PERP_4h_adapt_bolling_anti_chase_[200,20]',
                account_type='unified',
            )

        self.assertEqual(res['status'], 0)
        self.assertEqual(res['data']['target_position'], '100')
        self.assertEqual(res['data']['actual_position'], '0')
        self.assertEqual(res['data']['order_amount'], '100')
        self.assertEqual(exchange.orders[0]['side'], 'BUY')
        self.assertEqual(sum(order['quantity'] for order in exchange.orders),
                         100)
        update_info.assert_called_once()
        self.assertEqual(update_info.call_args.args[1]['position_amount'],
                         Decimal('100'))

    def test_stop_does_not_open_reverse_order_when_exchange_position_is_zero(self):
        exchange = CmPositionExchange(position_amt='0')

        with mock.patch.object(functions, 'cta_usd_get_symbol_db_position',
                               return_value=Decimal('0')), \
                mock.patch.object(functions, 'get_dapi_exchange_info',
                                  return_value={'ETHUSD_PERP': 2}), \
                mock.patch.object(functions, 'fetch_binance_dapi_ticker_data',
                                  return_value=2300.0), \
                mock.patch.object(functions, 'cta_usd_update_trade_info') as update_info, \
                mock.patch.object(functions.time, 'sleep'), \
                mock.patch.object(functions, 'send_wechat'):
            cta_usd_stop_after(
                exchange,
                self._trade_info(),
                'ETHUSD_PERP_4h_adapt_bolling_anti_chase_[200,20]',
                account_type='unified',
            )

        self.assertEqual(exchange.orders, [])
        update_info.assert_called_once()
        self.assertEqual(update_info.call_args.args[1]['position_amount'], 0.0)
        self.assertEqual(update_info.call_args.args[1]['is_running'], 0)


if __name__ == '__main__':
    unittest.main()
