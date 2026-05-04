import os
import sys
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import patch

import pandas as pd
from sqlalchemy import create_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schedule_task import (_append_ledger_row, _concat_ledger_frame,
                           cta_usdt_takeprofit_and_stoploss,
                           _get_um_margin_balance, _read_ledger_table,
                           _write_ledger_rows)


class _NoopContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeApp:
    def app_context(self):
        return _NoopContext()


class UnifiedAccountSummaryExchange:
    def papiGetAccount(self):
        return {
            'accountEquity': '123.45',
            'totalAvailableBalance': '100',
        }


class ScheduleTaskCompatTest(unittest.TestCase):
    def test_append_ledger_row_is_compatible_with_pandas_2(self):
        df = pd.DataFrame([{
            'net_value': 1,
        }])

        next_df = _append_ledger_row(df, {
            'net_value': 2,
        })

        self.assertEqual(list(next_df['net_value']), [1, 2])

    def test_concat_ledger_frame_is_compatible_with_pandas_2(self):
        df = pd.DataFrame([{
            'symbol': 'ETH',
            'max_profit_ratio': 0.1,
        }])
        addition = pd.DataFrame([{
            'symbol': 'BTC',
            'max_profit_ratio': 0.2,
        }])

        next_df = _concat_ledger_frame(df, addition)

        self.assertEqual(list(next_df['symbol']), ['ETH', 'BTC'])

    def test_read_ledger_table_uses_sqlalchemy_connection(self):
        engine = create_engine('sqlite:///:memory:')
        raw_connection = engine.raw_connection()
        try:
            pd.DataFrame([{
                'net_value': 7,
            }]).to_sql('account_value', con=raw_connection, index=True)
        finally:
            raw_connection.close()

        df = _read_ledger_table(engine, 'account_value')

        self.assertEqual(int(df.iloc[0]['net_value']), 7)

    def test_write_ledger_rows_uses_sqlalchemy_insert_not_pandas_to_sql(self):
        engine = create_engine('sqlite:///:memory:')
        df = pd.DataFrame([{
            'candle_begin_time': pd.Timestamp('2026-05-03 11:00:00'),
            'net_value': 9.5,
        }])

        with patch.object(pd.DataFrame, 'to_sql',
                          side_effect=AssertionError('do not use pandas to_sql')):
            inserted = _write_ledger_rows(engine, 'account_value', df)
        stored = _read_ledger_table(engine, 'account_value')

        self.assertEqual(inserted, 1)
        self.assertEqual(float(stored.iloc[0]['net_value']), 9.5)

    def test_unified_um_margin_balance_uses_account_adapter(self):
        balance = _get_um_margin_balance(UnifiedAccountSummaryExchange(),
                                         'unified')

        self.assertEqual(balance, 123.45)

    def test_usdt_tpsl_skips_open_position_without_open_price(self):
        trade_info = {
            'strategy': 'admin_v3_unified',
            'symbol': 'ETHUSDT',
            'signal': 1,
            'position_amount': Decimal('0.2'),
            'open_price': None,
            'takeprofit_percentage': Decimal('0.50'),
            'takeprofit_drawdown_percentage': Decimal('0.05'),
            'stoploss_percentage': Decimal('0.05'),
            'open_tpsl': 1,
            'interval': '4h',
        }

        with tempfile.TemporaryDirectory() as tmpdir, \
                patch('schedule_task.scheduler.app', _FakeApp()), \
                patch('schedule_task.fapi_path', tmpdir), \
                patch('schedule_task.cta_usdt_get_all_need_tpsl_cta_keys',
                      return_value=['ETHUSDT_4h_demo']), \
                patch('schedule_task.cta_usdt_get_trade_info',
                      return_value=trade_info), \
                patch('schedule_task.fetch_binance_ticker_data') as ticker:
            cta_usdt_takeprofit_and_stoploss([])

        ticker.assert_not_called()


if __name__ == '__main__':
    unittest.main()
