from factors._admin_v3_utils import default_para_list, finish_signal, highlow_bolling_core, parse_n


def signal(df, para=[55], proportion=1, leverage_rate=1):
    df = highlow_bolling_core(df, parse_n(para), use_wma=True)
    return finish_signal(df, proportion, leverage_rate)


def para_list(n_list=range(10, 300, 10)):
    return default_para_list(n_list)
