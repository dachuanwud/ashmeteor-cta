import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from functions import (dapi_buy_coin_list_and_transfer,
                       dapi_buy_coin_and_transfer,
                       fetch_binance_dapi_ticker_data,
                       fetch_binance_ticker_data)


class TickerExchange:
    def fapiPublicGetTicker24hr(self):
        return [{
            'symbol': 'WUSDT',
            'lastPrice': '1.23',
            'quoteVolume': '1000',
        }, {
            'symbol': 'ETHUSDT',
            'lastPrice': '3000.5',
            'quoteVolume': '2000',
        }]

    def dapiPublicGetTicker24hr(self):
        return [{
            'symbol': 'XLMUSD_PERP',
            'lastPrice': '0.11',
            'volume': '1000',
        }, {
            'symbol': 'ETHUSD_PERP',
            'lastPrice': '3000.5',
            'volume': '2000',
        }]


class UnifiedBuyCoinExchange:
    def __init__(self):
        self.orders = []

    def public_get_ticker_price(self, params=None):
        return {'symbol': params['symbol'], 'price': '2500'}

    def papiGetAccount(self):
        return {
            'accountStatus': 'NORMAL',
            'accountEquity': '1200',
            'totalAvailableBalance': '100',
        }

    def papiPostMarginOrder(self, params=None):
        self.orders.append(params)
        return {
            'executedQty': '0.004',
            'fills': [{
                'commission': '0.000001',
            }],
        }


class BuyCoinAndTickerTest(unittest.TestCase):
    def test_buy_coin_list_does_not_import_removed_urllib_unquote(self):
        with patch('functions.dapi_buy_coin_and_transfer',
                   return_value={'status': 0}):
            res = dapi_buy_coin_list_and_transfer(object(), 'ETH', 'normal',
                                                  '10', '')

        self.assertEqual(res['status'], 0)
        self.assertEqual(res['msg'], ['ETH购买并转入币本位成功'])

    def test_buy_coin_list_requires_asset_and_amount(self):
        res = dapi_buy_coin_list_and_transfer(object(), '', 'normal', '', '')

        self.assertEqual(res['status'], 500)
        self.assertIn('买币列表', res['msg'])
        self.assertIn('买币参数', res['msg'])

    def test_buy_coin_list_propagates_child_failure_message(self):
        with patch('functions.dapi_buy_coin_and_transfer',
                   return_value={'status': 500, 'msg': 'params error'}):
            res = dapi_buy_coin_list_and_transfer(object(), 'ETH', 'normal',
                                                  '10', '')

        self.assertEqual(res['status'], 500)
        self.assertEqual(res['msg'], ['ETH购买并转入币本位失败: params error'])

    def test_unified_buy_coin_uses_papi_margin_order_without_legacy_transfer(self):
        exchange = UnifiedBuyCoinExchange()

        res = dapi_buy_coin_and_transfer(exchange, 'ETH', 'normal', '10', '',
                                         'unified')

        self.assertEqual(res['status'], 0)
        self.assertIn('统一账户买入ETH成功', res['msg'])
        self.assertEqual(exchange.orders[0]['symbol'], 'ETHUSDT')
        self.assertEqual(exchange.orders[0]['side'], 'BUY')
        self.assertEqual(exchange.orders[0]['type'], 'MARKET')
        self.assertEqual(str(exchange.orders[0]['quoteOrderQty']), '10.00')

    def test_fetch_um_tickers_only_converts_last_price_to_numeric(self):
        prices = fetch_binance_ticker_data(TickerExchange())

        self.assertEqual(prices['WUSDT'], 1.23)
        self.assertEqual(prices['ETHUSDT'], 3000.5)

    def test_fetch_cm_tickers_only_converts_last_price_to_numeric(self):
        prices = fetch_binance_dapi_ticker_data(TickerExchange())

        self.assertEqual(prices['XLMUSD_PERP'], 0.11)
        self.assertEqual(prices['ETHUSD_PERP'], 3000.5)


if __name__ == '__main__':
    unittest.main()
