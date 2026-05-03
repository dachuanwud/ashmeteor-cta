from cta_api.function import process_anti_chase_entry_filter
from factors._admin_v3_utils import adaptive_bolling_core, default_para_list, finish_signal, parse_n


def _parse_max_fast_bias(para, default=0.20):
    if isinstance(para, (list, tuple)) and len(para) > 1:
        value = float(para[1])
        return value / 100 if value > 1 else value
    return default


def signal(df, para=[200, 20], proportion=1, leverage_rate=1):
    n = parse_n(para)
    max_fast_bias = _parse_max_fast_bias(para)
    df = adaptive_bolling_core(df, n, reverse=False, bias_filter=True)
    fast_n = max(int(n / 4), 1)
    df["median_fast"] = df["close"].rolling(fast_n, min_periods=1).mean()
    df["fast_bias"] = df["close"] / df["median_fast"] - 1
    df = process_anti_chase_entry_filter(df, midline_col="median_fast", max_fast_bias=max_fast_bias)
    return finish_signal(df, proportion, leverage_rate)


def para_list(n_list=range(10, 1000 + 10, 10)):
    return default_para_list(n_list)
