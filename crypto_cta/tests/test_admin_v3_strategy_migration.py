import unittest

import pandas as pd


def sample_ohlcv(closes):
    return pd.DataFrame(
        {
            "candle_begin_time": pd.date_range("2024-01-01", periods=len(closes), freq="h"),
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1] * len(closes),
            "quote_volume": [1] * len(closes),
            "trade_num": [1] * len(closes),
            "taker_buy_base_asset_volume": [1] * len(closes),
            "taker_buy_quote_asset_volume": [1] * len(closes),
            "offset": [0] * len(closes),
            "kline_pct": [[0]] * len(closes),
        }
    )


class AdminV3StrategyMigrationTest(unittest.TestCase):
    def test_adapt_bolling_opens_long_and_closes_below_middle(self):
        from factors import adapt_bolling

        df = sample_ohlcv([10, 10, 10, 12, 7, 7, 8, 9, 10, 9, 8, 14])

        result = adapt_bolling.signal(df, para=[3], proportion=100, leverage_rate=1)

        signals = result["signal"].dropna()
        self.assertEqual(signals.loc[6], 1)
        self.assertEqual(signals.loc[9], 0)

    def test_adapt_bolling_reverse_opens_short_on_upper_breakout(self):
        from factors import adapt_bolling_reverse

        df = sample_ohlcv([10, 10, 10, 8, 8, 8, 9])

        result = adapt_bolling_reverse.signal(df, para=[3], proportion=100, leverage_rate=1)

        signals = result["signal"].dropna()
        self.assertEqual(signals.loc[6], -1)

    def test_dc_flash_opens_long_on_dc_upper_breakout_with_positive_mtm(self):
        from factors import dc_flash

        df = sample_ohlcv([10, 10, 10, 8, 8, 8, 9])

        result = dc_flash.signal(df, para=[3], proportion=100, leverage_rate=1)

        signals = result["signal"].dropna()
        self.assertEqual(signals.loc[6], 1)

    def test_mtm_bolling_uses_crypto_cta_factor_interface(self):
        from factors import mtm_bolling

        df = sample_ohlcv([10, 10, 10, 12, 11.8, 11.6, 10.9, 10.2, 9.8])

        result = mtm_bolling.signal(df, para=[3], proportion=100, leverage_rate=1)

        self.assertIn("signal", result.columns)
        self.assertGreaterEqual(len(mtm_bolling.para_list()), 1)


if __name__ == "__main__":
    unittest.main()
