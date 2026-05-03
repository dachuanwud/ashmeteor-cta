import unittest

import pandas as pd


class AdaptBollingFlashTest(unittest.TestCase):
    def test_adaptive_bolling_flash_emits_signal_and_flash_stop_line(self):
        from factors import adapt_bolling_flash

        close = [100.0] * 40 + [150.0, 100.0, 200.0]
        df = pd.DataFrame(
            {
                "candle_begin_time": pd.date_range("2024-01-01", periods=len(close), freq="h"),
                "open": close,
                "high": [price * 1.01 for price in close],
                "low": [price * 0.99 for price in close],
                "close": close,
                "volume": [1.0] * len(close),
            }
        )

        result = adapt_bolling_flash.signal(df, para=[20], proportion=0.05, leverage_rate=1)

        for column in ["median", "upper", "lower", "flash_stop_win", "signal"]:
            self.assertIn(column, result.columns)
        self.assertTrue(result["signal"].notna().any())


if __name__ == "__main__":
    unittest.main()
