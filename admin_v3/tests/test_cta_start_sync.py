import os
import sys
import tempfile
import unittest
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import schedule_task


class _NoopContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeApp:
    def app_context(self):
        return _NoopContext()


class CtaUsdStartSyncTest(unittest.TestCase):
    def _run_init(self, sync_last_signal=False):
        klines = pd.DataFrame({
            "candle_begin_time": pd.date_range("2026-01-01", periods=3, freq="4h"),
            "open": [1, 2, 3],
            "high": [1, 2, 3],
            "low": [1, 2, 3],
            "close": [1, 2, 3],
            "volume": [1, 1, 1],
        })

        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.object(schedule_task.scheduler, "app", _FakeApp()), \
                    mock.patch.object(schedule_task.scheduler, "add_job") as add_job, \
                    mock.patch.object(schedule_task, "dapi_path", temp_dir), \
                    mock.patch.object(schedule_task, "dapi_get_kline", return_value=klines), \
                    mock.patch.object(schedule_task, "cta_usd_update_trade_info"), \
                    mock.patch.object(schedule_task, "send_wechat"), \
                    mock.patch.object(schedule_task.time, "sleep"), \
                    mock.patch.object(schedule_task, "cta_usd_excute_period") as execute_period:
                schedule_task.cta_usd_excute_init(
                    object(),
                    "ETHUSD_PERP",
                    "4h",
                    "adapt_bolling_anti_chase",
                    "[200,20]",
                    "unified",
                    sync_last_signal=sync_last_signal,
                )
                return execute_period, add_job

    def test_cta_usd_start_does_not_sync_last_signal_by_default(self):
        execute_period, _ = self._run_init()

        execute_period.assert_not_called()

    def test_cta_usd_start_can_sync_last_effective_signal_in_aggressive_mode(self):
        execute_period, _ = self._run_init(sync_last_signal=True)

        execute_period.assert_called_once()
        self.assertEqual(execute_period.call_args.args[:5], (
            mock.ANY,
            "ETHUSD_PERP",
            "4h",
            "adapt_bolling_anti_chase",
            "[200,20]",
        ))
        self.assertEqual(execute_period.call_args.args[5], "unified")
        self.assertTrue(execute_period.call_args.kwargs["pos_infer"])

    def test_cta_usd_start_replaces_existing_scheduler_job(self):
        _, add_job = self._run_init()

        self.assertTrue(add_job.call_args.kwargs["replace_existing"])


if __name__ == "__main__":
    unittest.main()
