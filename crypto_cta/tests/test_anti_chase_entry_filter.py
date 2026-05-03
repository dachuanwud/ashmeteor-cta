import unittest

import pandas as pd


class AntiChaseEntryFilterTest(unittest.TestCase):
    def test_blocks_short_entry_when_price_is_too_far_below_fast_midline(self):
        from cta_api.function import process_anti_chase_entry_filter

        df = pd.DataFrame(
            {
                "close": [100, 70, 72],
                "median_fast": [100, 100, 100],
                "signal": [None, -1, None],
            }
        )

        result = process_anti_chase_entry_filter(df, max_fast_bias=0.25)

        self.assertEqual(result["signal"].fillna("nan").tolist(), ["nan", 0, "nan"])
        self.assertTrue(result.loc[1, "anti_chase_block_trigger"])

    def test_blocks_long_entry_when_price_is_too_far_above_fast_midline(self):
        from cta_api.function import process_anti_chase_entry_filter

        df = pd.DataFrame(
            {
                "close": [100, 130, 128],
                "median_fast": [100, 100, 100],
                "signal": [None, 1, None],
            }
        )

        result = process_anti_chase_entry_filter(df, max_fast_bias=0.25)

        self.assertEqual(result["signal"].fillna("nan").tolist(), ["nan", 0, "nan"])
        self.assertTrue(result.loc[1, "anti_chase_block_trigger"])

    def test_keeps_entry_when_bias_is_inside_limit(self):
        from cta_api.function import process_anti_chase_entry_filter

        df = pd.DataFrame(
            {
                "close": [100, 82, 105],
                "median_fast": [100, 100, 100],
                "signal": [None, -1, 1],
            }
        )

        result = process_anti_chase_entry_filter(df, max_fast_bias=0.25)

        self.assertEqual(result["signal"].fillna("nan").tolist(), ["nan", -1, 1])
        self.assertFalse(result["anti_chase_block_trigger"].any())


if __name__ == "__main__":
    unittest.main()
