import unittest

import numpy as np
import pandas as pd


def sample_ohlcv(rows=360):
    idx = np.arange(rows)
    close = 100 + np.sin(idx / 7) * 8 + idx * 0.03
    close[80:95] += np.linspace(0, 25, 15)
    close[160:180] -= np.linspace(0, 30, 20)
    close[250:270] += np.linspace(0, 22, 20)
    return pd.DataFrame(
        {
            "candle_begin_time": pd.date_range("2024-01-01", periods=rows, freq="h"),
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.ones(rows),
            "quote_volume": np.ones(rows),
            "trade_num": np.ones(rows),
            "taker_buy_base_asset_volume": np.ones(rows),
            "taker_buy_quote_asset_volume": np.ones(rows),
            "offset": np.zeros(rows),
            "kline_pct": [[0]] * rows,
        }
    )


def reference_dc_flash_core(df, n):
    from factors._admin_v3_utils import atr

    ma_dict = {}
    stop_loss_pct = 10
    holding_times_min = 10
    df["signal"] = np.nan
    df["median"] = df["close"].rolling(n, min_periods=1).mean()
    df["flash_stop_win"] = df["median"].copy()
    df["upper"] = df["close"].rolling(n).max().shift(1)
    df["lower"] = df["close"].rolling(n).min().shift(1)
    df["mtm"] = df["close"] / df["close"].shift(n) - 1
    df["atr"] = atr(df, n)
    df.loc[(df["close"] > df["upper"]) & (df["mtm"] > 0) & (df["close"].shift(1) <= df["upper"].shift(1)), "signal_long"] = 1
    df.loc[(df["close"] < df["median"]) & (df["close"].shift(1) >= df["median"].shift(1)), "signal_long"] = 0
    df.loc[(df["close"] < df["lower"]) & (df["mtm"] < 0) & (df["close"].shift(1) >= df["lower"].shift(1)), "signal_short"] = -1
    df.loc[(df["close"] > df["median"]) & (df["close"].shift(1) <= df["median"].shift(1)), "signal_short"] = 0

    info = {"pre_signal": 0, "stop_lose_price": None, "holding_times": 0, "stop_win_times": 0, "stop_win_price": 0}
    for i in range(df.shape[0]):
        if info["pre_signal"] == 0:
            if df.at[i, "signal_long"] == 1:
                df.at[i, "signal"] = 1
                info = {"pre_signal": 1, "stop_lose_price": df.at[i, "close"] * (1 - stop_loss_pct / 100), "holding_times": 0, "stop_win_times": 0, "stop_win_price": 0}
            elif df.at[i, "signal_short"] == -1:
                df.at[i, "signal"] = -1
                info = {"pre_signal": -1, "stop_lose_price": df.at[i, "close"] * (1 + stop_loss_pct / 100), "holding_times": 0, "stop_win_times": 0, "stop_win_price": 0}
            else:
                info = {"pre_signal": 0, "stop_lose_price": None, "holding_times": 0, "stop_win_times": 0, "stop_win_price": 0}
        elif info["pre_signal"] == 1:
            holding_times = info["holding_times"]
            if df.at[i, "atr"] < df.at[i - 1, "atr"]:
                info["holding_times"] = holding_times + 1
            if df.at[i, "close"] > df.at[i - 1, "close"]:
                info["holding_times"] = max(holding_times - 1, 0)
            ma_temp = max(n - int(n / 50) * 10 * info["holding_times"], holding_times_min)
            ma_dict.setdefault(ma_temp, df["close"].rolling(ma_temp, min_periods=1).mean())
            df.at[i, "flash_stop_win"] = ma_dict[ma_temp].at[i]
            if df.at[i, "close"] < df.at[i, "flash_stop_win"]:
                if df.at[i, "close"] > info["stop_win_price"] or info["stop_win_times"] == 0:
                    info["stop_win_price"] = df.at[i, "close"]
                    info["stop_win_times"] += 1
                    info["holding_times"] = 0
                else:
                    df.at[i, "signal_long"] = 0
            if df.at[i, "signal_long"] == 0 or df.at[i, "close"] < info["stop_lose_price"]:
                df.at[i, "signal"] = 0
                info = {"pre_signal": 0, "stop_lose_price": None, "holding_times": 0, "stop_win_times": 0, "stop_win_price": 0}
            if df.at[i, "signal_short"] == -1:
                df.at[i, "signal"] = -1
                info = {"pre_signal": -1, "stop_lose_price": df.at[i, "close"] * (1 + stop_loss_pct / 100), "holding_times": 0, "stop_win_times": 0, "stop_win_price": 0}
        elif info["pre_signal"] == -1:
            holding_times = info["holding_times"]
            if df.at[i, "atr"] < df.at[i - 1, "atr"]:
                info["holding_times"] = holding_times + 1
            if df.at[i, "close"] < df.at[i - 1, "close"]:
                info["holding_times"] = max(holding_times - 1, 0)
            ma_temp = max(n - int(n / 50) * 10 * info["holding_times"], holding_times_min)
            ma_dict.setdefault(ma_temp, df["close"].rolling(ma_temp, min_periods=1).mean())
            df.at[i, "flash_stop_win"] = ma_dict[ma_temp].at[i]
            if df.at[i, "close"] > df.at[i, "flash_stop_win"]:
                if df.at[i, "close"] < info["stop_win_price"] or info["stop_win_times"] == 0:
                    info["stop_win_price"] = df.at[i, "close"]
                    info["stop_win_times"] += 1
                    info["holding_times"] = 0
                else:
                    df.at[i, "signal_short"] = 0
            if df.at[i, "signal_short"] == 0 or df.at[i, "close"] > info["stop_lose_price"]:
                df.at[i, "signal"] = 0
                info = {"pre_signal": 0, "stop_lose_price": None, "holding_times": 0, "stop_win_times": 0, "stop_win_price": 0}
            if df.at[i, "signal_long"] == 1:
                df.at[i, "signal"] = 1
                info = {"pre_signal": 1, "stop_lose_price": df.at[i, "close"] * (1 - stop_loss_pct / 100), "holding_times": 0, "stop_win_times": 0, "stop_win_price": 0}
    return df


class DcFlashOptimizationTest(unittest.TestCase):
    def test_dynamic_stop_windows_are_precomputable(self):
        from factors._admin_v3_utils import dc_flash_ma_windows

        self.assertEqual(dc_flash_ma_windows(10), [10])
        self.assertEqual(dc_flash_ma_windows(55), [55, 45, 35, 25, 15, 10])
        self.assertEqual(dc_flash_ma_windows(290), [290, 240, 190, 140, 90, 40, 10])

    def test_optimized_dc_flash_matches_reference_logic(self):
        from factors._admin_v3_utils import dc_flash_core

        df = sample_ohlcv()
        expected = reference_dc_flash_core(df.copy(), 55)
        actual = dc_flash_core(df.copy(), 55)

        for col in ["signal", "signal_long", "signal_short", "flash_stop_win"]:
            pd.testing.assert_series_equal(actual[col], expected[col], check_names=False)


if __name__ == "__main__":
    unittest.main()
