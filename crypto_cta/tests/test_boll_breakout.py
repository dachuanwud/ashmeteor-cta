import unittest

import pandas as pd

from factors import boll_breakout


class BollBreakoutSignalTest(unittest.TestCase):
    def test_opens_long_on_upper_breakout_and_closes_below_middle(self):
        df = pd.DataFrame(
            {
                "candle_begin_time": pd.date_range("2024-01-01", periods=7, freq="h"),
                "open": [10, 10, 10, 12, 11.5, 11.4, 11.3],
                "high": [10, 10, 10, 12, 11.5, 11.4, 11.3],
                "low": [10, 10, 10, 12, 11.5, 11.4, 11.3],
                "close": [10, 10, 10, 12, 11.5, 11.4, 11.3],
                "volume": [1] * 7,
                "quote_volume": [1] * 7,
                "trade_num": [1] * 7,
                "taker_buy_base_asset_volume": [1] * 7,
                "taker_buy_quote_asset_volume": [1] * 7,
                "offset": [0] * 7,
                "kline_pct": [[0]] * 7,
            }
        )

        result = boll_breakout.signal(df, para=[3, 1], proportion=100, leverage_rate=1)

        signals = result["signal"].dropna()
        self.assertEqual(signals.loc[3], 1)
        self.assertEqual(signals.loc[5], 0)


if __name__ == "__main__":
    unittest.main()
