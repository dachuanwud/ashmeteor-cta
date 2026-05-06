from datetime import datetime

import pandas as pd


def build_cta_key(symbol, interval, cta, period):
    return '_'.join((symbol, interval, cta, period))


def align_cta_run_time(now=None, interval='4h'):
    run_time = now or datetime.now()
    run_time = run_time.replace(second=0, microsecond=0)
    interval = interval or ''
    if 'h' in interval:
        interval_num = int(interval.split('h')[0])
        hour = run_time.hour // interval_num * interval_num
        return run_time.replace(hour=hour, minute=0)
    if 'm' in interval:
        interval_num = int(interval.split('m')[0])
        minute = run_time.minute // interval_num * interval_num
        return run_time.replace(minute=minute)
    return run_time


def merge_closed_kline_history(history, new_kline, run_time, max_rows=10000):
    symbol_data = pd.concat([history, new_kline])
    symbol_data.sort_values(by=['candle_begin_time'], inplace=True)
    symbol_data.drop_duplicates(subset=['candle_begin_time'],
                                keep='last',
                                inplace=True)
    symbol_data = symbol_data[symbol_data['candle_begin_time'] < run_time]
    symbol_data.reset_index(drop=True, inplace=True)
    return symbol_data.iloc[-max_rows:]


def calculate_cta_signal(symbol_data, cta_name, period, factors_module):
    df, *_ = getattr(factors_module, cta_name)(
        symbol_data.copy(), factors_module.parse_cta_period(period))
    return df, df.iloc[-1]['signal']

