import numpy as np

from cta_api.function import process_stop_loss_close


def signal(df, para=[298, 6], proportion=1, leverage_rate=1):
    """
    Bollinger breakout strategy.

    para[0]: rolling window
    para[1]: standard-deviation multiplier
    """
    n = int(para[0])
    m = float(para[1])

    df["median"] = df["close"].rolling(n, min_periods=1).mean()
    df["std"] = df["close"].rolling(n, min_periods=1).std(ddof=0)
    df["upper"] = df["median"] + m * df["std"]
    df["lower"] = df["median"] - m * df["std"]

    condition1 = df["close"] > df["upper"]
    condition2 = df["close"].shift(1) <= df["upper"].shift(1)
    df.loc[condition1 & condition2, "signal_long"] = 1

    condition1 = df["close"] < df["median"]
    condition2 = df["close"].shift(1) >= df["median"].shift(1)
    df.loc[condition1 & condition2, "signal_long"] = 0

    condition1 = df["close"] < df["lower"]
    condition2 = df["close"].shift(1) >= df["lower"].shift(1)
    df.loc[condition1 & condition2, "signal_short"] = -1

    condition1 = df["close"] > df["median"]
    condition2 = df["close"].shift(1) <= df["median"].shift(1)
    df.loc[condition1 & condition2, "signal_short"] = 0

    df["signal"] = df[["signal_long", "signal_short"]].sum(axis=1, min_count=1, skipna=True)
    temp = df[df["signal"].notnull()][["signal"]]
    temp = temp[temp["signal"] != temp["signal"].shift(1)]
    df["signal"] = temp["signal"]

    df.drop(["median", "std", "upper", "lower", "signal_long", "signal_short"], axis=1, inplace=True)

    df = process_stop_loss_close(df, proportion, leverage_rate=leverage_rate)

    return df


def para_list(n_list=range(2, 500, 2), m_list=None):
    if m_list is None:
        m_list = [i / 10 for i in range(10, 81, 5)]

    return [[n, m] for n in n_list for m in m_list]
