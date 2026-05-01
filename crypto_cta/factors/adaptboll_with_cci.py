from factors._admin_v3_utils import adaptboll_cci_core, default_para_list, finish_signal, parse_n


def signal(df, para=[55], proportion=1, leverage_rate=1):
    df = adaptboll_cci_core(df, parse_n(para), with_mtm_zdf=False)
    return finish_signal(df, proportion, leverage_rate)


def para_list(n_list=range(10, 200, 10)):
    return default_para_list(n_list)
