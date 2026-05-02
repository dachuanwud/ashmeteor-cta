import unittest


class RunConfiguredTest(unittest.TestCase):
    def test_normalize_task_list_accepts_string_or_list_aliases(self):
        from cta_api.run_configured import normalize_task_list

        self.assertEqual(normalize_task_list("backtest"), ["backtest"])
        self.assertEqual(normalize_task_list("sweep, plot, single"), ["sweep", "plot", "backtest"])
        self.assertEqual(normalize_task_list(["optimize", "evaluate"]), ["sweep", "plot"])

    def test_normalize_task_list_rejects_unknown_task(self):
        from cta_api.run_configured import normalize_task_list

        with self.assertRaises(ValueError):
            normalize_task_list(["backtest", "unknown"])

    def test_task_script_mapping(self):
        from cta_api.run_configured import task_script_names

        self.assertEqual(
            task_script_names(["backtest", "sweep", "plot", "visualize"]),
            ["2_fast_backview.py", "3_fastover.py", "4_strategy_evaluate.py", "5_strategy_visualize.py"],
        )


if __name__ == "__main__":
    unittest.main()
