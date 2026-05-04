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


class CtaUsdtStartSyncTest(unittest.TestCase):
    def _run_init(self, sync_last_signal=False, account_type="unified"):
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
                    mock.patch.object(schedule_task, "fapi_path", temp_dir), \
                    mock.patch.object(schedule_task, "get_kline", return_value=klines), \
                    mock.patch.object(schedule_task, "cta_usdt_update_trade_info"), \
                    mock.patch.object(schedule_task, "send_wechat"), \
                    mock.patch.object(schedule_task.time, "sleep"), \
                    mock.patch.object(schedule_task, "cta_excute_period") as execute_period:
                schedule_task.cta_excute_init(
                    object(),
                    "ETHUSDT",
                    "4h",
                    "adapt_bolling_anti_chase",
                    "[200,20]",
                    account_type,
                    sync_last_signal=sync_last_signal,
                )
                return execute_period, add_job

    def test_cta_usdt_start_can_sync_last_effective_signal_in_aggressive_mode(self):
        execute_period, _ = self._run_init(sync_last_signal=True)

        execute_period.assert_called_once()
        self.assertEqual(execute_period.call_args.args[:5], (
            mock.ANY,
            "ETHUSDT",
            "4h",
            "adapt_bolling_anti_chase",
            "[200,20]",
        ))
        self.assertEqual(execute_period.call_args.args[5], "unified")
        self.assertTrue(execute_period.call_args.kwargs["pos_infer"])

    def test_cta_usdt_start_replaces_existing_scheduler_job(self):
        _, add_job = self._run_init()

        self.assertEqual(
            add_job.call_args.kwargs["id"],
            "ETHUSDT_4h_adapt_bolling_anti_chase_[200,20]",
        )
        self.assertTrue(add_job.call_args.kwargs["replace_existing"])

    def test_unified_cta_check_position_skips_legacy_total_position_calibration(self):
        with mock.patch.object(schedule_task.scheduler, "app", _FakeApp()), \
                mock.patch.object(schedule_task, "robust") as robust:
            schedule_task.cta_check_position(
                object(),
                [["admin_v3_unified", "ETHUSDT", "4h",
                  "adapt_bolling_anti_chase", "[200,20]", 0]],
                "admin_v3_unified",
                account_type="unified",
            )

        robust.assert_not_called()

    def test_cta_usdt_start_all_uses_appended_account_type_not_position_amount(self):
        params_list = [[
            object(),
            "ETHUSDT",
            "4h",
            "adapt_bolling_anti_chase",
            "[200,20]",
            0,
            0,
            "unified",
        ]]

        with mock.patch.object(schedule_task, "cta_excute_init") as init:
            schedule_task.cta_excute_init_all(params_list)

        self.assertEqual(init.call_args.args[5], "unified")


class CtaUsdExecutePeriodSyncTest(unittest.TestCase):
    def test_pos_infer_reconciles_position_to_current_signal(self):
        klines = pd.DataFrame({
            "candle_begin_time": pd.date_range("2026-01-01", periods=3, freq="4h"),
            "open": [1, 2, 3],
            "high": [1, 2, 3],
            "low": [1, 2, 3],
            "close": [1, 2, 3],
            "volume": [1, 1, 1],
        })
        signal_df = klines.copy()
        signal_df["signal"] = [None, None, 1]

        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.object(schedule_task.scheduler, "app", _FakeApp()), \
                    mock.patch.object(schedule_task, "dapi_path", temp_dir), \
                    mock.patch.object(schedule_task.pd, "read_csv", return_value=klines), \
                    mock.patch.object(schedule_task, "dapi_get_kline", return_value=klines), \
                    mock.patch.object(schedule_task.factors, "parse_cta_period",
                                      return_value=[200, 20]), \
                    mock.patch.object(schedule_task.factors,
                                      "adapt_bolling_anti_chase",
                                      return_value=(signal_df, None)), \
                    mock.patch.object(schedule_task,
                                      "cta_usd_sync_position_to_signal",
                                      return_value={"status": 0}) as sync_position:
                schedule_task.cta_usd_excute_period(
                    object(),
                    "ETHUSD_PERP",
                    "4h",
                    "adapt_bolling_anti_chase",
                    "[200,20]",
                    "unified",
                    pos_infer=True,
                )

        sync_position.assert_called_once_with(
            mock.ANY,
            "ETHUSD_PERP_4h_adapt_bolling_anti_chase_[200,20]",
            "unified",
            target_signal=1,
        )


class CtaUsdtExecutePeriodSyncTest(unittest.TestCase):
    def test_pos_infer_uses_cta_delta_and_unified_um_order_route(self):
        klines = pd.DataFrame({
            "candle_begin_time": pd.date_range("2026-01-01", periods=3, freq="4h"),
            "open": [1, 2, 3],
            "high": [1, 2, 3],
            "low": [1, 2, 3],
            "close": [1, 2, 3],
            "volume": [1, 1, 1],
        })
        signal_df = klines.copy()
        signal_df["signal"] = [None, 1, None]

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(
                temp_dir, "ETHUSDT_4h_adapt_bolling_anti_chase_[200,20].csv")
            klines.to_csv(path, index=False)

            with mock.patch.object(schedule_task.scheduler, "app", _FakeApp()), \
                    mock.patch.object(schedule_task, "fapi_path", temp_dir), \
                    mock.patch.object(schedule_task, "get_kline", return_value=klines), \
                    mock.patch.object(schedule_task.factors, "parse_cta_period",
                                      return_value=[200, 20]), \
                    mock.patch.object(schedule_task.factors,
                                      "adapt_bolling_anti_chase",
                                      return_value=(signal_df, None)), \
                    mock.patch.object(schedule_task,
                                      "cta_usdt_get_trade_info",
                                      return_value={
                                          "signal": 0,
                                          "net_value": 500,
                                          "trade_ratio": 1,
                                          "position_amount": 0,
                                      }), \
                    mock.patch.object(schedule_task, "get_exchange_info",
                                      return_value=({"ETHUSDT": 3},
                                                    {"ETHUSDT": 2})), \
                    mock.patch.object(schedule_task,
                                      "fetch_binance_ticker_data",
                                      return_value=2500), \
                    mock.patch.object(schedule_task,
                                      "cta_usdt_update_trade_info"), \
                    mock.patch.object(schedule_task,
                                      "cta_usdt_open_limit_order",
                                      return_value=True) as open_order:
                schedule_task.cta_excute_period(
                    object(),
                    "ETHUSDT",
                    "4h",
                    "adapt_bolling_anti_chase",
                    "[200,20]",
                    "unified",
                    pos_infer=True,
                )

        self.assertEqual(open_order.call_args.args[2], 0.2)
        self.assertIn("order_func", open_order.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
