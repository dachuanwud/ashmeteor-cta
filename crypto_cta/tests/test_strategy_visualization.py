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

    def test_build_signal_markers_splits_special_close_triggers(self):
        from cta_api.strategy_visualization import build_signal_markers

        df = pd.DataFrame(
            {
                "candle_begin_time": pd.date_range("2024-01-01", periods=8, freq="h"),
                "high": [11, 12, 13, 14, 15, 16, 17, 18],
                "low": [9, 8, 7, 6, 5, 4, 3, 2],
                "close": [10, 11, 12, 13, 14, 15, 16, 17],
                "signal": [None, 1, 0, -1, 0, 0, 0, 0],
                "stop_loss_trigger": [False, False, False, False, True, False, False, False],
                "anti_chase_block_trigger": [False, False, False, False, False, False, True, False],
            }
        )

        markers = build_signal_markers(df)

        self.assertEqual(markers["开多"]["y"].round(3).tolist(), [12.072])
        self.assertEqual(markers["平仓"]["y"].tolist(), [12, 15, 17])
        self.assertEqual(markers["止损平仓"]["y"].tolist(), [14])
        self.assertEqual(markers["追单过滤"]["y"].tolist(), [16])
        self.assertEqual(markers["开空"]["y"].round(3).tolist(), [5.964])

    def test_add_equity_diagnostics_uses_running_peak_drawdown(self):
        from cta_api.strategy_visualization import add_equity_diagnostics

        df = pd.DataFrame(
            {
                "equity_curve": [1.0, 1.5, 1.2, 1.8, 0.9],
                "close": [100, 120, 110, 130, 125],
            }
        )

        result = add_equity_diagnostics(df)

        self.assertEqual(result["equity_peak"].round(2).tolist(), [1.0, 1.5, 1.5, 1.8, 1.8])
        self.assertEqual(result["drawdown"].round(4).tolist(), [0.0, 0.0, -0.2, 0.0, -0.5])
        self.assertEqual(result["benchmark_equity"].round(4).tolist(), [1.0, 1.2, 1.1, 1.3, 1.25])
        self.assertEqual(result["benchmark_drawdown"].round(4).tolist(), [0.0, 0.0, -0.0833, 0.0, -0.0385])

    def test_build_parameter_rank_summary_marks_selected_parameter(self):
        from cta_api.strategy_visualization import build_parameter_rank_summary

        parameter_df = pd.DataFrame(
            {
                "para": ["[230]", "[330]", "[250]"],
                "累积净值": [8.99, 10.49, 8.55],
                "年化收益": ["0.55", "0.60", "0.53"],
                "最大回撤": ["-47.80%", "-54.26%", "-54.19%"],
                "年化收益/回撤比": [1.15, 1.10, 0.98],
            }
        )

        rows = build_parameter_rank_summary(parameter_df, selected_para=[330], top_n=3)

        self.assertEqual(rows[0]["parameter"], "[230]")
        self.assertFalse(rows[0]["selected"])
        self.assertEqual(rows[1]["parameter"], "[330]")
        self.assertTrue(rows[1]["selected"])
        self.assertEqual(rows[1]["rank"], 2)

    def test_select_comparison_parameters_keeps_current_parameter_with_top_ranked(self):
        from cta_api.strategy_visualization import select_comparison_parameters

        parameter_df = pd.DataFrame(
            {
                "para": ["[230]", "[250]", "[400]", "[330]"],
                "年化收益/回撤比": [1.15, 0.98, 0.85, 1.10],
            }
        )

        selected = select_comparison_parameters(parameter_df, current_para=[330], limit=3)

        self.assertEqual(selected, [[330], [230], [250]])

    def test_build_comparison_summary_sorts_current_parameter_first(self):
        from cta_api.strategy_visualization import build_comparison_summary

        analyses = [
            {"para": [230], "metrics": pd.DataFrame({0: {"累积净值": 8.99, "最大回撤": "-47.80%"}}), "trade": pd.DataFrame(index=[1, 2])},
            {"para": [330], "metrics": pd.DataFrame({0: {"累积净值": 10.49, "最大回撤": "-54.26%"}}), "trade": pd.DataFrame(index=[1, 2, 3])},
        ]

        rows = build_comparison_summary(analyses, current_para=[330])

        self.assertEqual(rows[0]["parameter"], "[330]")
        self.assertTrue(rows[0]["selected"])
        self.assertEqual(rows[0]["trade_count"], 3)
        self.assertEqual(rows[1]["parameter"], "[230]")

    def test_build_metric_cards_includes_trade_count_and_average_holding(self):
        from cta_api.strategy_visualization import build_metric_cards

        metrics = pd.DataFrame(
            {
                0: {
                    "累积净值": 10.49,
                    "年化收益": "0.6",
                    "最大回撤": "-54.26%",
                    "年化收益/回撤比": 1.1,
                    "胜率": "41.86%",
                    "平均持仓周期": "34 天 13 小时 46 分钟",
                }
            }
        )
        trade = pd.DataFrame(index=range(43))

        cards = build_metric_cards(metrics, [330], trade)

        self.assertIn(("开仓次数", "43", ""), cards)
        self.assertIn(("平均持仓", "34 天 13 小时 46 分钟", ""), cards)


if __name__ == "__main__":
    unittest.main()
