import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import factors


class CtaPeriodAndFactorTest(unittest.TestCase):
    def test_parse_cta_period_accepts_single_and_list_parameters(self):
        self.assertEqual(factors.parse_cta_period("200"), 200)
        self.assertEqual(factors.parse_cta_period("[200,20]"), [200, 20])
        self.assertEqual(factors.parse_cta_period("200,20"), [200, 20])
        self.assertEqual(factors.format_cta_period("[200, 20]"), "[200,20]")

    def test_anti_chase_filter_blocks_overextended_short_entry(self):
        df = pd.DataFrame(
            {
                "close": [100, 70, 72],
                "median_fast": [100, 100, 100],
                "signal": [None, -1, None],
            }
        )

        result = factors.process_anti_chase_entry_filter(df, max_fast_bias=0.20)

        self.assertEqual(result["signal"].fillna("nan").tolist(), ["nan", 0, "nan"])
        self.assertTrue(result.loc[1, "anti_chase_block_trigger"])

    def test_adapt_bolling_anti_chase_accepts_native_two_dimensional_period(self):
        df = pd.DataFrame(
            {
                "candle_begin_time": pd.date_range("2024-01-01", periods=80, freq="4h"),
                "open": list(range(100, 180)),
                "high": list(range(101, 181)),
                "low": list(range(99, 179)),
                "close": list(range(100, 180)),
                "volume": [1] * 80,
            }
        )

        result, median, upper, lower, signal_data = factors.adapt_bolling_anti_chase(df, "[20,20]")

        self.assertIn("median_fast", result.columns)
        self.assertIn("fast_bias", result.columns)
        self.assertEqual(len(median), len(result))
        self.assertEqual(len(upper), len(result))
        self.assertEqual(len(lower), len(result))
        self.assertIsInstance(signal_data, list)


if __name__ == "__main__":
    unittest.main()
