import os
import sys
import unittest

import pandas as pd
from sqlalchemy import create_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schedule_task import (_append_ledger_row, _concat_ledger_frame,
                           _get_um_margin_balance, _read_ledger_table)


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

    def test_unified_um_margin_balance_uses_account_adapter(self):
        balance = _get_um_margin_balance(UnifiedAccountSummaryExchange(),
                                         'unified')

        self.assertEqual(balance, 123.45)


if __name__ == '__main__':
    unittest.main()
