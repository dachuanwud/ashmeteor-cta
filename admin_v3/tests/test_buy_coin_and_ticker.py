import os
import sys
import unittest
from decimal import Decimal
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from functions import (dapi_buy_coin_list_and_transfer,
                       dapi_buy_coin_and_transfer,
                       cta_unified_margin_rebalance_run_items,
                       execute_unified_base_asset_buy,
                       fetch_binance_dapi_ticker_data,
                       fetch_binance_ticker_data,
                       preview_unified_base_asset_buy,
                       rebalance_unified_margin_asset)


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
    def __init__(self,
                 account_status='NORMAL',
                 available='100',
                 max_borrow='1000',
                 eth_cross_after_buy='0.004'):
        self.orders = []
        self.account_status = account_status
        self.available = available
        self.max_borrow = max_borrow
        self.eth_cross_after_buy = eth_cross_after_buy

    def public_get_ticker_price(self, params=None):
        return {'symbol': params['symbol'], 'price': '2500'}

    def papiGetAccount(self):
        return {
            'accountStatus': self.account_status,
            'accountEquity': '1200',
            'totalAvailableBalance': self.available,
        }

    def papiGetMarginMaxBorrowable(self, params=None):
        return {
            'asset': params['asset'],
            'amount': self.max_borrow,
            'borrowLimit': self.max_borrow,
        }

    def papiGetBalance(self):
        if not self.orders:
            return []
        return [{
            'asset': 'ETH',
            'totalWalletBalance': self.eth_cross_after_buy,
            'crossMarginFree': self.eth_cross_after_buy,
            'crossMarginLocked': '0',
            'crossMarginBorrowed': '0',
            'crossMarginInterest': '0',
            'umWalletBalance': '0',
            'umUnrealizedPNL': '0',
            'cmWalletBalance': '0',
            'cmUnrealizedPNL': '0',
        }, {
            'asset': 'USDT',
            'totalWalletBalance': '-20',
            'crossMarginFree': '0',
            'crossMarginLocked': '0',
            'crossMarginBorrowed': '20',
            'crossMarginInterest': '0.01',
            'umWalletBalance': '0',
            'umUnrealizedPNL': '0',
            'cmWalletBalance': '0',
            'cmUnrealizedPNL': '0',
        }]

    def papiPostMarginOrder(self, params=None):
        self.orders.append(params)
        return {
            'orderId': 'base-buy-1',
            'executedQty': '0.004',
            'marginBuyBorrowAmount': '20',
            'marginBuyBorrowAsset': 'USDT',
            'fills': [{
                'commission': '0.000001',
            }],
        }


class UnifiedMarginRebalanceExchange(UnifiedBuyCoinExchange):
    def __init__(self, asset_qty='2', position_amt='-0.4'):
        super().__init__()
        self.asset_qty = asset_qty
        self.position_amt = position_amt

    def papiGetBalance(self):
        return [{
            'asset': 'ETH',
            'totalWalletBalance': self.asset_qty,
            'crossMarginFree': self.asset_qty,
        }]

    def papiGetUmPositionRisk(self, params=None):
        return [{
            'symbol': 'ETHUSDT',
            'positionAmt': self.position_amt,
        }]

    def fapiPublic_get_exchangeinfo(self):
        return {
            'symbols': [{
                'symbol': 'ETHUSDT',
                'status': 'TRADING',
                'filters': [{
                    'filterType': 'PRICE_FILTER',
                    'tickSize': '0.01',
                }, {
                    'filterType': 'MARKET_LOT_SIZE',
                    'minQty': '0.001',
                    'stepSize': '0.001',
                }, {
                    'filterType': 'MIN_NOTIONAL',
                    'notional': '5',
                }],
            }]
        }

    def fapiPublicGetTicker24hr(self, params=None):
        return {'symbol': 'ETHUSDT', 'lastPrice': '2500'}

    def papiPostUmOrder(self, params=None):
        self.orders.append(params)
        return {'orderId': 'hedge-1'}


class UnifiedMarginNoHedgeSymbolExchange(UnifiedMarginRebalanceExchange):
    def fapiPublic_get_exchangeinfo(self):
        return {'symbols': []}


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

    def test_unified_margin_buy_preview_uses_margin_buy_and_um_rebalance_plan(self):
        exchange = UnifiedBuyCoinExchange(available='50', max_borrow='200')

        res = preview_unified_base_asset_buy(exchange,
                                             strategy='acct',
                                             asset='ETH',
                                             quote_usd='100',
                                             buy_mode='margin',
                                             hedge_ratio='0.5')

        self.assertEqual(res['status'], 0)
        self.assertEqual(exchange.orders, [])
        self.assertEqual(res['data']['margin_order']['symbol'], 'ETHUSDT')
        self.assertEqual(res['data']['margin_order']['sideEffectType'],
                         'MARGIN_BUY')
        self.assertEqual(res['data']['rebalance_order']['symbol'], 'ETHUSDT')
        self.assertEqual(res['data']['rebalance_order']['side'], 'SELL')
        self.assertEqual(res['data']['buy_mode'], 'margin')

    def test_unified_margin_buy_preview_rejects_insufficient_borrow_capacity(self):
        exchange = UnifiedBuyCoinExchange(available='25', max_borrow='50')

        res = preview_unified_base_asset_buy(exchange,
                                             strategy='acct',
                                             asset='ETH',
                                             quote_usd='100',
                                             buy_mode='margin',
                                             hedge_ratio='0.5')

        self.assertEqual(res['status'], 500)
        self.assertIn('可借额度不足', res['msg'])
        self.assertEqual(exchange.orders, [])

    def test_unified_margin_buy_execute_requires_live_trade_enabled(self):
        exchange = UnifiedBuyCoinExchange()

        res = execute_unified_base_asset_buy(exchange,
                                             strategy='acct',
                                             asset='ETH',
                                             quote_usd='100',
                                             buy_mode='margin',
                                             hedge_ratio='0.5',
                                             live_trade_enabled=0)

        self.assertEqual(res['status'], 500)
        self.assertIn('未开启真实下单', res['msg'])
        self.assertEqual(exchange.orders, [])

    def test_unified_margin_buy_execute_records_borrow_and_rebalances_um(self):
        exchange = UnifiedMarginRebalanceExchange(asset_qty='0.004',
                                                  position_amt='0')
        exchange.max_borrow = '200'
        exchange.available = '50'

        res = execute_unified_base_asset_buy(exchange,
                                             strategy='acct',
                                             asset='ETH',
                                             quote_usd='100',
                                             buy_mode='margin',
                                             hedge_ratio='0.5',
                                             live_trade_enabled=1)

        self.assertEqual(res['status'], 0)
        self.assertEqual(exchange.orders[0]['sideEffectType'], 'MARGIN_BUY')
        self.assertEqual(exchange.orders[0]['quoteOrderQty'], '100.00')
        self.assertEqual(res['data']['margin_order_result']['borrow_asset'],
                         'USDT')
        self.assertEqual(res['data']['margin_order_result']['borrow_amount'],
                         '20')
        self.assertEqual(exchange.orders[1]['symbol'], 'ETHUSDT')
        self.assertEqual(exchange.orders[1]['side'], 'SELL')
        self.assertEqual(str(exchange.orders[1]['quantity']), '0.002')

    def test_unified_margin_buy_execute_refuses_rebalance_when_eth_not_cross_margin(self):
        exchange = UnifiedMarginRebalanceExchange(asset_qty='0',
                                                  position_amt='0')
        exchange.eth_cross_after_buy = '0'

        res = execute_unified_base_asset_buy(exchange,
                                             strategy='acct',
                                             asset='ETH',
                                             quote_usd='100',
                                             buy_mode='margin',
                                             hedge_ratio='0.5',
                                             live_trade_enabled=1)

        self.assertEqual(res['status'], 500)
        self.assertIn('没有落到现货/杠杆侧', res['msg'])
        self.assertEqual(len(exchange.orders), 1)

    def test_unified_buy_coin_can_create_record_and_trigger_um_rebalance(self):
        exchange = UnifiedBuyCoinExchange()

        with patch('functions.create_or_update_unified_margin_rebalance',
                   return_value={'id': 1}) as create_record, \
                patch('functions.rebalance_unified_margin_asset',
                      return_value={'status': 0, 'msg': '半套执行成功'}) as rebalance:
            res = dapi_buy_coin_and_transfer(exchange, 'ETH', 'normal', '10',
                                             '', 'unified',
                                             strategy='acct',
                                             hedge_ratio='0.5',
                                             live_trade_enabled=1)

        self.assertEqual(res['status'], 0)
        create_record.assert_called_once()
        rebalance.assert_called_once_with(exchange, 'acct', 'ETH',
                                          Decimal('0.5'), True)
        self.assertEqual(res['rebalance']['msg'], '半套执行成功')

    def test_unified_margin_rebalance_sells_um_when_short_is_below_target(self):
        exchange = UnifiedMarginRebalanceExchange(asset_qty='2',
                                                  position_amt='-0.4')

        res = rebalance_unified_margin_asset(exchange, 'acct', 'ETH',
                                             Decimal('0.5'), True)

        self.assertEqual(res['status'], 0)
        self.assertEqual(exchange.orders[0]['symbol'], 'ETHUSDT')
        self.assertEqual(exchange.orders[0]['side'], 'SELL')
        self.assertEqual(exchange.orders[0]['type'], 'MARKET')
        self.assertEqual(str(exchange.orders[0]['quantity']), '0.600')

    def test_unified_margin_rebalance_uses_only_margin_or_spot_eth_as_base(self):
        exchange = UnifiedMarginRebalanceExchange(asset_qty='2',
                                                  position_amt='0')

        def balance_with_separate_wallets():
            return [{
                'asset': 'ETH',
                'totalWalletBalance': '2',
                'crossMarginFree': '0.5',
                'crossMarginLocked': '0',
                'umWalletBalance': '0.3',
                'cmWalletBalance': '1.2',
            }]

        exchange.papiGetBalance = balance_with_separate_wallets

        res = rebalance_unified_margin_asset(exchange, 'acct', 'ETH',
                                             Decimal('0.5'), True)

        self.assertEqual(res['status'], 0)
        self.assertEqual(str(exchange.orders[0]['quantity']), '0.250')

    def test_unified_margin_rebalance_buys_reduce_only_when_short_is_above_target(self):
        exchange = UnifiedMarginRebalanceExchange(asset_qty='1',
                                                  position_amt='-0.8')

        res = rebalance_unified_margin_asset(exchange, 'acct', 'ETH',
                                             Decimal('0.5'), True)

        self.assertEqual(res['status'], 0)
        self.assertEqual(exchange.orders[0]['side'], 'BUY')
        self.assertTrue(exchange.orders[0]['reduceOnly'])
        self.assertEqual(str(exchange.orders[0]['quantity']), '0.300')

    def test_unified_margin_rebalance_skips_below_min_quantity(self):
        exchange = UnifiedMarginRebalanceExchange(asset_qty='0.001',
                                                  position_amt='0')

        res = rebalance_unified_margin_asset(exchange, 'acct', 'ETH',
                                             Decimal('0.5'), True)

        self.assertEqual(res['status'], 0)
        self.assertIn('小于最小下单量', res['msg'])
        self.assertEqual(exchange.orders, [])

    def test_unified_margin_rebalance_rejects_missing_um_symbol(self):
        exchange = UnifiedMarginNoHedgeSymbolExchange()

        res = rebalance_unified_margin_asset(exchange, 'acct', 'ETH',
                                             Decimal('0.5'), True)

        self.assertEqual(res['status'], 500)
        self.assertIn('ETHUSDT不支持U本位半套', res['msg'])
        self.assertEqual(exchange.orders, [])

    def test_unified_margin_rebalance_scheduler_dry_run_updates_preview_without_order(self):
        exchange = UnifiedMarginRebalanceExchange(asset_qty='2',
                                                  position_amt='0')
        item = {
            'strategy': 'acct',
            'asset': 'ETH',
            'hedge_ratio': Decimal('0.5'),
            'is_running': 1,
            'live_trade_enabled': 0,
            'hedge_market': 'um',
        }

        res = cta_unified_margin_rebalance_run_items([{
            'strategy': 'acct',
            'exchange': exchange,
        }], [item])

        self.assertEqual(res['status'], 0)
        self.assertEqual(res['data']['total'], 1)
        self.assertIn('预览', res['data']['items'][0]['msg'])
        self.assertEqual(exchange.orders, [])

    def test_unified_margin_rebalance_scheduler_live_adjusts_um_short(self):
        exchange = UnifiedMarginRebalanceExchange(asset_qty='2',
                                                  position_amt='0')
        item = {
            'strategy': 'acct',
            'asset': 'ETH',
            'hedge_ratio': Decimal('0.5'),
            'is_running': 1,
            'live_trade_enabled': 1,
            'hedge_market': 'um',
        }

        res = cta_unified_margin_rebalance_run_items([{
            'strategy': 'acct',
            'exchange': exchange,
        }], [item])

        self.assertEqual(res['status'], 0)
        self.assertEqual(exchange.orders[0]['symbol'], 'ETHUSDT')
        self.assertEqual(exchange.orders[0]['side'], 'SELL')
        self.assertEqual(str(exchange.orders[0]['quantity']), '1.000')

    def test_unified_margin_rebalance_scheduler_skips_paused_items(self):
        exchange = UnifiedMarginRebalanceExchange(asset_qty='2',
                                                  position_amt='0')
        item = {
            'strategy': 'acct',
            'asset': 'ETH',
            'hedge_ratio': Decimal('0.5'),
            'is_running': 0,
            'live_trade_enabled': 1,
            'hedge_market': 'um',
        }

        res = cta_unified_margin_rebalance_run_items([{
            'strategy': 'acct',
            'exchange': exchange,
        }], [item])

        self.assertEqual(res['status'], 0)
        self.assertEqual(res['data']['total'], 0)
        self.assertEqual(exchange.orders, [])

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
