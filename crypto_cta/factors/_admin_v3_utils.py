import numpy as np
import pandas as pd

from cta_api.function import process_stop_loss_close

try:
    import talib
except ImportError:
    talib = None


EPS = 1e-8


def parse_n(para, default=55):
    if isinstance(para, (list, tuple)):
        return int(para[0]) if para else default
    return int(para)


def finish_signal(df, proportion, leverage_rate, drop_cols=None):
    if drop_cols:
        df.drop([col for col in drop_cols if col in df.columns], axis=1, inplace=True)
    return process_stop_loss_close(df, proportion, leverage_rate=leverage_rate)


def dedupe_signal(df):
    temp = df[df["signal"].notnull()][["signal"]]
    temp = temp[temp["signal"] != temp["signal"].shift(1)]
    df["signal"] = temp["signal"]
    return df


def merge_persistent_signals(df, fill_zero=True):
    df["signal_short"] = df["signal_short"].ffill()
    df["signal_long"] = df["signal_long"].ffill()
    df["signal"] = df[["signal_long", "signal_short"]].sum(axis=1, min_count=1, skipna=True)
    if fill_zero:
        df["signal"] = df["signal"].fillna(value=0)
    return df


def wma(series, n):
    if talib is not None:
        return pd.Series(talib.WMA(series.astype(float).to_numpy(), timeperiod=n), index=series.index)

    weights = np.arange(1, n + 1, dtype=float)

    def _calc(values):
        weights_tail = weights[-len(values):]
        return np.dot(values, weights_tail) / weights_tail.sum()

    return series.rolling(n, min_periods=1).apply(_calc, raw=True)


def true_range(df):
    c1 = df["high"] - df["low"]
    c2 = (df["high"] - df["close"].shift(1)).abs()
    c3 = (df["low"] - df["close"].shift(1)).abs()
    return pd.concat([c1, c2, c3], axis=1).max(axis=1)


def atr(df, n):
    if talib is not None:
        return pd.Series(
            talib.ATR(
                df["high"].astype(float).to_numpy(),
                df["low"].astype(float).to_numpy(),
                df["close"].astype(float).to_numpy(),
                timeperiod=n,
            ),
            index=df.index,
        )
    return true_range(df).rolling(n, min_periods=1).mean()


def adx(df, n):
    if talib is not None:
        return pd.Series(
            talib.ADX(
                df["high"].astype(float).to_numpy(),
                df["low"].astype(float).to_numpy(),
                df["close"].astype(float).to_numpy(),
                timeperiod=n,
            ),
            index=df.index,
        )

    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr_value = atr(df, n).replace(0, np.nan)
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(n, min_periods=1).mean() / atr_value
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(n, min_periods=1).mean() / atr_value
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    return dx.rolling(n, min_periods=1).mean()


def linear_reg_angle(series, n):
    if talib is not None:
        return pd.Series(talib.LINEARREG_ANGLE(series.astype(float).to_numpy(), timeperiod=n), index=series.index)

    x = np.arange(n, dtype=float)

    def _angle(values):
        local_x = x[-len(values):]
        if len(values) < 2:
            return 0.0
        slope = np.polyfit(local_x, values, 1)[0]
        return np.degrees(np.arctan(slope))

    return series.rolling(n, min_periods=1).apply(_angle, raw=True)


def apply_bias_filter(df):
    df["temp"] = df["signal"]
    df.loc[(df["signal"] == 1) & (df["bias"] > df["bias_pct"]), "temp"] = None
    df.loc[(df["signal"] == -1) & (df["bias"] < -df["bias_pct"]), "temp"] = None
    df.loc[(df["signal"] != df["signal"].shift(1)) & df["temp"].isnull(), "temp"] = 0
    df["temp"] = df["temp"].ffill()
    df["signal"] = df["temp"]
    return df


def adaptive_bolling_core(df, n, reverse=False, bias_filter=True):
    df["median"] = df["close"].rolling(n, min_periods=1).mean()
    df["std"] = df["close"].rolling(n, min_periods=1).std(ddof=0)
    df["z_score"] = (df["close"] - df["median"]).abs() / df["std"].replace(0, np.nan)
    df["m"] = df["z_score"].rolling(n, min_periods=1).mean().shift()
    df["upper"] = df["median"] + df["m"] * df["std"]
    df["lower"] = df["median"] - df["m"] * df["std"]
    df.bfill(inplace=True)
    df["bias"] = df["close"] / (df["median"] + EPS) - 1
    df["bias_pct"] = df["bias"].abs().rolling(n, min_periods=1).max().shift()

    if reverse:
        df.loc[(df["close"] > df["upper"]) & (df["close"].shift(1) <= df["upper"].shift(1)), "signal_short"] = -1
        df.loc[(df["close"] < df["median"]) & (df["close"].shift(1) >= df["median"].shift(1)), "signal_short"] = 0
        df.loc[(df["close"] < df["lower"]) & (df["close"].shift(1) >= df["lower"].shift(1)), "signal_long"] = 1
        df.loc[(df["close"] > df["median"]) & (df["close"].shift(1) <= df["median"].shift(1)), "signal_long"] = 0
    else:
        df.loc[(df["close"] > df["upper"]) & (df["close"].shift(1) <= df["upper"].shift(1)), "signal_long"] = 1
        df.loc[(df["close"] < df["median"]) & (df["close"].shift(1) >= df["median"].shift(1)), "signal_long"] = 0
        df.loc[(df["close"] < df["lower"]) & (df["close"].shift(1) >= df["lower"].shift(1)), "signal_short"] = -1
        df.loc[(df["close"] > df["median"]) & (df["close"].shift(1) <= df["median"].shift(1)), "signal_short"] = 0

    merge_persistent_signals(df)
    if bias_filter:
        apply_bias_filter(df)
    return dedupe_signal(df)


def atr_bolling_bias_core(df, n, use_wma=False, reverse=False):
    df["atr"] = atr(df, n)
    df["std"] = df["close"].rolling(n, min_periods=1).std(ddof=0)
    df["median"] = wma(df["close"], n) if use_wma else df["close"].rolling(n, min_periods=1).mean()
    df["atr_J"] = (df["close"] - df["median"]).abs() / df["atr"].replace(0, np.nan)
    df["m_atr"] = df["atr_J"].rolling(n, min_periods=1).max().shift(1)
    df["boll_J"] = (df["close"] - df["median"]).abs() / df["std"].replace(0, np.nan)
    df["m_boll"] = df["boll_J"].rolling(n, min_periods=1).max().shift(1)
    df["upper_atr"] = df["median"] + df["m_atr"] * df["atr"]
    df["lower_atr"] = df["median"] - df["m_atr"] * df["atr"]
    df["upper_boll"] = df["median"] + df["m_boll"] * df["std"]
    df["lower_boll"] = df["median"] - df["m_boll"] * df["std"]
    df["upper"] = df[["upper_atr", "upper_boll"]].mean(axis=1)
    df["lower"] = df[["lower_atr", "lower_boll"]].mean(axis=1)
    df.bfill(inplace=True)
    df["bias"] = df["close"] / (df["median"] + EPS) - 1
    df["bias_pct"] = df["bias"].abs().rolling(n, min_periods=1).max().shift()

    if reverse:
        df.loc[(df["close"] > df["upper"]) & (df["close"].shift(1) <= df["upper"].shift(1)), "signal_short"] = -1
        df.loc[(df["close"] < df["median"]) & (df["close"].shift(1) >= df["median"].shift(1)), "signal_short"] = 0
        df.loc[(df["close"] < df["lower"]) & (df["close"].shift(1) >= df["lower"].shift(1)), "signal_long"] = 1
        df.loc[(df["close"] > df["median"]) & (df["close"].shift(1) <= df["median"].shift(1)), "signal_long"] = 0
    else:
        df.loc[(df["close"] < df["median"]) & (df["close"].shift(1) >= df["median"].shift(1)), "signal_long"] = 0
        df.loc[(df["close"] > df["upper"]) & (df["close"].shift(1) <= df["upper"].shift(1)), "signal_long"] = 1
        df.loc[(df["close"] > df["median"]) & (df["close"].shift(1) <= df["median"].shift(1)), "signal_short"] = 0
        df.loc[(df["close"] < df["lower"]) & (df["close"].shift(1) >= df["lower"].shift(1)), "signal_short"] = -1

    merge_persistent_signals(df)
    apply_bias_filter(df)
    return dedupe_signal(df)


def highlow_bolling_core(df, n, use_wma=False):
    df["median"] = wma(df["close"], n) if use_wma else df["close"].rolling(n, min_periods=1).mean()
    min_periods = n if use_wma else 1
    df["std"] = (df["high"] - df["low"]).rolling(n, min_periods=min_periods).mean()
    df["z_score"] = (df["close"] - df["median"]).abs() / df["std"].replace(0, np.nan)
    df["m"] = df["z_score"].rolling(n, min_periods=min_periods).mean()
    df["upper"] = df["median"] + df["std"] * df["m"]
    df["lower"] = df["median"] - df["std"] * df["m"]
    df.bfill(inplace=True)
    df.loc[(df["close"] > df["upper"]) & (df["close"].shift(1) <= df["upper"].shift(1)), "signal_long"] = 1
    df.loc[(df["close"] < df["median"]) & (df["close"].shift(1) >= df["median"].shift(1)), "signal_long"] = 0
    df.loc[(df["close"] < df["lower"]) & (df["close"].shift(1) >= df["lower"].shift(1)), "signal_short"] = -1
    df.loc[(df["close"] > df["median"]) & (df["close"].shift(1) <= df["median"].shift(1)), "signal_short"] = 0
    merge_persistent_signals(df)
    return dedupe_signal(df)


def bolling_formatter(df, n, indicator):
    df["median"] = df[indicator].rolling(n, min_periods=1).mean()
    df["std"] = df[indicator].rolling(n, min_periods=1).std(ddof=0)
    df["z_score"] = (df[indicator] - df["median"]).abs() / df["std"].replace(0, np.nan)
    df["m"] = df["z_score"].rolling(n, min_periods=1).mean().shift()
    df["upper"] = df["median"] + df["m"] * df["std"]
    df["lower"] = df["median"] - df["m"] * df["std"]
    df.bfill(inplace=True)
    df["bias"] = df["close"] / (df["median"] + EPS) - 1
    df["bias_pct"] = df["bias"].abs().rolling(n, min_periods=1).max().shift()

    df.loc[(df[indicator] > df["upper"]) & (df[indicator].shift(1) <= df["upper"].shift(1)), "signal_long"] = 1
    df.loc[(df[indicator] < df["median"]) & (df[indicator].shift(1) >= df["median"].shift(1)), "signal_long"] = 0
    df.loc[(df[indicator] < df["lower"]) & (df[indicator].shift(1) >= df["lower"].shift(1)), "signal_short"] = -1
    df.loc[(df[indicator] > df["median"]) & (df[indicator].shift(1) <= df["median"].shift(1)), "signal_short"] = 0
    merge_persistent_signals(df)
    apply_bias_filter(df)
    return dedupe_signal(df)


def mtm_bolling_core(df, n):
    df["mtm"] = (df["close"] / df["close"].shift(n) - 1) * 100
    return bolling_formatter(df, n, "mtm")


def adx_bolling_core(df, n):
    df["_adx"] = adx(df, n)
    df["adx"] = df["_adx"] / df["_adx"].rolling(n, min_periods=1).mean().shift()
    return bolling_formatter(df, n, "adx")


def angle_bolling_core(df, n):
    df["_angle"] = linear_reg_angle(df["close"], n)
    denom = (df["_angle"].rolling(n).max() - df["_angle"].rolling(n).min()).replace(0, np.nan)
    df["angle"] = (df["_angle"] - df["_angle"].rolling(n).min()) / denom
    return bolling_formatter(df, n, "angle")


def amv_bolling_core(df, n):
    df["AMOV"] = df["volume"] * (df["open"] + df["close"]) / 2
    df["AMV1"] = df["AMOV"].rolling(n).sum() / df["volume"].rolling(n).sum().replace(0, np.nan)
    denom = (df["AMV1"].rolling(n).max() - df["AMV1"].rolling(n).min()).replace(0, np.nan)
    df["amv"] = (df["AMV1"] - df["AMV1"].rolling(n).min()) / denom
    return bolling_formatter(df, n, "amv")


def ar_bolling_core(df, n):
    v1 = (df["high"] - df["open"]).rolling(n, min_periods=1).sum()
    v2 = (df["open"] - df["low"]).rolling(n, min_periods=1).sum()
    df["ar"] = 100 * v1 / v2.replace(0, np.nan)
    return bolling_formatter(df, n, "ar")


def atr_bolling_core(df, n):
    df["_ATR"] = atr(df, n)
    middle = df["close"].rolling(n, min_periods=1).mean()
    df["atr_factor"] = df["_ATR"] / (middle + EPS)
    return bolling_formatter(df, n, "atr_factor")


def bbw_bolling_core(df, n):
    median = df["close"].rolling(n, min_periods=1).mean()
    std = df["close"].rolling(n, min_periods=1).std(ddof=0)
    upper = median + std * 2
    lower = median - std * 2
    df["bbw"] = (upper - lower) / (median + EPS)
    return bolling_formatter(df, n, "bbw")


def adaptboll_mtm_v3_core(df, n):
    n2 = 35 * n
    median = df["close"].rolling(n2, min_periods=1).mean()
    std = df["close"].rolling(n2, min_periods=1).std(ddof=0)
    z_score = (df["close"] - median).abs() / std.replace(0, np.nan)
    m = z_score.rolling(n2, min_periods=1).mean()
    condition_long = df["close"] > median + std * m
    condition_short = df["close"] < median - std * m

    df["mtm"] = df["close"] / df["close"].shift(n) - 1
    df["mtm_mean"] = df["mtm"].rolling(n, min_periods=1).mean()
    df["wd_atr"] = atr(df, n) / (df["close"].rolling(n, min_periods=1).mean() + EPS)
    add_mtm_features(df, n)
    indicator = "mtm_mean"
    df[indicator] = df[indicator] * df["mtm_atr"] * df["mtm_atr_mean"] * df["wd_atr"]
    factor_adaptive_bolling(df, n, indicator, condition_long, condition_short)
    return df


def factor_adaptive_bolling(df, n, indicator, condition_long=None, condition_short=None):
    df["median"] = df[indicator].rolling(n, min_periods=1).mean()
    df["std"] = df[indicator].rolling(n, min_periods=1).std(ddof=0)
    df["z_score"] = (df[indicator] - df["median"]).abs() / df["std"].replace(0, np.nan)
    df["m"] = df["z_score"].rolling(n, min_periods=1).min().shift(1)
    df["up"] = df["median"] + df["std"] * df["m"]
    df["dn"] = df["median"] - df["std"] * df["m"]
    df.bfill(inplace=True)
    df.loc[(df[indicator] > df["up"]) & (df[indicator].shift(1) <= df["up"].shift(1)), "signal_long"] = 1
    df.loc[(df[indicator] < df["dn"]) & (df[indicator].shift(1) >= df["dn"].shift(1)), "signal_short"] = -1
    df.loc[(df[indicator] < df["median"]) & (df[indicator].shift(1) >= df["median"].shift(1)), "signal_long"] = 0
    df.loc[(df[indicator] > df["median"]) & (df[indicator].shift(1) <= df["median"].shift(1)), "signal_short"] = 0
    if condition_long is not None:
        df.loc[condition_long, "signal_short"] = 0
    if condition_short is not None:
        df.loc[condition_short, "signal_long"] = 0
    merge_persistent_signals(df)
    return dedupe_signal(df)


def add_mtm_features(df, n):
    df["mtm_l"] = df["low"] / df["low"].shift(n) - 1
    df["mtm_h"] = df["high"] / df["high"].shift(n) - 1
    df["mtm_c"] = df["close"] / df["close"].shift(n) - 1
    df["mtm_c1"] = df["mtm_h"] - df["mtm_l"]
    df["mtm_c2"] = (df["mtm_h"] - df["mtm_c"].shift(1)).abs()
    df["mtm_c3"] = (df["mtm_l"] - df["mtm_c"].shift(1)).abs()
    df["mtm_tr"] = df[["mtm_c1", "mtm_c2", "mtm_c3"]].max(axis=1)
    df["mtm_atr"] = df["mtm_tr"].rolling(n, min_periods=1).mean()
    df["mtm_l_mean"] = df["mtm_l"].rolling(n, min_periods=1).mean()
    df["mtm_h_mean"] = df["mtm_h"].rolling(n, min_periods=1).mean()
    df["mtm_c_mean"] = df["mtm_c"].rolling(n, min_periods=1).mean()
    df["mtm_c1"] = df["mtm_h_mean"] - df["mtm_l_mean"]
    df["mtm_c2"] = (df["mtm_h_mean"] - df["mtm_c_mean"].shift(1)).abs()
    df["mtm_c3"] = (df["mtm_l_mean"] - df["mtm_c_mean"].shift(1)).abs()
    df["mtm_tr"] = df[["mtm_c1", "mtm_c2", "mtm_c3"]].max(axis=1)
    df["mtm_atr_mean"] = df["mtm_tr"].rolling(n, min_periods=1).mean()
    return df


def add_cci_features(df, n):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    ma = tp.rolling(n, min_periods=1).mean()
    md = (df["close"] - ma).abs().rolling(n, min_periods=1).mean()
    cci_c = (tp - ma) / md.replace(0, np.nan) / 0.015
    ma_h = tp.rolling(n, min_periods=1).max()
    md_h = (df["close"] - ma_h).abs().rolling(n, min_periods=1).max()
    cci_h = (tp - ma_h) / md_h.replace(0, np.nan) / 0.015
    ma_l = tp.rolling(n, min_periods=1).min()
    md_l = (df["close"] - ma_l).abs().rolling(n, min_periods=1).min()
    cci_l = (tp - ma_l) / md_l.replace(0, np.nan) / 0.015
    cci_tr = pd.concat(
        [cci_h - cci_l, (cci_h - cci_c.shift(1)).abs(), (cci_l - cci_c.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    df["cci_atr"] = cci_tr.rolling(n, min_periods=1).mean()
    cci_l_mean = cci_l.rolling(n, min_periods=1).mean()
    cci_h_mean = cci_h.rolling(n, min_periods=1).mean()
    cci_c_mean = cci_c.rolling(n, min_periods=1).mean()
    cci_tr_mean = pd.concat(
        [cci_h_mean - cci_l_mean, (cci_h_mean - cci_c_mean.shift(1)).abs(), (cci_l_mean - cci_c_mean.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    df["cci_atr_mean"] = cci_tr_mean.rolling(n, min_periods=1).mean()
    return df


def add_zdf_features(df, n):
    zhf_c = df["close"].pct_change().rolling(n).std()
    zhf_h = df["high"].pct_change().rolling(n).std()
    zhf_l = df["low"].pct_change().rolling(n).std()
    zdf_l_mean = zhf_l.rolling(n, min_periods=1).mean()
    zdf_h_mean = zhf_h.rolling(n, min_periods=1).mean()
    zdf_c_mean = zhf_c.rolling(n, min_periods=1).mean()
    zdf_tr = pd.concat(
        [zdf_h_mean - zdf_l_mean, (zdf_h_mean - zdf_c_mean.shift(1)).abs(), (zdf_l_mean - zdf_c_mean.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    df["zdf_atr_mean"] = zdf_tr.rolling(n, min_periods=1).mean()
    return df


def adaptboll_cci_core(df, n, with_mtm_zdf=False):
    n2 = 35 * n
    median = df["close"].rolling(n2).mean()
    std = df["close"].rolling(n2, min_periods=1).std(ddof=0)
    z_score = (df["close"] - median).abs() / std.replace(0, np.nan)
    m = z_score.rolling(n2).mean()
    condition_long = df["close"] > median + std * m
    condition_short = df["close"] < median - std * m

    add_cci_features(df, n)
    indicator = "cci_atr"
    df[indicator] = df[indicator] * df["cci_atr_mean"]
    if with_mtm_zdf:
        add_mtm_features(df, n)
        add_zdf_features(df, n)
        df[indicator] = df[indicator] * df["mtm_atr"] * df["zdf_atr_mean"]
    return factor_adaptive_bolling(df, n, indicator, condition_long, condition_short)


def mtmbbw_bolling_core(df, n):
    df["diff_c"] = df["close"] / df["close"].shift(n)
    df["median"] = df["close"].rolling(n, min_periods=1).mean()
    df["std"] = df["close"].rolling(n, min_periods=1).std(ddof=0)
    multiplier = df["diff_c"] + df["diff_c"] ** (-1)
    df["upper"] = df["median"] + df["std"] * multiplier
    df["lower"] = df["median"] - df["std"] * multiplier
    df["mouth"] = df["upper"] - df["lower"]
    df["mouth_m"] = df["mouth"].rolling(n).mean()
    df.loc[(df["close"] > df["upper"]) & (df["close"].shift(1) <= df["upper"].shift(1)), "signal_long"] = 1
    df.loc[((df["mouth"] < df["mouth_m"]) & (df["mouth"].shift(1) >= df["mouth_m"].shift(1))) | ((df["close"] < df["median"]) & (df["close"].shift(1) >= df["median"].shift(1))), "signal_long"] = 0
    df.loc[(df["close"] < df["lower"]) & (df["close"].shift(1) >= df["lower"].shift(1)), "signal_short"] = -1
    df.loc[((df["mouth"] < df["mouth_m"]) & (df["mouth"].shift(1) >= df["mouth_m"].shift(1))) | ((df["close"] > df["median"]) & (df["close"].shift(1) <= df["median"].shift(1))), "signal_short"] = 0
    df["signal"] = df[["signal_long", "signal_short"]].sum(axis=1, min_count=1, skipna=True)
    return dedupe_signal(df)


def dc_flash_core(df, n):
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


def default_para_list(n_list=range(10, 300, 10)):
    return [[n] for n in n_list]
