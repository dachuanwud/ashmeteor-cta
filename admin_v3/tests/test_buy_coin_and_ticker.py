import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from functions import (dapi_buy_coin_list_and_transfer,
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
