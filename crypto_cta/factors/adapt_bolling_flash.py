from factors._admin_v3_utils import adaptive_bolling_flash_core, default_para_list, finish_signal, parse_n


def signal(df, para=[160], proportion=1, leverage_rate=1):
    df = adaptive_bolling_flash_core(df, parse_n(para))
    return finish_signal(df, proportion, leverage_rate)


def para_list(n_list=range(10, 300, 10)):
    return default_para_list(n_list)
