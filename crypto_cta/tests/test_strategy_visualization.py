import unittest

import pandas as pd


class StrategyVisualizationTest(unittest.TestCase):
    def test_select_overlay_columns_keeps_known_strategy_lines_in_order(self):
        from cta_api.strategy_visualization import select_overlay_columns

        df = pd.DataFrame(
            {
                "close": [1, 2],
                "upper": [3, 4],
                "lower": [0, 1],
                "median": [1.5, 2.5],
                "flash_stop_win": [1.2, 2.2],
                "signal": [None, 1],
            }
        )

        self.assertEqual(select_overlay_columns(df), ["upper", "lower", "median", "flash_stop_win"])

    def test_build_signal_markers_splits_long_short_and_close_triggers(self):
        from cta_api.strategy_visualization import build_signal_markers

        df = pd.DataFrame(
            {
                "candle_begin_time": pd.date_range("2024-01-01", periods=5, freq="h"),
                "high": [11, 12, 13, 14, 15],
                "low": [9, 8, 7, 6, 5],
                "close": [10, 11, 12, 13, 14],
                "signal": [None, 1, 0, -1, 0],
            }
        )

        markers = build_signal_markers(df)

        self.assertEqual(markers["开多"]["y"].round(3).tolist(), [12.072])
        self.assertEqual(markers["平仓"]["y"].tolist(), [12, 14])
        self.assertEqual(markers["开空"]["y"].round(3).tolist(), [5.964])


if __name__ == "__main__":
    unittest.main()
