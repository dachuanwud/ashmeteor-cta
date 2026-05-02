import pandas as pd
import numpy as np
import talib
import random
import ast

eps = 1e-8


if not hasattr(pd.DataFrame, 'append'):
    def _dataframe_append(self,
                          other,
                          ignore_index=False,
                          verify_integrity=False,
                          sort=False):
        if isinstance(other, dict):
            other = pd.DataFrame([other])
        elif isinstance(other, pd.Series):
            other = other.to_frame().T
        elif isinstance(other, list):
            other = pd.DataFrame(other)
        return pd.concat([self, other],
                         ignore_index=ignore_index,
                         verify_integrity=verify_integrity,
                         sort=sort)

    pd.DataFrame.append = _dataframe_append


pd.set_option('expand_frame_repr', False)
pd.set_option('display.max_rows', 100)  # 最多显示数据的行数


def _coerce_period_value(value):
    value = float(value)
    return int(value) if value.is_integer() else value


def parse_cta_period(period):
    """
    统一解析CTA参数，兼容单参数和二维参数。
    示例：200 -> 200, "200" -> 200, "[200,20]" -> [200, 20], "200,20" -> [200, 20]
    """
    if isinstance(period, (list, tuple)):
        return [_coerce_period_value(value) for value in period]
    if isinstance(period, (int, float, np.integer, np.floating)):
        return _coerce_period_value(period)

    text = str(period).strip()
    if text == '':
        raise ValueError('period不能为空')
    if text.startswith('[') or text.startswith('('):
        parsed = ast.literal_eval(text)
        if not isinstance(parsed, (list, tuple)):
            return _coerce_period_value(parsed)
        return [_coerce_period_value(value) for value in parsed]
    if ',' in text:
        return [_coerce_period_value(value.strip()) for value in text.split(',') if value.strip()]
    return _coerce_period_value(text)


def format_cta_period(period):
    parsed = parse_cta_period(period)
    if isinstance(parsed, list):
        return '[' + ','.join(str(value) for value in parsed) + ']'
    return str(parsed)


def generate_signal_data(df):
    # 画买卖点
    df['ctime'] = df['candle_begin_time'].apply(str)
    signal_data = df[~np.isnan(df['signal'])][['ctime', 'high', 'signal']]

    def get_act(x):  # 通过signal判断仓位方向
        if x > 0:
            return {'formatter': '多'}
        elif x < 0:
            return {'formatter': '空'}
        else:
            return {'formatter': '平'}

    def set_color(x):  # 设置不同操作的颜色
        if x > 0:
            return {'color': 'rgb(214,18,165)'}
        elif x < 0:
            return {'color': 'rgb(0,0,255)'}
        else:
            return {'color': 'rgb(224,136,11)'}

    signal_data['label'] = np.vectorize(get_act)(signal_data['signal'])
    signal_data['itemStyle'] = np.vectorize(set_color)(signal_data['signal'])
    del signal_data['signal']
    signal_data.columns = ['xAxis', 'yAxis', 'label', 'itemStyle']
    signal_data = signal_data.to_dict('records')
    return signal_data


def process_anti_chase_entry_filter(df,
                                    midline_col='median_fast',
                                    max_fast_bias=0.20):
    df['anti_chase_block_trigger'] = False
    effective_position = 0

    for i in df.index:
        raw_signal = df.loc[i, 'signal']
        if pd.isna(raw_signal):
            continue

        signal = int(raw_signal)
        if signal == 0:
            effective_position = 0
            continue

        if signal == effective_position:
            continue

        midline = df.loc[i, midline_col]
        if pd.isna(midline) or midline == 0:
            effective_position = signal
            continue

        fast_bias = df.loc[i, 'close'] / midline - 1
        chase_condition = ((signal == 1 and fast_bias > max_fast_bias) or
                           (signal == -1 and fast_bias < -max_fast_bias))
        if chase_condition:
            df.at[i, 'signal'] = 0
            df.at[i, 'anti_chase_block_trigger'] = True
            effective_position = 0
        else:
            effective_position = signal

    return df


# 随机生成交易信号
def real_signal_random(*args):
    """
    随机发出交易信号
    :param df:
    :param now_pos:
    :param avg_price:
    :param para:
    :return:
    """
    r = random.random()
    if r <= 0.25:
        return 1
    elif r <= 0.5:
        return 0
    elif r <= 0.75:
        return -1
    else:
        return None


def ema(*args):
    df = args[0]
    n = args[1]
    df['ema'] = df['close'].ewm(n, adjust=False).mean()

    condition1 = df['close'] > df['ema']
    condition2 = df['close'].shift(1) <= df['ema'].shift(1)
    df.loc[condition1 & condition2, 'signal'] = 1

    condition1 = df['close'] < df['ema']
    condition2 = df['close'].shift(1) >= df['ema'].shift(1)
    df.loc[condition1 & condition2, 'signal'] = -1

    signal_data = generate_signal_data(df)
    return df, df['ema'].tolist(), signal_data


def ema_pro(*args):
    df = args[0]
    n = args[1]
    df['ema'] = df['close'].ewm(span=n, adjust=False).mean()

    condition1 = df['close'] > df['ema']
    condition2 = df['close'].shift(1) <= df['ema'].shift(1)
    df.loc[condition1 & condition2, 'signal'] = 1

    condition1 = df['close'] < df['ema']
    condition2 = df['close'].shift(1) >= df['ema'].shift(1)
    df.loc[condition1 & condition2, 'signal'] = -1

    signal_data = generate_signal_data(df)
    return df, df['ema'].tolist(), signal_data


# ema大周期过滤策略
def ema_multi(*args):
    df = args[0]
    n = args[1]

    df['ema'] = df['close'].ewm(n, adjust=False).mean()
    df['ema_2x'] = df['close'].ewm(2 * n, adjust=False).mean()
    df['ema_4x'] = df['close'].ewm(4 * n, adjust=False).mean()
    df['ema_8x'] = df['close'].ewm(8 * n, adjust=False).mean()

    # 做多开仓条件
    condition1 = df['ema'] > df['ema_2x']
    condition2 = df['ema_2x'] > df['ema_4x']
    condition3 = df['ema_4x'] > df['ema_8x']
    df.loc[condition1 & condition2 & condition3, 'signal'] = 1

    # # 做多平仓条件
    # condition1 = df['close'] < df['ema_8x']
    # condition2 = df['close'].shift(1) >= df['ema_8x'].shift(1)
    # df.loc[condition1 & condition2, 'signal'] = 0

    # 做空开仓条件
    condition1 = df['ema'] <= df['ema_2x']
    condition2 = df['ema_2x'] <= df['ema_4x']
    condition3 = df['ema_4x'] <= df['ema_8x']
    df.loc[condition1 & condition2 & condition3, 'signal'] = -1

    # # 做空平仓条件
    # condition1 = df['close'] > df['ema_8x']
    # condition2 = df['close'].shift(1) <= df['ema_8x'].shift(1)
    # df.loc[condition1 & condition2, 'signal'] = 0

    df['signal'].fillna(method='ffill', inplace=True)
    # ===将signal中的重复值删除
    temp = df[['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp

    signal_data = generate_signal_data(df)
    # signal_data = []
    return df, df['ema'].tolist(), df['ema_2x'].tolist(), df['ema_4x'].tolist(
    ), df['ema_8x'].tolist(), signal_data


def simple_two_mean_close(*args):
    df = args[0]
    n = args[1]

    # ===计算指标区域
    # 我们默认长线参数为短线的2倍来达成一个参数的策略
    df['short_mean'] = df['close'].rolling(n, min_periods=1).mean()
    df['long_mean'] = df['close'].rolling(2 * n, min_periods=1).mean()

    # ===计算策略信号区域
    # 找出做多信号
    condition1 = df['short_mean'] > df['long_mean']
    condition2 = df['short_mean'].shift(1) <= df['long_mean'].shift(1)
    df.loc[condition1 & condition2,
    'signal'] = 1

    # 找出做空信号
    condition1 = df['short_mean'] < df['long_mean']
    condition2 = df['short_mean'].shift(1) >= df['long_mean'].shift(1)
    df.loc[condition1 & condition2,
    'signal'] = -1

    df['signal'].fillna(method='ffill', inplace=True)
    # ===将signal中的重复值删除
    temp = df[['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp

    signal_data = generate_signal_data(df)
    return df, df['short_mean'].tolist(), df['long_mean'].tolist(), signal_data


def adapt_bolling(*args):
    df = args[0]
    n = args[1]

    # 使用自适应 m
    df['median'] = df['close'].rolling(n, min_periods=1).mean()
    df['std'] = df['close'].rolling(n,
                                    min_periods=1).std(ddof=0)  # ddof代表标准差自由度
    df['z_score'] = abs(df['close'] - df['median']) / df['std']
    # df['m'] = df['z_score'].rolling(window=n).max().shift()
    # df['m'] = df['z_score'].rolling(window=n).min().shift()
    df['m'] = df['z_score'].rolling(n, min_periods=1).mean().shift()

    # ===计算指标
    # 计算均线
    # 计算上轨、下轨道
    df['upper'] = df['median'] + df['m'] * df['std']
    df['lower'] = df['median'] - df['m'] * df['std']

    df.fillna(method='backfill', inplace=True)

    # 计算bias
    df['bias'] = df['close'] / df['median'] - 1

    # bias_pct 自适应
    df['bias_pct'] = abs(df['bias']).rolling(window=n,
                                             min_periods=1).max().shift()

    # ===计算原始布林策略信号
    # 找出做多信号
    condition1 = df['close'] > df['upper']  # 当前K线的收盘价 > 上轨
    condition2 = df['close'].shift(1) <= df['upper'].shift(1)  # 之前K线的收盘价 <= 上轨
    df.loc[condition1 & condition2,
           'signal_long'] = 1  # 将产生做多信号的那根K线的signal设置为1，1代表做多

    # 找出做多平仓信号
    condition1 = df['close'] < df['median']  # 当前K线的收盘价 < 中轨
    condition2 = df['close'].shift(1) >= df['median'].shift(
        1)  # 之前K线的收盘价 >= 中轨
    df.loc[condition1 & condition2,
           'signal_long'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # 找出做空信号
    condition1 = df['close'] < df['lower']  # 当前K线的收盘价 < 下轨
    condition2 = df['close'].shift(1) >= df['lower'].shift(1)  # 之前K线的收盘价 >= 下轨
    df.loc[condition1 & condition2,
           'signal_short'] = -1  # 将产生做空信号的那根K线的signal设置为-1，-1代表做空

    # 找出做空平仓信号
    condition1 = df['close'] > df['median']  # 当前K线的收盘价 > 中轨
    condition2 = df['close'].shift(1) <= df['median'].shift(
        1)  # 之前K线的收盘价 <= 中轨
    df.loc[condition1 & condition2,
           'signal_short'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # ===将long和short合并为signal
    df['signal_short'].fillna(method='ffill', inplace=True)
    df['signal_long'].fillna(method='ffill', inplace=True)
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1)
    df['signal'].fillna(value=0, inplace=True)
    df['raw_signal'] = df['signal']

    # ===根据bias，修改开仓时间
    df['temp'] = df['signal']

    # 将原始信号做多时，当bias大于阀值，设置为空
    condition1 = (df['signal'] == 1)
    condition2 = (df['bias'] > df['bias_pct'])
    df.loc[condition1 & condition2, 'temp'] = None

    # 将原始信号做空时，当bias大于阀值，设置为空
    condition1 = (df['signal'] == -1)
    condition2 = (df['bias'] < -df['bias_pct'])
    df.loc[condition1 & condition2, 'temp'] = None

    # 原始信号刚开仓，并且大于阀值，将信号设置为0
    condition1 = (df['signal'] != df['signal'].shift(1))
    condition2 = (df['temp'].isnull())
    df.loc[condition1 & condition2, 'temp'] = 0

    # 使用之前的信号补全原始信号
    df['temp'].fillna(method='ffill', inplace=True)
    df['signal'] = df['temp']

    # ===将signal中的重复值删除
    temp = df[['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp

    df.drop(
        ['raw_signal', 'std', 'bias', 'temp', 'signal_long', 'signal_short'],
        axis=1,
        inplace=True)

    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
    ), signal_data


def adapt_bolling_anti_chase(*args):
    df = args[0]
    para = parse_cta_period(args[1] if len(args) > 1 else [200, 20])
    if isinstance(para, list):
        n = int(para[0])
        if len(para) > 1:
            max_fast_bias = float(para[1]) / 100 if float(para[1]) > 1 else float(para[1])
        else:
            max_fast_bias = 0.20
    else:
        n = int(para)
        max_fast_bias = 0.20

    df, median, upper, lower, _ = adapt_bolling(df, n)
    fast_n = max(int(n / 4), 1)
    df['median_fast'] = df['close'].rolling(fast_n, min_periods=1).mean()
    df['fast_bias'] = df['close'] / df['median_fast'] - 1
    df = process_anti_chase_entry_filter(df,
                                         midline_col='median_fast',
                                         max_fast_bias=max_fast_bias)

    signal_data = generate_signal_data(df)
    return df, median, upper, lower, signal_data


def signal_atrbolling_bias(*args):
    df = args[0]
    n = args[1]

    #----计算atr和std
    df['atr'] = talib.ATR(df['high'], df['low'], df['close'], n)
    df['std'] = df['close'].rolling(window=n, min_periods=1).std(ddof=0)

    #-----计算中轨以及atr和std的倍数

    #---中轨
    close = [float(x) for x in df['close']]
    # df['median'] = talib.WMA(np.array(close), timeperiod=n)
    df['median'] = df['close'].rolling(window=n, min_periods=1).mean()

    #---atr，std倍数
    df['atr_J神'] = abs(df['close'] - df['median']) / df['atr']
    df['m_atr'] = df['atr_J神'].rolling(window=n, min_periods=1).max().shift(1)
    df['boll_J神'] = abs(df['close'] - df['median']) / df['std']
    df['m_boll'] = df['boll_J神'].rolling(window=n,
                                         min_periods=1).max().shift(1)

    #---分别计算atr，布林通道上下轨
    df['upper_atr'] = df['median'] + df['m_atr'] * df['atr']
    df['lower_atr'] = df['median'] - df['m_atr'] * df['atr']

    df['upper_boll'] = df['median'] + df['m_boll'] * df['std']
    df['lower_boll'] = df['median'] - df['m_boll'] * df['std']

    #----将两个上下轨揉在一起。取MIN开仓太频繁，取MAX开仓太少，最终取mean
    df['upper'] = df[['upper_atr', 'upper_boll']].mean(axis=1)
    df['lower'] = df[['lower_atr', 'lower_boll']].mean(axis=1)

    df.fillna(method='backfill', inplace=True)

    # 计算bias
    df['bias'] = df['close'] / df['median'] - 1
    # bias_pct 自适应
    df['bias_pct'] = abs(df['bias']).rolling(window=n,
                                             min_periods=1).max().shift()

    #-----计算开仓

    condition1 = df['close'] < df['median']  # 当前K线的收盘价 < 中轨
    condition2 = df['close'].shift(1) >= df['median'].shift(
        1)  # 之前K线的收盘价 >= 中轨
    df.loc[condition1 & condition2,
           'signal_long'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # ===找出做多信号
    condition1 = df['close'] > df['upper']  # 当前K线的收盘价 > 上轨
    condition2 = df['close'].shift(1) <= df['upper'].shift(1)  # 之前K线的收盘价 <= 上轨
    df.loc[condition1 & condition2,
           'signal_long'] = 1  # 将产生做多信号的那根K线的signal设置为1，1代表做多

    # ===找出做空平仓信号
    condition1 = df['close'] > df['median']  # 当前K线的收盘价 > 中轨
    condition2 = df['close'].shift(1) <= df['median'].shift(
        1)  # 之前K线的收盘价 <= 中轨
    df.loc[condition1 & condition2,
           'signal_short'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # ===找出做空信号
    condition1 = df['close'] < df['lower']  # 当前K线的收盘价 < 下轨
    condition2 = df['close'].shift(1) >= df['lower'].shift(1)  # 之前K线的收盘价 >= 下轨
    df.loc[condition1 & condition2,
           'signal_short'] = -1  # 将产生做空信号的那根K线的signal设置为-1，-1代表做空

    # 合并做多做空信号，去除重复信号
    df['signal_short'].fillna(method='ffill', inplace=True)
    df['signal_long'].fillna(method='ffill', inplace=True)
    df['signal'] = df[['signal_long', 'signal_short'
                       ]].sum(axis=1, min_count=1,
                              skipna=True)  # 若你的pandas版本是最新的，请使用本行代码代替上面一行
    df['signal'].fillna(value=0, inplace=True)

    # ===根据bias，修改开仓时间
    df['temp'] = df['signal']

    # 将原始信号做多时，当bias大于阀值，设置为空
    condition1 = (df['signal'] == 1)
    condition2 = (df['bias'] > df['bias_pct'])
    df.loc[condition1 & condition2, 'temp'] = None

    # 将原始信号做空时，当bias大于阀值，设置为空
    condition1 = (df['signal'] == -1)
    condition2 = (df['bias'] < -df['bias_pct'])
    df.loc[condition1 & condition2, 'temp'] = None

    # 原始信号刚开仓，并且大于阀值，将信号设置为0
    condition1 = (df['signal'] != df['signal'].shift(1))
    condition2 = (df['temp'].isnull())
    df.loc[condition1 & condition2, 'temp'] = 0

    # 使用之前的信号补全原始信号
    df['temp'].fillna(method='ffill', inplace=True)
    df['signal'] = df['temp']

    temp = df[['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp

    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
    ), signal_data


def signal_atrbolling_bias_wma(*args):
    df = args[0]
    n = args[1]
    #----计算atr和std
    df['atr'] = talib.ATR(df['high'], df['low'], df['close'], n)
    df['std'] = df['close'].rolling(window=n).std(ddof=0)

    #-----计算中轨以及atr和std的倍数

    #---中轨
    close = [float(x) for x in df['close']]
    df['median'] = talib.WMA(np.array(close), timeperiod=n)
    # df['median'] = df['close'].rolling(window=n).mean()

    #---atr，std倍数
    df['atr_J神'] = abs(df['close'] - df['median']) / df['atr']
    df['m_atr'] = df['atr_J神'].rolling(window=n).max().shift(1)
    df['boll_J神'] = abs(df['close'] - df['median']) / df['std']
    df['m_boll'] = df['boll_J神'].rolling(window=n).max().shift(1)

    #---分别计算atr，布林通道上下轨
    df['upper_atr'] = df['median'] + df['m_atr'] * df['atr']
    df['lower_atr'] = df['median'] - df['m_atr'] * df['atr']

    df['upper_boll'] = df['median'] + df['m_boll'] * df['std']
    df['lower_boll'] = df['median'] - df['m_boll'] * df['std']

    #----将两个上下轨揉在一起。取MIN开仓太频繁，取MAX开仓太少，最终取mean
    df['upper'] = df[['upper_atr', 'upper_boll']].mean(axis=1)
    df['lower'] = df[['lower_atr', 'lower_boll']].mean(axis=1)

    # 计算bias
    df['bias'] = df['close'] / df['median'] - 1
    # bias_pct 自适应
    df['bias_pct'] = abs(df['bias']).rolling(window=n).max().shift()

    #-----计算开仓

    condition1 = df['close'] < df['median']  # 当前K线的收盘价 < 中轨
    condition2 = df['close'].shift(1) >= df['median'].shift(
        1)  # 之前K线的收盘价 >= 中轨
    df.loc[condition1 & condition2,
           'signal_long'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # ===找出做多信号
    condition1 = df['close'] > df['upper']  # 当前K线的收盘价 > 上轨
    condition2 = df['close'].shift(1) <= df['upper'].shift(1)  # 之前K线的收盘价 <= 上轨
    df.loc[condition1 & condition2,
           'signal_long'] = 1  # 将产生做多信号的那根K线的signal设置为1，1代表做多

    # ===找出做空平仓信号
    condition1 = df['close'] > df['median']  # 当前K线的收盘价 > 中轨
    condition2 = df['close'].shift(1) <= df['median'].shift(
        1)  # 之前K线的收盘价 <= 中轨
    df.loc[condition1 & condition2,
           'signal_short'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # ===找出做空信号
    condition1 = df['close'] < df['lower']  # 当前K线的收盘价 < 下轨
    condition2 = df['close'].shift(1) >= df['lower'].shift(1)  # 之前K线的收盘价 >= 下轨
    df.loc[condition1 & condition2,
           'signal_short'] = -1  # 将产生做空信号的那根K线的signal设置为-1，-1代表做空

    # 合并做多做空信号，去除重复信号
    df['signal_short'].fillna(method='ffill', inplace=True)
    df['signal_long'].fillna(method='ffill', inplace=True)
    df['signal'] = df[['signal_long', 'signal_short'
                       ]].sum(axis=1, min_count=1,
                              skipna=True)  # 若你的pandas版本是最新的，请使用本行代码代替上面一行
    df['signal'].fillna(value=0, inplace=True)

    # ===根据bias，修改开仓时间
    df['temp'] = df['signal']

    # 将原始信号做多时，当bias大于阀值，设置为空
    condition1 = (df['signal'] == 1)
    condition2 = (df['bias'] > df['bias_pct'])
    df.loc[condition1 & condition2, 'temp'] = None

    # 将原始信号做空时，当bias大于阀值，设置为空
    condition1 = (df['signal'] == -1)
    condition2 = (df['bias'] < -df['bias_pct'])
    df.loc[condition1 & condition2, 'temp'] = None

    # 原始信号刚开仓，并且大于阀值，将信号设置为0
    condition1 = (df['signal'] != df['signal'].shift(1))
    condition2 = (df['temp'].isnull())
    df.loc[condition1 & condition2, 'temp'] = 0

    # 使用之前的信号补全原始信号
    df['temp'].fillna(method='ffill', inplace=True)
    df['signal'] = df['temp']

    temp = df[['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp
    # 将无关的变量删除
    df.drop(['signal_long', 'signal_short'], axis=1, inplace=True)
    df['median'].fillna(method='bfill', inplace=True)
    df['upper'].fillna(method='bfill', inplace=True)
    df['lower'].fillna(method='bfill', inplace=True)

    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
    ), signal_data


def adaptboll_with_mtm_v3(*args):
    df = args[0]
    n1 = args[1]
    n2 = 35 * n1
    df['median'] = df['close'].rolling(window=n2, min_periods=1).mean()
    df['std'] = df['close'].rolling(n2,
                                    min_periods=1).std(ddof=0)  # ddof代表标准差自由度
    df['z_score'] = abs(df['close'] - df['median']) / df['std']
    df['m'] = df['z_score'].rolling(window=n2, min_periods=1).mean()
    df['upper'] = df['median'] + df['std'] * df['m']
    df['lower'] = df['median'] - df['std'] * df['m']

    condition_long = df['close'] > df['upper']
    condition_short = df['close'] < df['lower']

    df['mtm'] = df['close'] / df['close'].shift(n1) - 1
    df['mtm_mean'] = df['mtm'].rolling(window=n1, min_periods=1).mean()

    # 基于价格atr，计算波动率因子wd_atr
    df['c1'] = df['high'] - df['low']
    df['c2'] = abs(df['high'] - df['close'].shift(1))
    df['c3'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['c1', 'c2', 'c3']].max(axis=1)
    df['atr'] = df['tr'].rolling(window=n1, min_periods=1).mean()
    df['avg_price'] = df['close'].rolling(window=n1, min_periods=1).mean()
    df['wd_atr'] = df['atr'] / df['avg_price']

    # 参考ATR，对MTM指标，计算波动率因子
    df['mtm_l'] = df['low'] / df['low'].shift(n1) - 1
    df['mtm_h'] = df['high'] / df['high'].shift(n1) - 1
    df['mtm_c'] = df['close'] / df['close'].shift(n1) - 1
    df['mtm_c1'] = df['mtm_h'] - df['mtm_l']
    df['mtm_c2'] = abs(df['mtm_h'] - df['mtm_c'].shift(1))
    df['mtm_c3'] = abs(df['mtm_l'] - df['mtm_c'].shift(1))
    df['mtm_tr'] = df[['mtm_c1', 'mtm_c2', 'mtm_c3']].max(axis=1)
    df['mtm_atr'] = df['mtm_tr'].rolling(window=n1, min_periods=1).mean()

    # 参考ATR，对MTM mean指标，计算波动率因子
    df['mtm_l_mean'] = df['mtm_l'].rolling(window=n1, min_periods=1).mean()
    df['mtm_h_mean'] = df['mtm_h'].rolling(window=n1, min_periods=1).mean()
    df['mtm_c_mean'] = df['mtm_c'].rolling(window=n1, min_periods=1).mean()
    df['mtm_c1'] = df['mtm_h_mean'] - df['mtm_l_mean']
    df['mtm_c2'] = abs(df['mtm_h_mean'] - df['mtm_c_mean'].shift(1))
    df['mtm_c3'] = abs(df['mtm_l_mean'] - df['mtm_c_mean'].shift(1))
    df['mtm_tr'] = df[['mtm_c1', 'mtm_c2', 'mtm_c3']].max(axis=1)
    df['mtm_atr_mean'] = df['mtm_tr'].rolling(window=n1, min_periods=1).mean()

    indicator = 'mtm_mean'

    # mtm_mean指标分别乘以三个波动率因子
    df[indicator] = df[indicator] * df['mtm_atr']
    df[indicator] = df[indicator] * df['mtm_atr_mean']
    df[indicator] = df[indicator] * df['wd_atr']

    # 对新策略因子计算自适应布林
    df['median'] = df[indicator].rolling(window=n1, min_periods=1).mean()
    df['std'] = df[indicator].rolling(n1, min_periods=1).std(
        ddof=0)  # ddof代表标准差自由度
    df['z_score'] = abs(df[indicator] - df['median']) / df['std']
    # df['m'] = df['z_score'].rolling(window=n1).max().shift(1)
    # df['m'] = df['z_score'].rolling(window=n1).mean()
    df['m'] = df['z_score'].rolling(window=n1, min_periods=1).min().shift(1)
    df['up'] = df['median'] + df['std'] * df['m']
    df['dn'] = df['median'] - df['std'] * df['m']

    df.fillna(method='backfill', inplace=True)

    # 突破上轨做多
    condition1 = df[indicator] > df['up']
    condition2 = df[indicator].shift(1) <= df['up'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_long'] = 1

    # 突破下轨做空
    condition1 = df[indicator] < df['dn']
    condition2 = df[indicator].shift(1) >= df['dn'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_short'] = -1

    # 均线平仓(多头持仓)
    condition1 = df[indicator] < df['median']
    condition2 = df[indicator].shift(1) >= df['median'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_long'] = 0

    # 均线平仓(空头持仓)
    condition1 = df[indicator] > df['median']
    condition2 = df[indicator].shift(1) <= df['median'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_short'] = 0

    df.loc[condition_long, 'signal_short'] = 0
    df.loc[condition_short, 'signal_long'] = 0

    # ===由signal计算出实际的每天持有仓位
    # signal的计算运用了收盘价，是每根K线收盘之后产生的信号，到第二根开盘的时候才买入，仓位才会改变。
    df['signal_short'].fillna(method='ffill', inplace=True)
    df['signal_long'].fillna(method='ffill', inplace=True)
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1)
    df['signal'].fillna(value=0, inplace=True)
    # df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1, min_count=1,
    #                                                        skipna=True)  # 若你的pandas版本是最新的，请使用本行代码代替上面一行
    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    df.drop(['signal_long', 'signal_short', 'atr', 'z_score'],
            axis=1,
            inplace=True)

    signal_data = generate_signal_data(df)

    return df, signal_data


def signal_simple_turtle(*args):
    """
    今天收盘价突破过去20天中的收盘价和开盘价中的最高价，做多。今天收盘价突破过去10天中的收盘价的最低价，平仓。
    今天收盘价突破过去20天中的收盘价和开盘价中的的最低价，做空。今天收盘价突破过去10天中的收盘价的最高价，平仓。
    :param para: [参数1, 参数2]
    :param df:
    :return:
    """
    df = args[0]
    n = args[1]

    df['open_close_high'] = df[['open', 'close']].max(axis=1)
    df['open_close_low'] = df[['open', 'close']].min(axis=1)
    # 最近n1日的最高价、最低价
    df['n_high'] = df['open_close_high'].rolling(n, min_periods=1).max()
    df['n_low'] = df['open_close_low'].rolling(n, min_periods=1).min()
    # # 最近n2日的最高价、最低价
    # df['n2_high'] = df['open_close_high'].rolling(n2, min_periods=1).max()
    # df['n2_low'] = df['open_close_low'].rolling(n2, min_periods=1).min()

    # #计算bbi
    # df["ma_low"] = df['open_close_low'].rolling(n1, min_periods=1).mean()
    # df['bbi_low'] = df['ma_low'].rolling(window=n1).mean()

    # df["ma_high"] = df['open_close_high'].rolling(n1, min_periods=1).mean()
    # df['bbi_high'] = df['ma_high'].rolling(window=n1).mean()

    # # dema平仓
    # close = [float(x) for x in df['close']]
    # df['median'] = talib.DEMA(np.array(close), timeperiod=n)

    # ema平仓
    df['median'] = df['close'].ewm(n, adjust=False).mean()
    df.fillna(method='backfill', inplace=True)
    # df['medianstd'] = talib.WMA(np.array(close), timeperiod=n1)
    # df['emastd'] = talib.EMA(np.array(close), timeperiod=n1)

    #dmacd
    # ===找出做多信号
    # 当天的收盘价 > n1日的最高价，做多
    condition = (df['close'] > df['n_high'].shift(1))
    # 将买入信号当天的signal设置为1
    df.loc[condition, 'signal_long'] = 1
    # ===找出做多平仓
    # 当天的收盘价 < n2日的最低价，多单平仓
    # condition = (df['close'] < df['n2_low'].shift(1))

    # # 将卖出信号当天的signal设置为0
    # df.loc[condition, 'signal_long'] = 0

    # 找出做多平仓信号， 触发条件为 穿中轨 或 回撤超过阈值 二者之一
    condition_sell = (df['close'] < df['median']) & (
        df['close'].shift() >= df['median'].shift())  # k线下穿中轨
    df.loc[condition_sell, 'signal_long'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # ===找出做空信号
    # 当天的收盘价 < n1日的最低价，做空
    condition = (df['close'] < df['n_low'].shift(1))
    df.loc[condition, 'signal_short'] = -1
    # ===找出做空平仓
    # 当天的收盘价 > n2日的最高价，做空平仓
    # condition = (df['close'] > df['n2_high'].shift(1))

    # # 将卖出信号当天的signal设置为0
    # df.loc[condition, 'signal_short'] = 0

    condition_cover = (df['close'] > df['median']) & (
        df['close'].shift() <= df['median'].shift())  # K线上穿中轨
    df.loc[condition_cover, 'signal_short'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # 合并做多做空信号，去除重复信号
    df['signal'] = df[['signal_long', 'signal_short'
                       ]].sum(axis=1, min_count=1,
                              skipna=True)  # 若你的pandas版本是最新的，请使用本行代码代替上面一行
    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    # 将无关的变量删除
    df.drop(
        ['signal_long', 'signal_short', 'open_close_high', 'open_close_low'],
        axis=1,
        inplace=True)
    df['median'].fillna(method='bfill', inplace=True)
    df['n_high'].fillna(method='bfill', inplace=True)
    df['n_low'].fillna(method='bfill', inplace=True)

    signal_data = generate_signal_data(df)

    return df, df['median'].tolist(), df['n_high'].tolist(
    ), df['n_low'].tolist(), signal_data


def signal_simple_turtle_dema(*args):
    """
    今天收盘价突破过去20天中的收盘价和开盘价中的最高价，做多。今天收盘价突破过去10天中的收盘价的最低价，平仓。
    今天收盘价突破过去20天中的收盘价和开盘价中的的最低价，做空。今天收盘价突破过去10天中的收盘价的最高价，平仓。
    :param para: [参数1, 参数2]
    :param df:
    :return:
    """
    df = args[0]
    n = int(args[1])

    df['open_close_high'] = df[['open', 'close']].max(axis=1)
    df['open_close_low'] = df[['open', 'close']].min(axis=1)
    # 最近n1日的最高价、最低价
    df['n_high'] = df['open_close_high'].rolling(n, min_periods=1).max()
    df['n_low'] = df['open_close_low'].rolling(n, min_periods=1).min()
    # # 最近n2日的最高价、最低价
    # df['n2_high'] = df['open_close_high'].rolling(n2, min_periods=1).max()
    # df['n2_low'] = df['open_close_low'].rolling(n2, min_periods=1).min()

    # #计算bbi
    # df["ma_low"] = df['open_close_low'].rolling(n1, min_periods=1).mean()
    # df['bbi_low'] = df['ma_low'].rolling(window=n1).mean()

    # df["ma_high"] = df['open_close_high'].rolling(n1, min_periods=1).mean()
    # df['bbi_high'] = df['ma_high'].rolling(window=n1).mean()
    close = [float(x) for x in df['close']]
    df['median'] = talib.DEMA(np.array(close), timeperiod=n)
    # df['medianstd'] = talib.WMA(np.array(close), timeperiod=n1)
    # df['emastd'] = talib.EMA(np.array(close), timeperiod=n1)

    #dmacd
    # ===找出做多信号
    # 当天的收盘价 > n1日的最高价，做多
    condition = (df['close'] > df['n_high'].shift(1))
    # 将买入信号当天的signal设置为1
    df.loc[condition, 'signal_long'] = 1
    # ===找出做多平仓
    # 当天的收盘价 < n2日的最低价，多单平仓
    # condition = (df['close'] < df['n2_low'].shift(1))

    # # 将卖出信号当天的signal设置为0
    # df.loc[condition, 'signal_long'] = 0

    # 找出做多平仓信号， 触发条件为 穿中轨 或 回撤超过阈值 二者之一
    condition_sell = (df['close'] < df['median']) & (
        df['close'].shift() >= df['median'].shift())  # k线下穿中轨
    df.loc[condition_sell, 'signal_long'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # ===找出做空信号
    # 当天的收盘价 < n1日的最低价，做空
    condition = (df['close'] < df['n_low'].shift(1))
    df.loc[condition, 'signal_short'] = -1
    # ===找出做空平仓
    # 当天的收盘价 > n2日的最高价，做空平仓
    # condition = (df['close'] > df['n2_high'].shift(1))

    # # 将卖出信号当天的signal设置为0
    # df.loc[condition, 'signal_short'] = 0

    condition_cover = (df['close'] > df['median']) & (
        df['close'].shift() <= df['median'].shift())  # K线上穿中轨
    df.loc[condition_cover, 'signal_short'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # 合并做多做空信号，去除重复信号
    df['signal'] = df[['signal_long', 'signal_short'
                       ]].sum(axis=1, min_count=1,
                              skipna=True)  # 若你的pandas版本是最新的，请使用本行代码代替上面一行
    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    # 将无关的变量删除
    df.drop(
        ['signal_long', 'signal_short', 'open_close_high', 'open_close_low'],
        axis=1,
        inplace=True)
    df['median'].fillna(method='bfill', inplace=True)
    df['n_high'].fillna(method='bfill', inplace=True)
    df['n_low'].fillna(method='bfill', inplace=True)
    signal_data = generate_signal_data(df)

    return df, df['median'].tolist(), df['n_high'].tolist(
    ), df['n_low'].tolist(), signal_data


def signal_simple_turtle_wma(*args):
    """
    今天收盘价突破过去20天中的收盘价和开盘价中的最高价，做多。今天收盘价突破过去10天中的收盘价的最低价，平仓。
    今天收盘价突破过去20天中的收盘价和开盘价中的的最低价，做空。今天收盘价突破过去10天中的收盘价的最高价，平仓。
    :param para: [参数1, 参数2]
    :param df:
    :return:
    """
    df = args[0]
    n = int(args[1])

    df['open_close_high'] = df[['open', 'close']].max(axis=1)
    df['open_close_low'] = df[['open', 'close']].min(axis=1)
    # 最近n1日的最高价、最低价
    df['n_high'] = df['open_close_high'].rolling(n, min_periods=1).max()
    df['n_low'] = df['open_close_low'].rolling(n, min_periods=1).min()
    # # 最近n2日的最高价、最低价
    # df['n2_high'] = df['open_close_high'].rolling(n2, min_periods=1).max()
    # df['n2_low'] = df['open_close_low'].rolling(n2, min_periods=1).min()

    # #计算bbi
    # df["ma_low"] = df['open_close_low'].rolling(n1, min_periods=1).mean()
    # df['bbi_low'] = df['ma_low'].rolling(window=n1).mean()

    # df["ma_high"] = df['open_close_high'].rolling(n1, min_periods=1).mean()
    # df['bbi_high'] = df['ma_high'].rolling(window=n1).mean()
    close = [float(x) for x in df['close']]
    df['median'] = talib.WMA(np.array(close), timeperiod=n)
    # df['medianstd'] = talib.WMA(np.array(close), timeperiod=n1)
    # df['emastd'] = talib.EMA(np.array(close), timeperiod=n1)

    #dmacd
    # ===找出做多信号
    # 当天的收盘价 > n1日的最高价，做多
    condition = (df['close'] > df['n_high'].shift(1))
    # 将买入信号当天的signal设置为1
    df.loc[condition, 'signal_long'] = 1
    # ===找出做多平仓
    # 当天的收盘价 < n2日的最低价，多单平仓
    # condition = (df['close'] < df['n2_low'].shift(1))

    # # 将卖出信号当天的signal设置为0
    # df.loc[condition, 'signal_long'] = 0

    # 找出做多平仓信号， 触发条件为 穿中轨 或 回撤超过阈值 二者之一
    condition_sell = (df['close'] < df['median']) & (
        df['close'].shift() >= df['median'].shift())  # k线下穿中轨
    df.loc[condition_sell, 'signal_long'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # ===找出做空信号
    # 当天的收盘价 < n1日的最低价，做空
    condition = (df['close'] < df['n_low'].shift(1))
    df.loc[condition, 'signal_short'] = -1
    # ===找出做空平仓
    # 当天的收盘价 > n2日的最高价，做空平仓
    # condition = (df['close'] > df['n2_high'].shift(1))

    # # 将卖出信号当天的signal设置为0
    # df.loc[condition, 'signal_short'] = 0

    condition_cover = (df['close'] > df['median']) & (
        df['close'].shift() <= df['median'].shift())  # K线上穿中轨
    df.loc[condition_cover, 'signal_short'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # 合并做多做空信号，去除重复信号
    df['signal'] = df[['signal_long', 'signal_short'
                       ]].sum(axis=1, min_count=1,
                              skipna=True)  # 若你的pandas版本是最新的，请使用本行代码代替上面一行
    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    # 将无关的变量删除
    df.drop(
        ['signal_long', 'signal_short', 'open_close_high', 'open_close_low'],
        axis=1,
        inplace=True)
    df['median'].fillna(method='bfill', inplace=True)
    df['n_high'].fillna(method='bfill', inplace=True)
    df['n_low'].fillna(method='bfill', inplace=True)
    signal_data = generate_signal_data(df)

    return df, df['median'].tolist(), df['n_high'].tolist(
    ), df['n_low'].tolist(), signal_data


def signal_highlow_bolling_wma(*args):
    df = args[0]
    n = int(args[1])

    indicator = 'close'
    df['median'] = talib.WMA(df[indicator], timeperiod=n)  # 使用WMA, 综合表现优于其他
    # df['median'] = talib.DEMA(df[indicator], timeperiod=n)
    # df['smedian'] = df[indicator].rolling(n, min_periods=1).mean()

    df['std'] = (df['high'] - df['low']).rolling(n).mean()
    df['z_score'] = abs(df[indicator] - df['median']) / df['std']
    df['m'] = df['z_score'].rolling(window=n).mean()
    df['upper'] = df['median'] + df['std'] * df['m']
    df['lower'] = df['median'] - df['std'] * df['m']

    condition1 = df['close'] > df['upper']
    condition2 = df['close'].shift(1) <= df['upper'].shift(1)
    df.loc[condition1 & condition2, 'signal_long'] = 1

    condition1 = df['close'] < df['median']
    condition2 = df['close'].shift(1) >= df['median'].shift(1)
    df.loc[condition1 & condition2, 'signal_long'] = 0

    condition1 = df['close'] < df['lower']
    condition2 = df['close'].shift(1) >= df['lower'].shift(1)
    df.loc[condition1 & condition2, 'signal_short'] = -1

    condition1 = df['close'] > df['median']
    condition2 = df['close'].shift(1) <= df['median'].shift(1)
    df.loc[condition1 & condition2, 'signal_short'] = 0

    df['signal_short'].fillna(method='ffill', inplace=True)
    df['signal_long'].fillna(method='ffill', inplace=True)
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1)
    df['signal'].fillna(value=0, inplace=True)
    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    signal_data = generate_signal_data(df)
    df['median'].fillna(method='bfill', inplace=True)
    df['upper'].fillna(method='bfill', inplace=True)
    df['lower'].fillna(method='bfill', inplace=True)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
    ), signal_data


def signal_highlow_bolling(*args):
    df = args[0]
    n = args[1]

    indicator = 'close'
    # df['median'] = talib.WMA(df[indicator], timeperiod=n)  # 使用WMA, 综合表现优于其他
    # df['median'] = talib.DEMA(df[indicator], timeperiod=n)
    df['median'] = df[indicator].rolling(n, min_periods=1).mean()

    df['std'] = (df['high'] - df['low']).rolling(n, min_periods=1).mean()
    df['z_score'] = abs(df[indicator] - df['median']) / df['std']
    df['m'] = df['z_score'].rolling(window=n, min_periods=1).mean()
    df['upper'] = df['median'] + df['std'] * df['m']
    df['lower'] = df['median'] - df['std'] * df['m']

    # 为了画图补全一下，不影响实际信号
    df.fillna(method='backfill', inplace=True)

    condition1 = df['close'] > df['upper']
    condition2 = df['close'].shift(1) <= df['upper'].shift(1)
    df.loc[condition1 & condition2, 'signal_long'] = 1

    condition1 = df['close'] < df['median']
    condition2 = df['close'].shift(1) >= df['median'].shift(1)
    df.loc[condition1 & condition2, 'signal_long'] = 0

    condition1 = df['close'] < df['lower']
    condition2 = df['close'].shift(1) >= df['lower'].shift(1)
    df.loc[condition1 & condition2, 'signal_short'] = -1

    condition1 = df['close'] > df['median']
    condition2 = df['close'].shift(1) <= df['median'].shift(1)
    df.loc[condition1 & condition2, 'signal_short'] = 0

    df['signal_short'].fillna(method='ffill', inplace=True)
    df['signal_long'].fillna(method='ffill', inplace=True)
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1)
    df['signal'].fillna(value=0, inplace=True)
    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    df['median'].fillna(method='bfill', inplace=True)
    df['upper'].fillna(method='bfill', inplace=True)
    df['lower'].fillna(method='bfill', inplace=True)
    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
    ), signal_data


def adapt_bolling_reverse(*args):
    df = args[0]
    n = args[1]

    # 使用自适应 m
    df['median'] = df['close'].rolling(n, min_periods=1).mean()
    df['std'] = df['close'].rolling(n,
                                    min_periods=1).std(ddof=0)  # ddof代表标准差自由度
    df['z_score'] = abs(df['close'] - df['median']) / df['std']
    # df['m'] = df['z_score'].rolling(window=n).max().shift()
    # df['m'] = df['z_score'].rolling(window=n).min().shift()
    df['m'] = df['z_score'].rolling(n, min_periods=1).mean().shift()

    # ===计算指标
    # 计算均线
    # 计算上轨、下轨道
    df['upper'] = df['median'] + df['m'] * df['std']
    df['lower'] = df['median'] - df['m'] * df['std']

    df.fillna(method='backfill', inplace=True)

    # 计算bias
    df['bias'] = df['close'] / df['median'] - 1

    # bias_pct 自适应
    df['bias_pct'] = abs(df['bias']).rolling(window=n,
                                             min_periods=1).max().shift()

    # ===计算原始布林策略信号
    # 找出做空信号
    condition1 = df['close'] > df['upper']  # 当前K线的收盘价 > 上轨
    condition2 = df['close'].shift(1) <= df['upper'].shift(1)  # 之前K线的收盘价 <= 上轨
    df.loc[condition1 & condition2,
           'signal_short'] = -1  # 将产生做多信号的那根K线的signal设置为1，1代表做多

    # 找出做空平仓信号
    condition1 = df['close'] < df['median']  # 当前K线的收盘价 < 中轨
    condition2 = df['close'].shift(1) >= df['median'].shift(
        1)  # 之前K线的收盘价 >= 中轨
    df.loc[condition1 & condition2,
           'signal_short'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # 找出做多信号
    condition1 = df['close'] < df['lower']  # 当前K线的收盘价 < 下轨
    condition2 = df['close'].shift(1) >= df['lower'].shift(1)  # 之前K线的收盘价 >= 下轨
    df.loc[condition1 & condition2,
           'signal_long'] = 1  # 将产生做空信号的那根K线的signal设置为-1，-1代表做空

    # 找出做多平仓信号
    condition1 = df['close'] > df['median']  # 当前K线的收盘价 > 中轨
    condition2 = df['close'].shift(1) <= df['median'].shift(
        1)  # 之前K线的收盘价 <= 中轨
    df.loc[condition1 & condition2,
           'signal_long'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # ===将long和short合并为signal
    df['signal_short'].fillna(method='ffill', inplace=True)
    df['signal_long'].fillna(method='ffill', inplace=True)
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1)
    df['signal'].fillna(value=0, inplace=True)
    df['raw_signal'] = df['signal']

    # ===根据bias，修改开仓时间
    df['temp'] = df['signal']

    # # 将原始信号做多时，当bias大于阀值，设置为空
    # condition1 = (df['signal'] == 1)
    # condition2 = (df['bias'] > df['bias_pct'])
    # df.loc[condition1 & condition2, 'temp'] = None

    # # 将原始信号做空时，当bias大于阀值，设置为空
    # condition1 = (df['signal'] == -1)
    # condition2 = (df['bias'] < -df['bias_pct'])
    # df.loc[condition1 & condition2, 'temp'] = None

    # 原始信号刚开仓，并且大于阀值，将信号设置为0
    condition1 = (df['signal'] != df['signal'].shift(1))
    condition2 = (df['temp'].isnull())
    df.loc[condition1 & condition2, 'temp'] = 0

    # 使用之前的信号补全原始信号
    df['temp'].fillna(method='ffill', inplace=True)
    df['signal'] = df['temp']

    # ===将signal中的重复值删除
    temp = df[['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp

    df.drop(
        ['raw_signal', 'std', 'bias', 'temp', 'signal_long', 'signal_short'],
        axis=1,
        inplace=True)

    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
    ), signal_data


def signal_simple_turtle_reverse(*args):
    """
    今天收盘价突破过去20天中的收盘价和开盘价中的最高价，做多。今天收盘价突破过去10天中的收盘价的最低价，平仓。
    今天收盘价突破过去20天中的收盘价和开盘价中的的最低价，做空。今天收盘价突破过去10天中的收盘价的最高价，平仓。
    :param para: [参数1, 参数2]
    :param df:
    :return:
    """
    df = args[0]
    n = args[1]

    df['open_close_high'] = df[['open', 'close']].max(axis=1)
    df['open_close_low'] = df[['open', 'close']].min(axis=1)
    # 最近n1日的最高价、最低价
    df['n_high'] = df['open_close_high'].rolling(n, min_periods=1).max()
    df['n_low'] = df['open_close_low'].rolling(n, min_periods=1).min()
    # # 最近n2日的最高价、最低价
    # df['n2_high'] = df['open_close_high'].rolling(n2, min_periods=1).max()
    # df['n2_low'] = df['open_close_low'].rolling(n2, min_periods=1).min()

    # #计算bbi
    # df["ma_low"] = df['open_close_low'].rolling(n1, min_periods=1).mean()
    # df['bbi_low'] = df['ma_low'].rolling(window=n1).mean()

    # df["ma_high"] = df['open_close_high'].rolling(n1, min_periods=1).mean()
    # df['bbi_high'] = df['ma_high'].rolling(window=n1).mean()

    # # dema平仓
    # close = [float(x) for x in df['close']]
    # df['median'] = talib.DEMA(np.array(close), timeperiod=n)

    # ema平仓
    df['median'] = df['close'].ewm(n, adjust=False).mean()
    df.fillna(method='backfill', inplace=True)
    # df['medianstd'] = talib.WMA(np.array(close), timeperiod=n1)
    # df['emastd'] = talib.EMA(np.array(close), timeperiod=n1)

    #dmacd
    # ===找出做多信号
    # 当天的收盘价 > n1日的最高价，做多
    condition = (df['close'] > df['n_high'].shift(1))
    # 将买入信号当天的signal设置为1
    df.loc[condition, 'signal_short'] = -1
    # ===找出做多平仓
    # 当天的收盘价 < n2日的最低价，多单平仓
    # condition = (df['close'] < df['n2_low'].shift(1))

    # # 将卖出信号当天的signal设置为0
    # df.loc[condition, 'signal_long'] = 0

    # 找出做多平仓信号， 触发条件为 穿中轨 或 回撤超过阈值 二者之一
    condition_sell = (df['close'] < df['median']) & (
        df['close'].shift() >= df['median'].shift())  # k线下穿中轨
    df.loc[condition_sell, 'signal_long'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # ===找出做空信号
    # 当天的收盘价 < n1日的最低价，做空
    condition = (df['close'] < df['n_low'].shift(1))
    df.loc[condition, 'signal_short'] = 1
    # ===找出做空平仓
    # 当天的收盘价 > n2日的最高价，做空平仓
    # condition = (df['close'] > df['n2_high'].shift(1))

    # # 将卖出信号当天的signal设置为0
    # df.loc[condition, 'signal_short'] = 0

    condition_cover = (df['close'] > df['median']) & (
        df['close'].shift() <= df['median'].shift())  # K线上穿中轨
    df.loc[condition_cover, 'signal_short'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # 合并做多做空信号，去除重复信号
    df['signal'] = df[['signal_long', 'signal_short'
                       ]].sum(axis=1, min_count=1,
                              skipna=True)  # 若你的pandas版本是最新的，请使用本行代码代替上面一行
    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    # 将无关的变量删除
    df.drop(
        ['signal_long', 'signal_short', 'open_close_high', 'open_close_low'],
        axis=1,
        inplace=True)

    signal_data = generate_signal_data(df)

    return df, df['median'].tolist(), df['n_high'].tolist(
    ), df['n_low'].tolist(), signal_data


def signal_atrbolling_bias_reverse(*args):
    df = args[0]
    n = args[1]

    #----计算atr和std
    df['atr'] = talib.ATR(df['high'], df['low'], df['close'], n)
    df['std'] = df['close'].rolling(window=n, min_periods=1).std(ddof=0)

    #-----计算中轨以及atr和std的倍数

    #---中轨
    close = [float(x) for x in df['close']]
    # df['median'] = talib.WMA(np.array(close), timeperiod=n)
    df['median'] = df['close'].rolling(window=n, min_periods=1).mean()

    #---atr，std倍数
    df['atr_J神'] = abs(df['close'] - df['median']) / df['atr']
    df['m_atr'] = df['atr_J神'].rolling(window=n, min_periods=1).max().shift(1)
    df['boll_J神'] = abs(df['close'] - df['median']) / df['std']
    df['m_boll'] = df['boll_J神'].rolling(window=n,
                                         min_periods=1).max().shift(1)

    #---分别计算atr，布林通道上下轨
    df['upper_atr'] = df['median'] + df['m_atr'] * df['atr']
    df['lower_atr'] = df['median'] - df['m_atr'] * df['atr']

    df['upper_boll'] = df['median'] + df['m_boll'] * df['std']
    df['lower_boll'] = df['median'] - df['m_boll'] * df['std']

    #----将两个上下轨揉在一起。取MIN开仓太频繁，取MAX开仓太少，最终取mean
    df['upper'] = df[['upper_atr', 'upper_boll']].mean(axis=1)
    df['lower'] = df[['lower_atr', 'lower_boll']].mean(axis=1)

    df.fillna(method='backfill', inplace=True)

    # 计算bias
    df['bias'] = df['close'] / df['median'] - 1
    # bias_pct 自适应
    df['bias_pct'] = abs(df['bias']).rolling(window=n,
                                             min_periods=1).max().shift()

    #-----计算开仓

    condition1 = df['close'] < df['median']  # 当前K线的收盘价 < 中轨
    condition2 = df['close'].shift(1) >= df['median'].shift(
        1)  # 之前K线的收盘价 >= 中轨
    df.loc[condition1 & condition2,
           'signal_short'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # ===找出做多信号
    condition1 = df['close'] > df['upper']  # 当前K线的收盘价 > 上轨
    condition2 = df['close'].shift(1) <= df['upper'].shift(1)  # 之前K线的收盘价 <= 上轨
    df.loc[condition1 & condition2,
           'signal_short'] = -1  # 将产生做多信号的那根K线的signal设置为1，1代表做多

    # ===找出做空平仓信号
    condition1 = df['close'] > df['median']  # 当前K线的收盘价 > 中轨
    condition2 = df['close'].shift(1) <= df['median'].shift(
        1)  # 之前K线的收盘价 <= 中轨
    df.loc[condition1 & condition2,
           'signal_long'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # ===找出做空信号
    condition1 = df['close'] < df['lower']  # 当前K线的收盘价 < 下轨
    condition2 = df['close'].shift(1) >= df['lower'].shift(1)  # 之前K线的收盘价 >= 下轨
    df.loc[condition1 & condition2,
           'signal_long'] = 1  # 将产生做空信号的那根K线的signal设置为-1，-1代表做空

    # 合并做多做空信号，去除重复信号
    df['signal_short'].fillna(method='ffill', inplace=True)
    df['signal_long'].fillna(method='ffill', inplace=True)
    df['signal'] = df[['signal_long', 'signal_short'
                       ]].sum(axis=1, min_count=1,
                              skipna=True)  # 若你的pandas版本是最新的，请使用本行代码代替上面一行
    df['signal'].fillna(value=0, inplace=True)

    # ===根据bias，修改开仓时间
    df['temp'] = df['signal']

    # # 将原始信号做多时，当bias大于阀值，设置为空
    # condition1 = (df['signal'] == 1)
    # condition2 = (df['bias'] > df['bias_pct'])
    # df.loc[condition1 & condition2, 'temp'] = None

    # # 将原始信号做空时，当bias大于阀值，设置为空
    # condition1 = (df['signal'] == -1)
    # condition2 = (df['bias'] < -df['bias_pct'])
    # df.loc[condition1 & condition2, 'temp'] = None

    # 原始信号刚开仓，并且大于阀值，将信号设置为0
    condition1 = (df['signal'] != df['signal'].shift(1))
    condition2 = (df['temp'].isnull())
    df.loc[condition1 & condition2, 'temp'] = 0

    # 使用之前的信号补全原始信号
    df['temp'].fillna(method='ffill', inplace=True)
    df['signal'] = df['temp']

    temp = df[['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp

    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
    ), signal_data


def signal_adapt_kc(*args):
    df = args[0]
    n = args[1]
    n2 = 3 * n
    df['TR'] = np.max([
        abs(df['high'] - df['low']),
        abs(df['high'] - df['close'].shift(1)),
        abs(df['close'].shift(1) - df['low'].shift(1))
    ],
                      axis=0)
    df['ATR'] = df['TR'].rolling(n2, min_periods=1).mean()
    df['median2'] = df['close'].ewm(span=180, min_periods=1,
                                    adjust=False).mean()
    df['z_score'] = abs(df['close'] - df['median2']) / df['ATR']
    df['m'] = df['z_score'].rolling(window=n2).max().shift()
    df['upper2'] = df['median2'] + df['ATR'] * df['m']
    df['lower2'] = df['median2'] - df['ATR'] * df['m']

    # condition_long = df['close'] > df['upper2']
    # condition_short = df['close'] < df['lower2']
    '''
    计算KC
    TR=MAX(ABS(HIGH-LOW),ABS(HIGH-REF(CLOSE,1)),ABS(REF(CLOSE,1)-REF(LOW,1)))
    ATR=MA(TR,N)
    Middle=EMA(CLOSE,20)
    自适应转换
    UPPER=MIDDLE+2*ATR
    LOWER=MIDDLE-2*ATR
    '''
    # 基于价格因素计算KC通道
    df['TR'] = np.max([
        abs(df['high'] - df['low']),
        abs(df['high'] - df['close'].shift(1)),
        abs(df['close'].shift(1) - df['low'].shift(1))
    ],
                      axis=0)
    df['ATR'] = df['TR'].rolling(n, min_periods=1).mean()
    df['median'] = df['close'].ewm(span=20, min_periods=1, adjust=False).mean()
    df['z_score'] = abs(df['close'] - df['median']) / df['ATR']
    df['m'] = df['z_score'].rolling(window=n).max().shift()
    df['upper'] = df['median'] + df['ATR'] * df['m']
    df['lower'] = df['median'] - df['ATR'] * df['m']

    condition_long = df['upper'] > df['upper2']
    condition_short = df['lower'] < df['lower2']

    # 找出做多信号
    condition1 = (df['close'] > df['upper']) & (df['close'].shift(1) <=
                                                df['upper'].shift(1))
    df.loc[(condition1 & condition_long), 'signal_long'] = 1

    # 找出做多平仓信号
    condition1 = (df['upper'] < df['upper2']) & (df['upper'].shift(1) >=
                                                 df['upper2'].shift(1))
    condition2 = (df['close'] < df['lower']) & (df['close'].shift() >=
                                                df['lower'].shift())
    df.loc[(condition1 | condition2), 'signal_long'] = 0

    # 找出做空信号
    condition1 = (df['close'] < df['lower']) & (df['close'].shift(1) >=
                                                df['lower'].shift(1))
    df.loc[condition1 & condition_short, 'signal_short'] = -1

    # 找出做空平仓信号
    condition1 = (df['lower'] > df['lower2']) & (df['lower'].shift(1) <=
                                                 df['lower2'].shift(1))
    condition2 = (df['close'] > df['upper']) & (df['close'].shift() <=
                                                df['upper'].shift())
    df.loc[condition1 | condition2, 'signal_short'] = 0
    # ========================= 固定代码 =========================

    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1,
                                                           min_count=1,
                                                           skipna=True)

    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    # ========================= 固定代码 =========================
    # 删除无关变量
    df.drop([
        'TR', 'ATR', 'm', 'z_score', 'median2', 'signal_long', 'signal_short'
    ],
            axis=1,
            inplace=True)

    df['median'].fillna(method='bfill', inplace=True)
    df['upper'].fillna(method='bfill', inplace=True)
    df['upper2'].fillna(method='bfill', inplace=True)
    df['lower'].fillna(method='bfill', inplace=True)
    df['lower2'].fillna(method='bfill', inplace=True)

    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
    ), df['upper2'].tolist(), df['lower2'].tolist(), signal_data


def signal_adapt_kc_with_rsi(*args):
    df = args[0]
    n = args[1]
    # n2 = 3 * n
    # df['TR'] = np.max([abs(df['high'] - df['low']), abs(df['high'] - df['low'].shift(1)),
    #                 abs(df['close'].shift(1) - df['low'].shift(1))], axis=0)
    # df['ATR'] = df['TR'].rolling(n2, min_periods=1).mean()
    # df['median2'] = df['close'].ewm(span=180, min_periods=1, adjust=False).mean()
    # df['z_score'] = abs(df['close'] - df['median2']) / df['ATR']
    # df['m'] = df['z_score'].rolling(window=n2).max().shift(1)
    # df['upper2'] = df['median2'] + df['ATR'] * df['m']
    # df['lower2'] = df['median2'] - df['ATR'] * df['m']
    '''
    计算KC
    TR=MAX(ABS(HIGH-LOW),ABS(HIGH-REF(CLOSE,1)),ABS(REF(CLOSE,1)-REF(LOW,1)))
    ATR=MA(TR,N)
    Middle=EMA(CLOSE,20)
    自适应转换
    UPPER=MIDDLE+2*ATR
    LOWER=MIDDLE-2*ATR
    '''
    # 基于价格因素计算KC通道
    df['TR'] = np.max([
        abs(df['high'] - df['low']),
        abs(df['high'] - df['close'].shift(1)),
        abs(df['close'].shift(1) - df['low'].shift(1))
    ],
                      axis=0)
    df['ATR'] = df['TR'].rolling(n, min_periods=1).mean()
    df['median'] = df['close'].ewm(span=20, min_periods=1, adjust=False).mean()
    df['z_score'] = abs(df['close'] - df['median']) / df['ATR']
    df['m'] = df['z_score'].rolling(window=n).max().shift(1)
    df['upper'] = df['median'] + df['ATR'] * df['m']
    df['lower'] = df['median'] - df['ATR'] * df['m']

    # RSI
    # CLOSEUP=IF(CLOSE>REF(CLOSE,1),CLOSE-REF(CLOSE,1),0)
    df['closeup'] = np.where(df['close'] > df['close'].shift(),
                             df['close'] - df['close'].shift(), 0)
    # # CLOSEDOWN=IF(CLOSE<REF(CLOSE,1),ABS(CLOSE-REF(CL OSE,1)),0)
    df['closedown'] = np.where(df['close'] < df['close'].shift(),
                               abs(df['close'] - df['close'].shift()), 0)
    # # CLOSEUP_MA=SMA(CLOSEUP,N,1)
    # df['data'].ewm(alpha=1 / 2, adjust=False).mean()
    df['closeup_ma'] = df['closeup'].ewm(alpha=1 / 2, adjust=False).mean()
    # # CLOSEDOWN_MA=SMA(CLOSEDOWN,N,1)
    df['closedown_ma'] = df['closedown'].ewm(alpha=1 / 2, adjust=False).mean()
    # # RSI=100*CLOSEUP_MA/(CLOSEUP_MA+CLOSEDOWN_MA)
    df['rsi'] = 100 * df['closeup_ma'] / (df['closeup_ma'] +
                                          df['closedown_ma'])
    # RSI_MIDDLE=MA(RSI,N)
    # df['rsi_middle'] = df['rsi'].rolling(n, min_periods=1).mean().shift()
    # # RSI_UPPER=RSI_MIDDLE+PARAM*STD(RSI,N)
    # df['z_score'] = abs(df['closeup_ma'] - df['rsi_middle']) / df['rsi']
    # df['m'] = df['z_score'].rolling(window=n).max().shift()
    # df['rsi_std'] = df['rsi'].rolling(n, min_periods=1).std(ddof=0)
    # # RSI_LOWER=RSI_MIDDLE-PARAM*STD(RSI,N)
    # df['rsi_lower'] = df['rsi_middle'] - df['m'] * df['rsi_std']
    # df['rsi_upper'] = df['rsi_middle'] + df['m'] * df['rsi_std']
    # 找出做多信号
    condition1 = (df['close'] > df['upper']) & (
        df['close'].shift(1) <= df['upper'].shift(1)) & (df['rsi'] > 70)
    # df.loc[(condition1 & condition_long), 'signal_long'] = 1
    df.loc[(condition1), 'signal_long'] = 1

    # 找出做多平仓信号
    # condition1 = (df['upper'] < df['upper2']) & (df['upper'].shift(1) >= df['upper2'].shift(1))
    condition1 = (df['rsi'] < 65)
    condition2 = (df['close'] < df['lower']) & (df['close'].shift() >=
                                                df['lower'].shift())
    df.loc[(condition1 & condition2), 'signal_long'] = 0

    # 找出做空信号
    condition1 = (df['close'] < df['lower']) & (
        df['close'].shift(1) >= df['lower'].shift(1)) & (df['rsi'] < 30)
    # df.loc[condition1 & condition_short, 'signal_short'] = -1
    df.loc[condition1, 'signal_short'] = -1

    # 找出做空平仓信号
    # condition1 = (df['lower'] > df['lower2']) & (df['lower'].shift(1) <= df['lower2'].shift(1))
    condition1 = (df['rsi'] > 35)
    condition2 = (df['close'] > df['upper']) & (df['close'].shift() <=
                                                df['upper'].shift())
    df.loc[condition1 & condition2, 'signal_short'] = 0

    # ========================= 固定代码 =========================

    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1,
                                                           min_count=1,
                                                           skipna=True)

    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    # ========================= 固定代码 =========================

    # 删除无关变量
    df.drop(['TR', 'ATR', 'm', 'z_score', 'signal_long', 'signal_short'],
            axis=1,
            inplace=True)

    df['median'].fillna(method='bfill', inplace=True)
    df['upper'].fillna(method='bfill', inplace=True)
    df['lower'].fillna(method='bfill', inplace=True)

    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
    ), signal_data


def signal_mike(*args):
    df = args[0]
    n = args[1]
    df['typ'] = (df['close'] + df['high'] + df['low']) / 3
    df['hh'] = df['high'].rolling(n, min_periods=1).max()
    df['ll'] = df['low'].rolling(n, min_periods=1).min()

    df['sr'] = df['hh'] * 2 - df['ll']
    df['mr'] = df['typ'] + df['hh'] - df['ll']
    df['wr'] = df['typ'] * 2 - df['ll']

    df['ws'] = df['typ'] * 2 - df['hh']
    df['ms'] = df['typ'] - (df['hh'] - df['ll'])
    df['ss'] = df['ll'] * 2 - df['hh']

    condtion1 = (df['close'] < df['ws'].shift()) & (df['close'] >
                                                    df['ms'].shift())
    condtion2 = df['close'] > df['sr'].shift()
    df.loc[(condtion1 | condtion2), 'signal_long'] = 1

    condtion1 = (df['close'] > df['wr'].shift()) & (df['close'] <
                                                    df['mr'].shift())
    condtion2 = df['close'] < df['ss'].shift()
    df.loc[condtion1 | condtion2, 'signal_short'] = -1

    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1,
                                                           min_count=1,
                                                           skipna=True)

    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]

    df['signal'] = temp['signal']
    # 删除无关变量
    df.drop([
        'typ', 'hh', 'll', 'sr', 'mr', 'wr', 'ws', 'ms', 'ss', 'signal_long',
        'signal_short'
    ],
            axis=1,
            inplace=True)
    signal_data = generate_signal_data(df)
    return df, signal_data


def mike_stop_with_bias(*args):
    df = args[0]
    n = args[1]
    # stop = para[1]
    n2 = 4 * 24 * 20  # 20日
    # 计算 mike 指标
    df['typ'] = (df['close'] + df['high'] + df['low']) / 3
    df['hh'] = df['high'].rolling(n, min_periods=1).max()
    df['ll'] = df['low'].rolling(n, min_periods=1).min()

    # 计算 bias 指标
    df['ma'] = df['close'].rolling(window=n2, min_periods=1).mean()
    # df['bias'] = (df['close'] - df['ma']) / df['ma'] * 100

    df['sr'] = df['hh'] * 2 - df['ll']
    df['mr'] = df['typ'] + df['hh'] - df['ll']
    df['wr'] = df['typ'] * 2 - df['ll']

    df['ws'] = df['typ'] * 2 - df['hh']
    df['ms'] = df['typ'] - (df['hh'] - df['ll'])
    df['ss'] = df['ll'] * 2 - df['hh']

    close = [float(x) for x in df['close']]
    df['median'] = talib.DEMA(np.array(close), timeperiod=n)

    # 当收盘价在初级支撑线与中级支撑线之间或者突破强力压力线时，平空做多；
    cond1 = (df['close'] < df['ws'].shift(1)) & (df['close'] >
                                                 df['ms'].shift(1))
    cond2 = df['close'] > df['sr'].shift(1)
    df.loc[cond1 | cond2, 'signal_long'] = 1
    # bias大于一定值 平多
    # df.loc[df['bias'] > stop, 'signal_long'] = 0
    # 找出做多平仓信号， 触发条件为 穿中轨 或 回撤超过阈值 二者之一
    condition_sell = (df['close'] < df['median']) & (
        df['close'].shift() >= df['median'].shift())  # k线下穿中轨
    df.loc[condition_sell, 'signal_long'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # 当收盘价在初级压力线和中间压力之间或者跌破强力支撑线时，平多做空。
    cond3 = (df['close'] > df['wr'].shift(1)) & (df['close'] <
                                                 df['mr'].shift(1))
    cond4 = df['close'] < df['ss'].shift(1)
    df.loc[cond3 | cond4, 'signal_short'] = -1
    # bias小于一定值 平空
    # df.loc[df['bias'] < -stop, 'signal_short'] = 0
    # ===找出做空平仓

    condition_cover = (df['close'] > df['median']) & (
        df['close'].shift() <= df['median'].shift())  # K线上穿中轨
    df.loc[condition_cover, 'signal_short'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # 合并做多做空信号，去除重复信号
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1,
                                                           min_count=1,
                                                           skipna=True)
    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    # 删除无关变量
    df.drop([
        'typ', 'hh', 'll', 'sr', 'mr', 'wr', 'ws', 'ms', 'ss', 'signal_long',
        'signal_short'
    ],
            axis=1,
            inplace=True)

    signal_data = generate_signal_data(df)
    return df, signal_data


def signal_dc_tunnel(*args):
    # 基础dc通道
    df = args[0]
    n = args[1]

    df['mean'] = df['close'].rolling(n).mean()
    df['max'] = df['close'].rolling(n).max().shift()
    df['min'] = df['close'].rolling(n).min().shift()

    factor = "close"

    # 做多信号
    condition1 = df[factor] > df['max']
    condition2 = df[factor].shift() <= df['max'].shift()
    df.loc[condition1 & condition2, 'signal_long'] = 1  # 1代表做多
    # 平多信号
    condition1 = df[factor] < df['mean']
    condition2 = df[factor].shift() >= df['mean'].shift()
    df.loc[condition1 & condition2, 'signal_long'] = 0
    # 做空信号
    condition1 = df[factor] < df['min']
    condition2 = df[factor].shift() >= df['min'].shift()
    df.loc[condition1 & condition2, 'signal_short'] = -1
    # 平空信号
    condition1 = df[factor] > df['mean']
    condition2 = df[factor].shift() <= df['mean'].shift()
    df.loc[condition1 & condition2, 'signal_short'] = 0

    # ===将long和short合并为signal
    df['signal_short'].fillna(method='ffill', inplace=True)
    df['signal_long'].fillna(method='ffill', inplace=True)
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1)
    df['signal'].fillna(value=0, inplace=True)

    temp = df[['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp
    df['mean'].fillna(method='bfill', inplace=True)
    df['max'].fillna(method='bfill', inplace=True)
    df['min'].fillna(method='bfill', inplace=True)
    signal_data = generate_signal_data(df)
    return df, df['mean'].tolist(), df['max'].tolist(), df['min'].tolist(
    ), signal_data


def signal_dc_flash_with_stop_lose(*args):
    # J神dc闪电侠
    """
    n： 时间窗口参数
    stop_loss_pct： 止损百分比参数
    DC上轨：n天收盘价的最大值
    DC下轨：n天收盘价的最小值
    当收盘价由下向上穿过DC上轨的时候，做多；
    当收盘价由上向下穿过DC下轨的时候，做空；
    flash 平仓。

    :param df:  原始数据
    :param para:  参数，[n, stop_lose]
    :param ma_dict: 均线ma缓存
    :return:
    """
    df = args[0]
    n = args[1]
    ma_dict = {}
    stop_loss_pct = 10

    df['signal'] = np.nan
    holding_times_min = 10

    df['median'] = df['close'].rolling(n, min_periods=1).mean()
    df['flash_stop_win'] = df['median'].copy()
    df['upper'] = df['close'].rolling(window=n).max().shift(1)
    df['lower'] = df['close'].rolling(window=n).min().shift(1)
    df['mtm'] = df['close'] / df['close'].shift(n) - 1

    df['c1'] = df['high'] - df['low']
    df['c2'] = abs(df['high'] - df['close'].shift(1))
    df['c3'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['c1', 'c2', 'c3']].max(axis=1)
    df['atr'] = df['tr'].rolling(window=n, min_periods=1).mean()

    condition1 = (df['close'] > df['upper']) & (df['mtm'] > 0)
    condition2 = df['close'].shift(1) <= df['upper'].shift(1)
    df.loc[condition1 & condition2, 'signal_long'] = 1

    condition1 = df['close'] < df['median']
    condition2 = df['close'].shift(1) >= df['median'].shift(1)
    df.loc[condition1 & condition2, 'signal_long'] = 0

    condition1 = (df['close'] < df['lower']) & (df['mtm'] < 0)
    condition2 = df['close'].shift(1) >= df['lower'].shift(1)
    df.loc[condition1 & condition2, 'signal_short'] = -1

    condition1 = df['close'] > df['median']
    condition2 = df['close'].shift(1) <= df['median'].shift(1)
    df.loc[condition1 & condition2, 'signal_short'] = 0

    info_dict = {
        'pre_signal': 0,
        'stop_lose_price': None,
        'holding_times': 0,
        'stop_win_times': 0,
        'stop_win_price': 0
    }

    for i in range(df.shape[0]):
        if info_dict['pre_signal'] == 0:
            if df.at[i, 'signal_long'] == 1:
                df.at[i, 'signal'] = 1
                pre_signal = 1
                stop_lose_price = df.at[i, 'close'] * (1 - stop_loss_pct / 100)
                info_dict = {
                    'pre_signal': pre_signal,
                    'stop_lose_price': stop_lose_price,
                    'holding_times': 0,
                    'stop_win_times': 0,
                    'stop_win_price': 0
                }
            elif df.at[i, 'signal_short'] == -1:
                df.at[i, 'signal'] = -1
                pre_signal = -1
                stop_lose_price = df.at[i, 'close'] * (1 + stop_loss_pct / 100)
                info_dict = {
                    'pre_signal': pre_signal,
                    'stop_lose_price': stop_lose_price,
                    'holding_times': 0,
                    'stop_win_times': 0,
                    'stop_win_price': 0
                }
            else:
                info_dict = {
                    'pre_signal': 0,
                    'stop_lose_price': None,
                    'holding_times': 0,
                    'stop_win_times': 0,
                    'stop_win_price': 0
                }
        elif info_dict['pre_signal'] == 1:
            holding_times = info_dict['holding_times']
            if df.at[i, 'atr'] < df.at[i - 1, 'atr']:
                info_dict['holding_times'] = holding_times + 1
            if df.at[i, 'close'] > df.at[i - 1, 'close']:
                if holding_times > 0:
                    info_dict['holding_times'] = holding_times - 1
                else:
                    info_dict['holding_times'] = 0
            ma_temp = max(n - int(n / 50) * 10 * holding_times,
                          holding_times_min)
            if ma_temp in ma_dict:
                df_ma_temp = ma_dict[ma_temp]
            else:
                df_ma_temp = df['close'].rolling(ma_temp, min_periods=1).mean()
                ma_dict[ma_temp] = df_ma_temp

            df.at[i, 'flash_stop_win'] = df_ma_temp.at[i]

            if df.at[i, 'close'] < df.at[i, 'flash_stop_win']:
                if df.at[i, 'close'] > info_dict[
                        'stop_win_price'] or info_dict['stop_win_times'] == 0:
                    info_dict['stop_win_price'] = df.at[i, 'close']
                    info_dict[
                        'stop_win_times'] = info_dict['stop_win_times'] + 1
                    info_dict['holding_times'] = 0
                else:
                    df.at[i, 'signal_long'] = 0
            if (df.at[i, 'signal_long'] == 0) or (
                    df.at[i, 'close'] < info_dict['stop_lose_price']):
                df.at[i, 'signal'] = 0
                info_dict = {
                    'pre_signal': 0,
                    'stop_lose_price': None,
                    'holding_times': 0,
                    'stop_win_times': 0,
                    'stop_win_price': 0
                }
            if df.at[i, 'signal_short'] == -1:
                df.at[i, 'signal'] = -1
                pre_signal = -1
                stop_lose_price = df.at[i, 'close'] * (1 + stop_loss_pct / 100)
                info_dict = {
                    'pre_signal': pre_signal,
                    'stop_lose_price': stop_lose_price,
                    'holding_times': 0,
                    'stop_win_times': 0,
                    'stop_win_price': 0
                }
        elif info_dict['pre_signal'] == -1:
            holding_times = info_dict['holding_times']
            if df.at[i, 'atr'] < df.at[i - 1, 'atr']:
                info_dict['holding_times'] = holding_times + 1
            if df.at[i, 'close'] < df.at[i - 1, 'close']:
                if holding_times > 0:
                    info_dict['holding_times'] = holding_times - 1
                else:
                    info_dict['holding_times'] = 0
            ma_temp = max(n - int(n / 50) * 10 * holding_times,
                          holding_times_min)
            if ma_temp in ma_dict:
                df_ma_temp = ma_dict[ma_temp]
            else:
                df_ma_temp = df['close'].rolling(ma_temp, min_periods=1).mean()
                ma_dict[ma_temp] = df_ma_temp
            df.at[i, 'flash_stop_win'] = df_ma_temp.at[i]
            if df.at[i, 'close'] > df.at[i, 'flash_stop_win']:
                if df.at[i, 'close'] < info_dict[
                        'stop_win_price'] or info_dict['stop_win_times'] == 0:
                    info_dict['stop_win_price'] = df.at[i, 'close']
                    info_dict[
                        'stop_win_times'] = info_dict['stop_win_times'] + 1
                    info_dict['holding_times'] = 0
                else:
                    df.at[i, 'signal_short'] = 0

            if (df.at[i, 'signal_short'] == 0) or (
                    df.at[i, 'close'] > info_dict['stop_lose_price']):
                df.at[i, 'signal'] = 0
                info_dict = {
                    'pre_signal': 0,
                    'stop_lose_price': None,
                    'holding_times': 0,
                    'stop_win_times': 0,
                    'stop_win_price': 0
                }
            if df.at[i, 'signal_long'] == 1:
                df.at[i, 'signal'] = 1
                pre_signal = 1
                stop_lose_price = df.at[i, 'close'] * (1 - stop_loss_pct / 100)
                info_dict = {
                    'pre_signal': pre_signal,
                    'stop_lose_price': stop_lose_price,
                    'holding_times': 0,
                    'stop_win_times': 0,
                    'stop_win_price': 0
                }
        else:
            raise ValueError('不可能出现其他的情况，如果出现，说明代码逻辑有误，报错')
    df['pos'] = df['signal'].shift()
    df['pos'].fillna(method='ffill', inplace=True)
    df['pos'].fillna(value=0, inplace=True)
    signal_data = generate_signal_data(df)
    return df, signal_data


def signal_dual_thrust(*args):
    # dual thrust
    df = args[0]
    n = args[1]

    df['hh'] = df['high'].rolling(n, min_periods=1).max()
    df['lc'] = df['close'].rolling(n, min_periods=1).min()
    df['hc'] = df['close'].rolling(n, min_periods=1).max()
    df['ll'] = df['low'].rolling(n, min_periods=1).min()

    condition1 = (df['hh'] - df['lc']) > (df['hc'] - df['ll'])
    condition2 = (df['hh'] - df['lc']) <= (df['hc'] - df['ll'])

    df.loc[condition1, 'range'] = df['hh'] - df['lc']
    df.loc[condition2, 'range'] = df['hc'] - df['ll']

    df['upper_open'] = 2 * abs(df['close'] -
                               df['open'].shift()) / df['range'].rolling(
                                   n, min_periods=1).max()
    df['lower_open'] = 2 * abs(df['open'].shift() -
                               df['close']) / df['range'].rolling(
                                   n, min_periods=1).max()

    df['upper'] = df['open'].shift() + df['upper_open'] * df['range']
    df['lower'] = df['open'].shift() - df['lower_open'] * df['range']

    #close >open + upper_open * range  upper_open <(close - open)/range
    #close <open - lower_open*range lower_open< (open -close)/range
    condition = df['close'] > df['upper']
    # condition &= df['close'].shift()  <= df['upper'].shift()
    # condition &= (df['upper'].shift() - df['lower'].shift())  > df['high'].shift() - df['low'].shift()
    condition &= (df['upper'].shift() -
                  df['lower'].shift()) / df['upper'].shift() > 0.05

    df.loc[condition, 'signal_long'] = 1

    condition = df['close'] < df['lower']
    # condition &= df['close'].shift()  >= df['lower'].shift()
    # condition &= (df['upper'].shift() - df['lower'].shift())  > df['high'].shift() - df['low'].shift()
    condition &= (df['upper'].shift() -
                  df['lower'].shift()) / df['upper'].shift() > 0.05

    df.loc[condition, 'signal_short'] = -1

    condition = (df['upper'].shift() -
                 df['lower'].shift()) < df['high'].shift() - df['low'].shift()
    condition |= (df['upper'].shift() -
                  df['lower'].shift()) / df['upper'].shift() < 0.05

    df.loc[condition, 'signal_short'] = 0
    df.loc[condition, 'signal_long'] = 0

    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1,
                                                           min_count=1,
                                                           skipna=True)

    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]

    df['signal'] = temp['signal']

    signal_data = generate_signal_data(df)
    return df, signal_data


def signal_takerby(*args):
    df = args[0]
    n = args[1]

    df = df.copy()
    df['volume'] = df['quote_volume'].rolling(n, min_periods=1).sum()
    df['buy_volume'] = df['taker_buy_quote_asset_volume'].rolling(
        n, min_periods=1).sum()
    df['takerby'] = df['buy_volume'] / df['volume']

    df['takerby_h'] = df['takerby'].rolling(n, min_periods=1).max()
    df['takerby_l'] = df['takerby'].rolling(n, min_periods=1).min()
    df['takerby_c'] = df['takerby'].rolling(n, min_periods=1).mean()

    df['takerby_c1'] = df['takerby_h'] - df['takerby_l']
    df['takerby_c2'] = abs(df['takerby_h'] - df['takerby_c'].shift(1))
    df['takerby_c3'] = abs(df['takerby_l'] - df['takerby_c'].shift(1))

    df['takerby_tr'] = df[['takerby_c1', 'takerby_c2',
                           'takerby_c3']].max(axis=1)
    df['takerby_atr'] = df['takerby_tr'].rolling(window=n,
                                                 min_periods=1).mean()

    # 删除无关变量
    df.drop([
        'volume', 'buy_volume', 'takerby', 'takerby_h', 'takerby_l',
        'takerby_c', 'takerby_c1', 'takerby_c2', 'takerby_c3', 'takerby_tr'
    ],
            axis=1,
            inplace=True)
    return df


def signal_bias(*args):
    df = args[0]
    n = args[1]

    df['ma'] = df['close'].rolling(n, min_periods=1).mean()
    df['bias_c'] = (df['close'] / df['ma'] - 1)

    df['ma'] = df['high'].rolling(n, min_periods=1).mean()
    df['bias_h'] = (df['high'] / df['ma'] - 1)

    df['ma'] = df['low'].rolling(n, min_periods=1).mean()
    df['bias_l'] = (df['low'] / df['ma'] - 1)

    df['bias_c1'] = df['bias_h'] - df['bias_l']
    df['bias_c2'] = abs(df['bias_h'] - df['bias_c'].shift(1))
    df['bias_c3'] = abs(df['bias_l'] - df['bias_c'].shift(1))
    df['bias_tr'] = df[['bias_c1', 'bias_c2', 'bias_c3']].max(axis=1)
    df['bias_atr'] = df['bias_tr'].rolling(window=n, min_periods=1).mean()

    # 参考ATR，对MTM mean指标，计算波动率因子
    df['bias_l_mean'] = df['bias_l'].rolling(window=n, min_periods=1).mean()
    df['bias_h_mean'] = df['bias_h'].rolling(window=n, min_periods=1).mean()
    df['bias_c_mean'] = df['bias_c'].rolling(window=n, min_periods=1).mean()
    df['bias_c1'] = df['bias_h_mean'] - df['bias_l_mean']
    df['bias_c2'] = abs(df['bias_h_mean'] - df['bias_c_mean'].shift(1))
    df['bias_c3'] = abs(df['bias_l_mean'] - df['bias_c_mean'].shift(1))
    df['bias_tr'] = df[['bias_c1', 'bias_c2', 'bias_c3']].max(axis=1)
    df['bias_atr_mean'] = df['bias_tr'].rolling(window=n, min_periods=1).mean()

    # 删除无关变量
    df.drop([
        'ma', 'bias_c', 'bias_h', 'bias_l', 'bias_c1', 'bias_c2', 'bias_c3',
        'bias_tr', 'bias_l_mean', 'bias_h_mean', 'bias_c_mean'
    ],
            axis=1,
            inplace=True)
    return df


def signal_zhangdiefu_std(*args):
    df = args[0]
    n = args[1]

    # 涨跌幅std，振幅的另外一种形式
    change = df['close'].pct_change()
    df['zhf_c'] = pd.Series(change).rolling(n).std()

    change = df['high'].pct_change()
    df['zhf_h'] = pd.Series(change).rolling(n).std()

    change = df['low'].pct_change()
    df['zhf_l'] = pd.Series(change).rolling(n).std()

    df['zhf_c1'] = df['zhf_h'] - df['zhf_l']
    df['zhf_c2'] = abs(df['zhf_h'] - df['zhf_c'].shift(1))
    df['zhf_c3'] = abs(df['zhf_l'] - df['zhf_c'].shift(1))
    df['zhf_tr'] = df[['zhf_c1', 'zhf_c2', 'zhf_c3']].max(axis=1)
    df['zdf_atr'] = df['zhf_tr'].rolling(window=n, min_periods=1).mean()

    # 参考ATR，对MTM mean指标，计算波动率因子
    df['zdf_l_mean'] = df['zhf_l'].rolling(window=n, min_periods=1).mean()
    df['zdf_h_mean'] = df['zhf_h'].rolling(window=n, min_periods=1).mean()
    df['zdf_c_mean'] = df['zhf_c'].rolling(window=n, min_periods=1).mean()
    df['zdf_c1'] = df['zdf_h_mean'] - df['zdf_l_mean']
    df['zdf_c2'] = abs(df['zdf_h_mean'] - df['zdf_c_mean'].shift(1))
    df['zdf_c3'] = abs(df['zdf_l_mean'] - df['zdf_c_mean'].shift(1))
    df['zdf_tr'] = df[['zdf_c1', 'zdf_c2', 'zdf_c3']].max(axis=1)
    df['zdf_atr_mean'] = df['zdf_tr'].rolling(window=n, min_periods=1).mean()

    # 删除无关变量
    df.drop([
        'zhf_c', 'zhf_h', 'zhf_l', 'zhf_c1', 'zhf_c2', 'zhf_c3', 'zhf_tr',
        'zdf_l_mean', 'zdf_h_mean', 'zdf_c_mean'
    ],
            axis=1,
            inplace=True)
    return df


def signal_vwap(*args):
    df = args[0]
    n = args[1]

    df['vwap'] = df['quote_volume'] / df['volume']  # 在周期内成交额除以成交量等于成交均价
    ma = df['vwap'].rolling(n, min_periods=1).mean()  # 求移动平均线
    df['vwapbias_c'] = df['vwap'] / (ma + eps) - 1  # 去量纲

    ma = df['vwap'].rolling(n, min_periods=1).max()  # 求移动平均线
    df['vwapbias_h'] = df['vwap'] / (ma + eps) - 1  # 去量纲

    ma = df['vwap'].rolling(n, min_periods=1).min()  # 求移动平均线
    df['vwapbias_l'] = df['vwap'] / (ma + eps) - 1  # 去量纲

    df['vwapbias_c1'] = df['vwapbias_h'] - df['vwapbias_l']
    df['vwapbias_c2'] = abs(df['vwapbias_h'] - df['vwapbias_c'].shift(1))
    df['vwapbias_c3'] = abs(df['vwapbias_l'] - df['vwapbias_c'].shift(1))
    df['vwapbias_tr'] = df[['vwapbias_c1', 'vwapbias_c2',
                            'vwapbias_c3']].max(axis=1)
    df['vwapbias_atr'] = df['vwapbias_tr'].rolling(window=n,
                                                   min_periods=1).mean()

    df['vwapbias_l_mean'] = df['vwapbias_l'].rolling(window=n,
                                                     min_periods=1).mean()
    df['vwapbias_h_mean'] = df['vwapbias_h'].rolling(window=n,
                                                     min_periods=1).mean()
    df['vwapbias_c_mean'] = df['vwapbias_c'].rolling(window=n,
                                                     min_periods=1).mean()
    df['vwapbias_c1'] = df['vwapbias_h_mean'] - df['vwapbias_l_mean']
    df['vwapbias_c2'] = abs(df['vwapbias_h_mean'] -
                            df['vwapbias_c_mean'].shift(1))
    df['vwapbias_c3'] = abs(df['vwapbias_l_mean'] -
                            df['vwapbias_c_mean'].shift(1))
    df['vwapbias_tr'] = df[['vwapbias_c1', 'vwapbias_c2',
                            'vwapbias_c3']].max(axis=1)
    df['vwapbias_atr_mean'] = df['vwapbias_tr'].rolling(window=n,
                                                        min_periods=1).mean()
    # 删除无关变量
    df.drop([
        'vwap', 'vwapbias_c', 'vwapbias_h', 'vwapbias_l', 'vwapbias_c1',
        'vwapbias_c2', 'vwapbias_c3', 'vwapbias_l_mean', 'vwapbias_h_mean',
        'vwapbias_c_mean', 'vwapbias_tr'
    ],
            axis=1,
            inplace=True)
    return df


def signal_rsi(*args):
    df = args[0]
    n = args[1]

    # rsi
    df['rtn'] = df['close'].diff()
    df['up'] = np.where(df['rtn'] > 0, df['rtn'], 0)
    df['down'] = np.where(df['rtn'] < 0, abs(df['rtn']), 0)
    df['A'] = df['up'].rolling(n).sum()
    df['B'] = df['down'].rolling(n).sum()
    df['rsi_c'] = df['A'] / (df['A'] + df['B']) * 100

    df['rtn'] = df['high'].diff()
    df['up'] = np.where(df['rtn'] > 0, df['rtn'], 0)
    df['down'] = np.where(df['rtn'] < 0, abs(df['rtn']), 0)
    df['A'] = df['up'].rolling(n).sum()
    df['B'] = df['down'].rolling(n).sum()
    df['rsi_h'] = df['A'] / (df['A'] + df['B']) * 100

    df['rtn'] = df['low'].diff()
    df['up'] = np.where(df['rtn'] > 0, df['rtn'], 0)
    df['down'] = np.where(df['rtn'] < 0, abs(df['rtn']), 0)
    df['A'] = df['up'].rolling(n).sum()
    df['B'] = df['down'].rolling(n).sum()
    df['rsi_l'] = df['A'] / (df['A'] + df['B']) * 100

    df['rsi_c1'] = df['rsi_h'] - df['rsi_l']
    df['rsi_c2'] = abs(df['rsi_h'] - df['rsi_c'].shift(1))
    df['rsi_c3'] = abs(df['rsi_l'] - df['rsi_c'].shift(1))
    df['rsi_tr'] = df[['rsi_c1', 'rsi_c2', 'rsi_c3']].max(axis=1)
    df['rsi_atr'] = df['rsi_tr'].rolling(window=n, min_periods=1).mean()

    df['rsi_l_mean'] = df['rsi_l'].rolling(window=n, min_periods=1).mean()
    df['rsi_h_mean'] = df['rsi_h'].rolling(window=n, min_periods=1).mean()
    df['rsi_c_mean'] = df['rsi_c'].rolling(window=n, min_periods=1).mean()
    df['rsi_c1'] = df['rsi_h_mean'] - df['rsi_l_mean']
    df['rsi_c2'] = abs(df['rsi_h_mean'] - df['rsi_c_mean'].shift(1))
    df['rsi_c3'] = abs(df['rsi_l_mean'] - df['rsi_c_mean'].shift(1))
    df['rsi_tr'] = df[['rsi_c1', 'rsi_c2', 'rsi_c3']].max(axis=1)
    df['rsi_atr_mean'] = df['rsi_tr'].rolling(window=n, min_periods=1).mean()

    # 删除无关变量
    df.drop([
        'rtn', 'up', 'down', 'A', 'B', 'rsi_c', 'rsi_h', 'rsi_l', 'rsi_c_mean',
        'rsi_c1', 'rsi_c2', 'rsi_c3', 'rsi_c3', 'rsi_tr', 'rsi_l_mean',
        'rsi_h_mean'
    ],
            axis=1,
            inplace=True)
    return df


def signal_mtm(*args):
    df = args[0]
    n = args[1]

    df['mtm'] = df['close'] / df['close'].shift(n) - 1
    df['mtm_mean'] = df['mtm'].rolling(window=n, min_periods=1).mean()

    # 参考ATR，对MTM指标，计算波动率因子
    df['mtm_l'] = df['low'] / df['low'].shift(n) - 1
    df['mtm_h'] = df['high'] / df['high'].shift(n) - 1
    df['mtm_c'] = df['close'] / df['close'].shift(n) - 1
    df['mtm_c1'] = df['mtm_h'] - df['mtm_l']
    df['mtm_c2'] = abs(df['mtm_h'] - df['mtm_c'].shift(1))
    df['mtm_c3'] = abs(df['mtm_l'] - df['mtm_c'].shift(1))
    df['mtm_tr'] = df[['mtm_c1', 'mtm_c2', 'mtm_c3']].max(axis=1)
    df['mtm_atr'] = df['mtm_tr'].rolling(window=n, min_periods=1).mean()

    # 参考ATR，对MTM mean指标，计算波动率因子
    df['mtm_l_mean'] = df['mtm_l'].rolling(window=n, min_periods=1).mean()
    df['mtm_h_mean'] = df['mtm_h'].rolling(window=n, min_periods=1).mean()
    df['mtm_c_mean'] = df['mtm_c'].rolling(window=n, min_periods=1).mean()
    df['mtm_c1'] = df['mtm_h_mean'] - df['mtm_l_mean']
    df['mtm_c2'] = abs(df['mtm_h_mean'] - df['mtm_c_mean'].shift(1))
    df['mtm_c3'] = abs(df['mtm_l_mean'] - df['mtm_c_mean'].shift(1))
    df['mtm_tr'] = df[['mtm_c1', 'mtm_c2', 'mtm_c3']].max(axis=1)
    df['mtm_atr_mean'] = df['mtm_tr'].rolling(window=n, min_periods=1).mean()
    # 删除无关变量
    df.drop([
        'mtm', 'mtm_mean', 'mtm_l', 'mtm_h', 'mtm_c', 'mtm_c1', 'mtm_c2',
        'mtm_c3', 'mtm_tr', 'mtm_l_mean', 'mtm_h_mean', 'mtm_c1', 'mtm_c2',
        'mtm_c3', 'mtm_tr'
    ],
            axis=1,
            inplace=True)
    return df


def signal_cci(*args):
    df = args[0]
    n = args[1]

    df['tp'] = (df['high'] + df['low'] + df['close']) / 3
    df['ma'] = df['tp'].rolling(window=n, min_periods=1).mean()
    df['md'] = abs(df['close'] - df['ma']).rolling(window=n,
                                                   min_periods=1).mean()
    df['cci_c'] = (df['tp'] - df['ma']) / df['md'] / 0.015

    df['cci_mean'] = df['cci_c'].rolling(window=n, min_periods=1).mean()

    df['ma_h'] = df['tp'].rolling(window=n, min_periods=1).max()
    df['md_h'] = abs(df['close'] - df['ma_h']).rolling(window=n,
                                                       min_periods=1).max()
    df['cci_h'] = (df['tp'] - df['ma_h']) / df['md_h'] / 0.015

    df['ma_l'] = df['tp'].rolling(window=n, min_periods=1).min()
    df['md_l'] = abs(df['close'] - df['ma_l']).rolling(window=n,
                                                       min_periods=1).min()
    df['cci_l'] = (df['tp'] - df['ma_l']) / df['md_l'] / 0.015

    df['cci_c1'] = df['cci_h'] - df['cci_l']
    df['cci_c2'] = abs(df['cci_h'] - df['cci_c'].shift(1))
    df['cci_c3'] = abs(df['cci_l'] - df['cci_c'].shift(1))
    df['cci_tr'] = df[['cci_c1', 'cci_c2', 'cci_c3']].max(axis=1)
    df['cci_atr'] = df['cci_tr'].rolling(window=n, min_periods=1).mean()

    df['cci_l_mean'] = df['cci_l'].rolling(window=n, min_periods=1).mean()
    df['cci_h_mean'] = df['cci_h'].rolling(window=n, min_periods=1).mean()
    df['cci_c_mean'] = df['cci_c'].rolling(window=n, min_periods=1).mean()
    df['cci_c1'] = df['cci_h_mean'] - df['cci_l_mean']
    df['cci_c2'] = abs(df['cci_h_mean'] - df['cci_c_mean'].shift(1))
    df['cci_c3'] = abs(df['cci_l_mean'] - df['cci_c_mean'].shift(1))
    df['cci_tr'] = df[['cci_c1', 'cci_c2', 'cci_c3']].max(axis=1)
    df['cci_atr_mean'] = df['cci_tr'].rolling(window=n, min_periods=1).mean()
    # 删除无关变量
    df.drop([
        'tp', 'ma', 'md', 'cci_c', 'cci_mean', 'ma_h', 'md_h', 'cci_h', 'ma_l',
        'md_l', 'cci_l', 'cci_c1', 'cci_c2', 'cci_c3', 'cci_tr', 'cci_l_mean',
        'cci_h_mean', 'cci_c_mean'
    ],
            axis=1,
            inplace=True)
    return df


def signal_vixbw(*args):
    df = args[0]
    n = args[1]

    df['vix'] = df['close'] / df['close'].shift(n) - 1
    df['vix_median'] = df['vix'].rolling(window=n, min_periods=1).mean()
    df['vix_std'] = df['vix'].rolling(n, min_periods=1).std()
    df['vix_score'] = abs(df['vix'] - df['vix_median']) / df['vix_std']
    df['max'] = df['vix_score'].rolling(window=n,
                                        min_periods=1).mean().shift(1)
    df['min'] = df['vix_score'].rolling(window=n, min_periods=1).min().shift(1)
    df['vix_upper'] = df['vix_median'] + df['max'] * df['vix_std']
    df['vix_lower'] = df['vix_median'] - df['max'] * df['vix_std']
    df['vixbw'] = (df['vix_upper'] - df['vix_lower']) * np.sign(
        df['vix_median'].diff(n))
    # 删除无关变量
    df.drop([
        'vix', 'vix_median', 'vix_std', 'vix_score', 'min', 'vix_upper',
        'vix_lower'
    ],
            axis=1,
            inplace=True)
    return df


def signal_volume(*args):
    df = args[0]
    n = args[1]

    df['volume_c'] = df['quote_volume'].rolling(n, min_periods=1).mean()
    df['volume_l'] = df['quote_volume'].rolling(n, min_periods=1).min()
    df['volume_h'] = df['quote_volume'].rolling(n, min_periods=1).max()

    df['volume_c1'] = df['volume_h'] - df['volume_l']
    df['volume_c2'] = abs(df['volume_h'] - df['volume_c'].shift(1))
    df['volume_c3'] = abs(df['volume_l'] - df['volume_c'].shift(1))
    df['volume_tr'] = df[['volume_c1', 'volume_c2', 'volume_c3']].max(axis=1)
    df['volume_atr'] = df['volume_tr'].rolling(window=n, min_periods=1).mean()

    df['volume_l_mean'] = df['volume_l'].rolling(window=n,
                                                 min_periods=1).mean()
    df['volume_h_mean'] = df['volume_h'].rolling(window=n,
                                                 min_periods=1).mean()
    df['volume_c_mean'] = df['volume_c'].rolling(window=n,
                                                 min_periods=1).mean()
    df['volume_c1'] = df['volume_h_mean'] - df['volume_l_mean']
    df['volume_c2'] = abs(df['volume_h_mean'] - df['volume_c_mean'].shift(1))
    df['volume_c3'] = abs(df['volume_l_mean'] - df['volume_c_mean'].shift(1))
    df['volume_tr'] = df[['volume_c1', 'volume_c2', 'volume_c3']].max(axis=1)
    df['volume_atr_mean'] = df['volume_tr'].rolling(window=n,
                                                    min_periods=1).mean()
    # 删除无关变量
    df.drop([
        'volume_c', 'volume_l', 'volume_h', 'volume_c1', 'volume_c2',
        'volume_c3', 'volume_tr', 'volume_l_mean', 'volume_h_mean',
        'volume_c_mean'
    ],
            axis=1,
            inplace=True)
    return df


def adaptboll_with_cci(*args):
    '''
    cci_atr + cci_atr_mean
    '''
    df = args[0]
    n = args[1]
    n2 = 35 * n  #35

    df['median'] = df['close'].rolling(window=n2).mean()
    df['std'] = df['close'].rolling(n2,
                                    min_periods=1).std(ddof=0)  # ddof代表标准差自由度
    df['z_score'] = abs(df['close'] - df['median']) / df['std']
    df['m'] = df['z_score'].rolling(window=n2).mean()
    df['upper'] = df['median'] + df['std'] * df['m']
    df['lower'] = df['median'] - df['std'] * df['m']

    condition_long = df['close'] > df['upper']
    condition_short = df['close'] < df['lower']

    indicator = 'cci_atr'  #短线

    df = signal_cci(df, n)

    df[indicator] = df[indicator] * df['cci_atr_mean']  #1

    # 对新策略因子计算自适应布林
    df['median'] = df[indicator].rolling(window=n).mean()
    df['std'] = df[indicator].rolling(n, min_periods=1).apply(np.std)  # 配合精度修改std
    df['z_score'] = abs(df[indicator] - df['median']) / df['std']
    # df['m'] = df['z_score'].rolling(window=n).max().shift(1)
    # df['m'] = df['z_score'].rolling(window=n).mean()
    df['m'] = df['z_score'].rolling(window=n).min().shift(1)
    df['up'] = df['median'] + df['std'] * df['m']
    df['dn'] = df['median'] - df['std'] * df['m']

    # 突破上轨做多
    condition1 = df[indicator] > df['up']
    condition2 = df[indicator].shift(1) <= df['up'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_long'] = 1

    # 突破下轨做空
    condition1 = df[indicator] < df['dn']
    condition2 = df[indicator].shift(1) >= df['dn'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_short'] = -1

    # 均线平仓(多头持仓)
    condition1 = df[indicator] < df['median']
    condition2 = df[indicator].shift(1) >= df['median'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_long'] = 0

    # 均线平仓(空头持仓)
    condition1 = df[indicator] > df['median']
    condition2 = df[indicator].shift(1) <= df['median'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_short'] = 0

    df.loc[condition_long, 'signal_short'] = 0
    df.loc[condition_short, 'signal_long'] = 0

    # ===由signal计算出实际的每天持有仓位
    # signal的计算运用了收盘价，是每根K线收盘之后产生的信号，到第二根开盘的时候才买入，仓位才会改变。
    df['signal_short'].fillna(method='ffill', inplace=True)
    df['signal_long'].fillna(method='ffill', inplace=True)
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1)
    df['signal'].fillna(value=0, inplace=True)
    # df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1, min_count=1,
    #                                                        skipna=True)  # 若你的pandas版本是最新的，请使用本行代码代替上面一行

    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    df.drop(['signal_long', 'signal_short', 'z_score'], axis=1, inplace=True)

    signal_data = generate_signal_data(df)

    return df, signal_data


def adaptboll_with_mtm_cci_zdf(*args):
    '''
    cci_atr + cci_atr_mean + mtm_atr + zdf_atr_mean
    '''
    df = args[0]
    n = args[1]
    n2 = 35 * n  #35

    df['median'] = df['close'].rolling(window=n2).mean()
    df['std'] = df['close'].rolling(n2,
                                    min_periods=1).std(ddof=0)  # ddof代表标准差自由度
    df['z_score'] = abs(df['close'] - df['median']) / df['std']
    df['m'] = df['z_score'].rolling(window=n2).mean()
    df['upper'] = df['median'] + df['std'] * df['m']
    df['lower'] = df['median'] - df['std'] * df['m']

    condition_long = df['close'] > df['upper']
    condition_short = df['close'] < df['lower']

    # 基于价格atr，计算波动率因子wd_atr
    df['c1'] = df['high'] - df['low']
    df['c2'] = abs(df['high'] - df['close'].shift(1))
    df['c3'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['c1', 'c2', 'c3']].max(axis=1)
    df['atr'] = df['tr'].rolling(window=n, min_periods=1).mean()
    df['avg_price'] = df['close'].rolling(window=n, min_periods=1).mean()
    df['wd_atr'] = df['atr'] / df['avg_price']

    indicator = 'cci_atr'  #短线
    df = signal_zhangdiefu_std(df, n)
    df = signal_cci(df, n)
    df = signal_mtm(df, n)

    # mtm_mean 指标分别乘以三个波动率因子 2-10
    df[indicator] = df[indicator] * df['cci_atr_mean']
    df[indicator] = df[indicator] * df['mtm_atr']
    df[indicator] = df[indicator] * df['zdf_atr_mean']

    # 对新策略因子计算自适应布林
    df['median'] = df[indicator].rolling(window=n).mean()
    df['std'] = df[indicator].rolling(n, min_periods=1).apply(np.std)  # 配合精度修改std
    df['z_score'] = abs(df[indicator] - df['median']) / df['std']
    # df['m'] = df['z_score'].rolling(window=n).max().shift(1)
    # df['m'] = df['z_score'].rolling(window=n).mean()
    df['m'] = df['z_score'].rolling(window=n).min().shift(1)
    df['up'] = df['median'] + df['std'] * df['m']
    df['dn'] = df['median'] - df['std'] * df['m']

    # 突破上轨做多
    condition1 = df[indicator] > df['up']
    condition2 = df[indicator].shift(1) <= df['up'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_long'] = 1

    # 突破下轨做空
    condition1 = df[indicator] < df['dn']
    condition2 = df[indicator].shift(1) >= df['dn'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_short'] = -1

    # 均线平仓(多头持仓)
    condition1 = df[indicator] < df['median']
    condition2 = df[indicator].shift(1) >= df['median'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_long'] = 0

    # 均线平仓(空头持仓)
    condition1 = df[indicator] > df['median']
    condition2 = df[indicator].shift(1) <= df['median'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_short'] = 0

    df.loc[condition_long, 'signal_short'] = 0
    df.loc[condition_short, 'signal_long'] = 0

    # ===由signal计算出实际的每天持有仓位
    # signal的计算运用了收盘价，是每根K线收盘之后产生的信号，到第二根开盘的时候才买入，仓位才会改变。
    df['signal_short'].fillna(method='ffill', inplace=True)
    df['signal_long'].fillna(method='ffill', inplace=True)
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1)
    df['signal'].fillna(value=0, inplace=True)
    # df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1, min_count=1,
    #                                                        skipna=True)  # 若你的pandas版本是最新的，请使用本行代码代替上面一行

    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    df.drop(['signal_long', 'signal_short', 'z_score'], axis=1, inplace=True)

    signal_data = generate_signal_data(df)

    return df, signal_data


def signal_atrbolling_bias_reverse(*args):
    df = args[0]
    n = args[1]

    #----计算atr和std
    df['atr'] = talib.ATR(df['high'], df['low'], df['close'], n)
    df['std'] = df['close'].rolling(window=n, min_periods=1).std(ddof=0)

    #-----计算中轨以及atr和std的倍数

    #---中轨
    close = [float(x) for x in df['close']]
    # df['median'] = talib.WMA(np.array(close), timeperiod=n)
    df['median'] = df['close'].rolling(window=n, min_periods=1).mean()

    #---atr，std倍数
    df['atr_J神'] = abs(df['close'] - df['median']) / df['atr']
    df['m_atr'] = df['atr_J神'].rolling(window=n, min_periods=1).max().shift(1)
    df['boll_J神'] = abs(df['close'] - df['median']) / df['std']
    df['m_boll'] = df['boll_J神'].rolling(window=n,
                                         min_periods=1).max().shift(1)

    #---分别计算atr，布林通道上下轨
    df['upper_atr'] = df['median'] + df['m_atr'] * df['atr']
    df['lower_atr'] = df['median'] - df['m_atr'] * df['atr']

    df['upper_boll'] = df['median'] + df['m_boll'] * df['std']
    df['lower_boll'] = df['median'] - df['m_boll'] * df['std']

    #----将两个上下轨揉在一起。取MIN开仓太频繁，取MAX开仓太少，最终取mean
    df['upper'] = df[['upper_atr', 'upper_boll']].mean(axis=1)
    df['lower'] = df[['lower_atr', 'lower_boll']].mean(axis=1)

    df.fillna(method='backfill', inplace=True)

    # 计算bias
    df['bias'] = df['close'] / df['median'] - 1
    # bias_pct 自适应
    df['bias_pct'] = abs(df['bias']).rolling(window=n,
                                             min_periods=1).max().shift()

    #-----计算开仓

    condition1 = df['close'] < df['median']  # 当前K线的收盘价 < 中轨
    condition2 = df['close'].shift(1) >= df['median'].shift(
        1)  # 之前K线的收盘价 >= 中轨
    df.loc[condition1 & condition2,
           'signal_short'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # ===找出做多信号
    condition1 = df['close'] > df['upper']  # 当前K线的收盘价 > 上轨
    condition2 = df['close'].shift(1) <= df['upper'].shift(1)  # 之前K线的收盘价 <= 上轨
    df.loc[condition1 & condition2,
           'signal_short'] = -1  # 将产生做多信号的那根K线的signal设置为1，1代表做多

    # ===找出做空平仓信号
    condition1 = df['close'] > df['median']  # 当前K线的收盘价 > 中轨
    condition2 = df['close'].shift(1) <= df['median'].shift(
        1)  # 之前K线的收盘价 <= 中轨
    df.loc[condition1 & condition2,
           'signal_long'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # ===找出做空信号
    condition1 = df['close'] < df['lower']  # 当前K线的收盘价 < 下轨
    condition2 = df['close'].shift(1) >= df['lower'].shift(1)  # 之前K线的收盘价 >= 下轨
    df.loc[condition1 & condition2,
           'signal_long'] = 1  # 将产生做空信号的那根K线的signal设置为-1，-1代表做空

    # 合并做多做空信号，去除重复信号
    df['signal_short'].fillna(method='ffill', inplace=True)
    df['signal_long'].fillna(method='ffill', inplace=True)
    df['signal'] = df[['signal_long', 'signal_short'
                       ]].sum(axis=1, min_count=1,
                              skipna=True)  # 若你的pandas版本是最新的，请使用本行代码代替上面一行
    df['signal'].fillna(value=0, inplace=True)

    # ===根据bias，修改开仓时间
    df['temp'] = df['signal']

    # # 将原始信号做多时，当bias大于阀值，设置为空
    # condition1 = (df['signal'] == 1)
    # condition2 = (df['bias'] > df['bias_pct'])
    # df.loc[condition1 & condition2, 'temp'] = None

    # # 将原始信号做空时，当bias大于阀值，设置为空
    # condition1 = (df['signal'] == -1)
    # condition2 = (df['bias'] < -df['bias_pct'])
    # df.loc[condition1 & condition2, 'temp'] = None

    # 原始信号刚开仓，并且大于阀值，将信号设置为0
    condition1 = (df['signal'] != df['signal'].shift(1))
    condition2 = (df['temp'].isnull())
    df.loc[condition1 & condition2, 'temp'] = 0

    # 使用之前的信号补全原始信号
    df['temp'].fillna(method='ffill', inplace=True)
    df['signal'] = df['temp']

    temp = df[['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp

    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
    ), signal_data


def signal_adapt_kc(*args):
    df = args[0]
    n = args[1]
    n2 = 3 * n
    df['TR'] = np.max([
        abs(df['high'] - df['low']),
        abs(df['high'] - df['close'].shift(1)),
        abs(df['close'].shift(1) - df['low'].shift(1))
    ],
                      axis=0)
    df['ATR'] = df['TR'].rolling(n2, min_periods=1).mean()
    df['median2'] = df['close'].ewm(span=180, min_periods=1,
                                    adjust=False).mean()
    df['z_score'] = abs(df['close'] - df['median2']) / df['ATR']
    df['m'] = df['z_score'].rolling(window=n2).max().shift()
    df['upper2'] = df['median2'] + df['ATR'] * df['m']
    df['lower2'] = df['median2'] - df['ATR'] * df['m']

    # condition_long = df['close'] > df['upper2']
    # condition_short = df['close'] < df['lower2']
    '''
    计算KC
    TR=MAX(ABS(HIGH-LOW),ABS(HIGH-REF(CLOSE,1)),ABS(REF(CLOSE,1)-REF(LOW,1)))
    ATR=MA(TR,N)
    Middle=EMA(CLOSE,20)
    自适应转换
    UPPER=MIDDLE+2*ATR
    LOWER=MIDDLE-2*ATR
    '''
    # 基于价格因素计算KC通道
    df['TR'] = np.max([
        abs(df['high'] - df['low']),
        abs(df['high'] - df['close'].shift(1)),
        abs(df['close'].shift(1) - df['low'].shift(1))
    ],
                      axis=0)
    df['ATR'] = df['TR'].rolling(n, min_periods=1).mean()
    df['median'] = df['close'].ewm(span=20, min_periods=1, adjust=False).mean()
    df['z_score'] = abs(df['close'] - df['median']) / df['ATR']
    df['m'] = df['z_score'].rolling(window=n).max().shift()
    df['upper'] = df['median'] + df['ATR'] * df['m']
    df['lower'] = df['median'] - df['ATR'] * df['m']

    condition_long = df['upper'] > df['upper2']
    condition_short = df['lower'] < df['lower2']

    # 找出做多信号
    condition1 = (df['close'] > df['upper']) & (df['close'].shift(1) <=
                                                df['upper'].shift(1))
    df.loc[(condition1 & condition_long), 'signal_long'] = 1

    # 找出做多平仓信号
    condition1 = (df['upper'] < df['upper2']) & (df['upper'].shift(1) >=
                                                 df['upper2'].shift(1))
    condition2 = (df['close'] < df['lower']) & (df['close'].shift() >=
                                                df['lower'].shift())
    df.loc[(condition1 | condition2), 'signal_long'] = 0

    # 找出做空信号
    condition1 = (df['close'] < df['lower']) & (df['close'].shift(1) >=
                                                df['lower'].shift(1))
    df.loc[condition1 & condition_short, 'signal_short'] = -1

    # 找出做空平仓信号
    condition1 = (df['lower'] > df['lower2']) & (df['lower'].shift(1) <=
                                                 df['lower2'].shift(1))
    condition2 = (df['close'] > df['upper']) & (df['close'].shift() <=
                                                df['upper'].shift())
    df.loc[condition1 | condition2, 'signal_short'] = 0
    # ========================= 固定代码 =========================

    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1,
                                                           min_count=1,
                                                           skipna=True)

    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    # ========================= 固定代码 =========================
    # 删除无关变量
    df.drop([
        'TR', 'ATR', 'm', 'z_score', 'median2', 'signal_long', 'signal_short'
    ],
            axis=1,
            inplace=True)

    df['median'].fillna(method='bfill', inplace=True)
    df['upper'].fillna(method='bfill', inplace=True)
    df['upper2'].fillna(method='bfill', inplace=True)
    df['lower'].fillna(method='bfill', inplace=True)
    df['lower2'].fillna(method='bfill', inplace=True)

    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
    ), df['upper2'].tolist(), df['lower2'].tolist(), signal_data


def signal_adapt_kc_with_rsi(*args):
    df = args[0]
    n = args[1]
    # n2 = 3 * n
    # df['TR'] = np.max([abs(df['high'] - df['low']), abs(df['high'] - df['low'].shift(1)),
    #                 abs(df['close'].shift(1) - df['low'].shift(1))], axis=0)
    # df['ATR'] = df['TR'].rolling(n2, min_periods=1).mean()
    # df['median2'] = df['close'].ewm(span=180, min_periods=1, adjust=False).mean()
    # df['z_score'] = abs(df['close'] - df['median2']) / df['ATR']
    # df['m'] = df['z_score'].rolling(window=n2).max().shift(1)
    # df['upper2'] = df['median2'] + df['ATR'] * df['m']
    # df['lower2'] = df['median2'] - df['ATR'] * df['m']
    '''
    计算KC
    TR=MAX(ABS(HIGH-LOW),ABS(HIGH-REF(CLOSE,1)),ABS(REF(CLOSE,1)-REF(LOW,1)))
    ATR=MA(TR,N)
    Middle=EMA(CLOSE,20)
    自适应转换
    UPPER=MIDDLE+2*ATR
    LOWER=MIDDLE-2*ATR
    '''
    # 基于价格因素计算KC通道
    df['TR'] = np.max([
        abs(df['high'] - df['low']),
        abs(df['high'] - df['close'].shift(1)),
        abs(df['close'].shift(1) - df['low'].shift(1))
    ],
                      axis=0)
    df['ATR'] = df['TR'].rolling(n, min_periods=1).mean()
    df['median'] = df['close'].ewm(span=20, min_periods=1, adjust=False).mean()
    df['z_score'] = abs(df['close'] - df['median']) / df['ATR']
    df['m'] = df['z_score'].rolling(window=n).max().shift(1)
    df['upper'] = df['median'] + df['ATR'] * df['m']
    df['lower'] = df['median'] - df['ATR'] * df['m']

    # RSI
    # CLOSEUP=IF(CLOSE>REF(CLOSE,1),CLOSE-REF(CLOSE,1),0)
    df['closeup'] = np.where(df['close'] > df['close'].shift(),
                             df['close'] - df['close'].shift(), 0)
    # # CLOSEDOWN=IF(CLOSE<REF(CLOSE,1),ABS(CLOSE-REF(CL OSE,1)),0)
    df['closedown'] = np.where(df['close'] < df['close'].shift(),
                               abs(df['close'] - df['close'].shift()), 0)
    # # CLOSEUP_MA=SMA(CLOSEUP,N,1)
    # df['data'].ewm(alpha=1 / 2, adjust=False).mean()
    df['closeup_ma'] = df['closeup'].ewm(alpha=1 / 2, adjust=False).mean()
    # # CLOSEDOWN_MA=SMA(CLOSEDOWN,N,1)
    df['closedown_ma'] = df['closedown'].ewm(alpha=1 / 2, adjust=False).mean()
    # # RSI=100*CLOSEUP_MA/(CLOSEUP_MA+CLOSEDOWN_MA)
    df['rsi'] = 100 * df['closeup_ma'] / (df['closeup_ma'] +
                                          df['closedown_ma'])
    # RSI_MIDDLE=MA(RSI,N)
    # df['rsi_middle'] = df['rsi'].rolling(n, min_periods=1).mean().shift()
    # # RSI_UPPER=RSI_MIDDLE+PARAM*STD(RSI,N)
    # df['z_score'] = abs(df['closeup_ma'] - df['rsi_middle']) / df['rsi']
    # df['m'] = df['z_score'].rolling(window=n).max().shift()
    # df['rsi_std'] = df['rsi'].rolling(n, min_periods=1).std(ddof=0)
    # # RSI_LOWER=RSI_MIDDLE-PARAM*STD(RSI,N)
    # df['rsi_lower'] = df['rsi_middle'] - df['m'] * df['rsi_std']
    # df['rsi_upper'] = df['rsi_middle'] + df['m'] * df['rsi_std']
    # 找出做多信号
    condition1 = (df['close'] > df['upper']) & (
        df['close'].shift(1) <= df['upper'].shift(1)) & (df['rsi'] > 70)
    # df.loc[(condition1 & condition_long), 'signal_long'] = 1
    df.loc[(condition1), 'signal_long'] = 1

    # 找出做多平仓信号
    # condition1 = (df['upper'] < df['upper2']) & (df['upper'].shift(1) >= df['upper2'].shift(1))
    condition1 = (df['rsi'] < 65)
    condition2 = (df['close'] < df['lower']) & (df['close'].shift() >=
                                                df['lower'].shift())
    df.loc[(condition1 & condition2), 'signal_long'] = 0

    # 找出做空信号
    condition1 = (df['close'] < df['lower']) & (
        df['close'].shift(1) >= df['lower'].shift(1)) & (df['rsi'] < 30)
    # df.loc[condition1 & condition_short, 'signal_short'] = -1
    df.loc[condition1, 'signal_short'] = -1

    # 找出做空平仓信号
    # condition1 = (df['lower'] > df['lower2']) & (df['lower'].shift(1) <= df['lower2'].shift(1))
    condition1 = (df['rsi'] > 35)
    condition2 = (df['close'] > df['upper']) & (df['close'].shift() <=
                                                df['upper'].shift())
    df.loc[condition1 & condition2, 'signal_short'] = 0

    # ========================= 固定代码 =========================

    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1,
                                                           min_count=1,
                                                           skipna=True)

    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    # ========================= 固定代码 =========================

    # 删除无关变量
    df.drop(['TR', 'ATR', 'm', 'z_score', 'signal_long', 'signal_short'],
            axis=1,
            inplace=True)

    df['median'].fillna(method='bfill', inplace=True)
    df['upper'].fillna(method='bfill', inplace=True)
    df['lower'].fillna(method='bfill', inplace=True)

    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
    ), signal_data


def signal_mike(*args):
    df = args[0]
    n = args[1]
    df['typ'] = (df['close'] + df['high'] + df['low']) / 3
    df['hh'] = df['high'].rolling(n, min_periods=1).max()
    df['ll'] = df['low'].rolling(n, min_periods=1).min()

    df['sr'] = df['hh'] * 2 - df['ll']
    df['mr'] = df['typ'] + df['hh'] - df['ll']
    df['wr'] = df['typ'] * 2 - df['ll']

    df['ws'] = df['typ'] * 2 - df['hh']
    df['ms'] = df['typ'] - (df['hh'] - df['ll'])
    df['ss'] = df['ll'] * 2 - df['hh']

    condtion1 = (df['close'] < df['ws'].shift()) & (df['close'] >
                                                    df['ms'].shift())
    condtion2 = df['close'] > df['sr'].shift()
    df.loc[(condtion1 | condtion2), 'signal_long'] = 1

    condtion1 = (df['close'] > df['wr'].shift()) & (df['close'] <
                                                    df['mr'].shift())
    condtion2 = df['close'] < df['ss'].shift()
    df.loc[condtion1 | condtion2, 'signal_short'] = -1

    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1,
                                                           min_count=1,
                                                           skipna=True)

    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]

    df['signal'] = temp['signal']
    # 删除无关变量
    df.drop([
        'typ', 'hh', 'll', 'sr', 'mr', 'wr', 'ws', 'ms', 'ss', 'signal_long',
        'signal_short'
    ],
            axis=1,
            inplace=True)
    signal_data = generate_signal_data(df)
    return df, signal_data


def mike_stop_with_bias(*args):
    df = args[0]
    n = args[1]
    # stop = para[1]
    n2 = 4 * 24 * 20  # 20日
    # 计算 mike 指标
    df['typ'] = (df['close'] + df['high'] + df['low']) / 3
    df['hh'] = df['high'].rolling(n, min_periods=1).max()
    df['ll'] = df['low'].rolling(n, min_periods=1).min()

    # 计算 bias 指标
    df['ma'] = df['close'].rolling(window=n2, min_periods=1).mean()
    # df['bias'] = (df['close'] - df['ma']) / df['ma'] * 100

    df['sr'] = df['hh'] * 2 - df['ll']
    df['mr'] = df['typ'] + df['hh'] - df['ll']
    df['wr'] = df['typ'] * 2 - df['ll']

    df['ws'] = df['typ'] * 2 - df['hh']
    df['ms'] = df['typ'] - (df['hh'] - df['ll'])
    df['ss'] = df['ll'] * 2 - df['hh']

    close = [float(x) for x in df['close']]
    df['median'] = talib.DEMA(np.array(close), timeperiod=n)

    # 当收盘价在初级支撑线与中级支撑线之间或者突破强力压力线时，平空做多；
    cond1 = (df['close'] < df['ws'].shift(1)) & (df['close'] >
                                                 df['ms'].shift(1))
    cond2 = df['close'] > df['sr'].shift(1)
    df.loc[cond1 | cond2, 'signal_long'] = 1
    # bias大于一定值 平多
    # df.loc[df['bias'] > stop, 'signal_long'] = 0
    # 找出做多平仓信号， 触发条件为 穿中轨 或 回撤超过阈值 二者之一
    condition_sell = (df['close'] < df['median']) & (
        df['close'].shift() >= df['median'].shift())  # k线下穿中轨
    df.loc[condition_sell, 'signal_long'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # 当收盘价在初级压力线和中间压力之间或者跌破强力支撑线时，平多做空。
    cond3 = (df['close'] > df['wr'].shift(1)) & (df['close'] <
                                                 df['mr'].shift(1))
    cond4 = df['close'] < df['ss'].shift(1)
    df.loc[cond3 | cond4, 'signal_short'] = -1
    # bias小于一定值 平空
    # df.loc[df['bias'] < -stop, 'signal_short'] = 0
    # ===找出做空平仓

    condition_cover = (df['close'] > df['median']) & (
        df['close'].shift() <= df['median'].shift())  # K线上穿中轨
    df.loc[condition_cover, 'signal_short'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # 合并做多做空信号，去除重复信号
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1,
                                                           min_count=1,
                                                           skipna=True)
    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    # 删除无关变量
    df.drop([
        'typ', 'hh', 'll', 'sr', 'mr', 'wr', 'ws', 'ms', 'ss', 'signal_long',
        'signal_short'
    ],
            axis=1,
            inplace=True)

    signal_data = generate_signal_data(df)
    return df, signal_data


def signal_dc_tunnel(*args):
    # 基础dc通道
    df = args[0]
    n = args[1]

    df['mean'] = df['close'].rolling(n).mean()
    df['max'] = df['close'].rolling(n).max().shift()
    df['min'] = df['close'].rolling(n).min().shift()

    factor = "close"

    # 做多信号
    condition1 = df[factor] > df['max']
    condition2 = df[factor].shift() <= df['max'].shift()
    df.loc[condition1 & condition2, 'signal_long'] = 1  # 1代表做多
    # 平多信号
    condition1 = df[factor] < df['mean']
    condition2 = df[factor].shift() >= df['mean'].shift()
    df.loc[condition1 & condition2, 'signal_long'] = 0
    # 做空信号
    condition1 = df[factor] < df['min']
    condition2 = df[factor].shift() >= df['min'].shift()
    df.loc[condition1 & condition2, 'signal_short'] = -1
    # 平空信号
    condition1 = df[factor] > df['mean']
    condition2 = df[factor].shift() <= df['mean'].shift()
    df.loc[condition1 & condition2, 'signal_short'] = 0

    # ===将long和short合并为signal
    df['signal_short'].fillna(method='ffill', inplace=True)
    df['signal_long'].fillna(method='ffill', inplace=True)
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1)
    df['signal'].fillna(value=0, inplace=True)

    temp = df[['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp
    df['mean'].fillna(method='bfill', inplace=True)
    df['max'].fillna(method='bfill', inplace=True)
    df['min'].fillna(method='bfill', inplace=True)
    signal_data = generate_signal_data(df)
    return df, df['mean'].tolist(), df['max'].tolist(), df['min'].tolist(
    ), signal_data


def signal_dc_flash_with_stop_lose(*args):
    # J神dc闪电侠
    """
    n： 时间窗口参数
    stop_loss_pct： 止损百分比参数
    DC上轨：n天收盘价的最大值
    DC下轨：n天收盘价的最小值
    当收盘价由下向上穿过DC上轨的时候，做多；
    当收盘价由上向下穿过DC下轨的时候，做空；
    flash 平仓。

    :param df:  原始数据
    :param para:  参数，[n, stop_lose]
    :param ma_dict: 均线ma缓存
    :return:
    """
    df = args[0]
    n = args[1]
    ma_dict = {}
    stop_loss_pct = 10

    df['signal'] = np.nan
    holding_times_min = 10

    df['median'] = df['close'].rolling(n, min_periods=1).mean()
    df['flash_stop_win'] = df['median'].copy()
    df['upper'] = df['close'].rolling(window=n).max().shift(1)
    df['lower'] = df['close'].rolling(window=n).min().shift(1)
    df['mtm'] = df['close'] / df['close'].shift(n) - 1

    df['c1'] = df['high'] - df['low']
    df['c2'] = abs(df['high'] - df['close'].shift(1))
    df['c3'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['c1', 'c2', 'c3']].max(axis=1)
    df['atr'] = df['tr'].rolling(window=n, min_periods=1).mean()

    condition1 = (df['close'] > df['upper']) & (df['mtm'] > 0)
    condition2 = df['close'].shift(1) <= df['upper'].shift(1)
    df.loc[condition1 & condition2, 'signal_long'] = 1

    condition1 = df['close'] < df['median']
    condition2 = df['close'].shift(1) >= df['median'].shift(1)
    df.loc[condition1 & condition2, 'signal_long'] = 0

    condition1 = (df['close'] < df['lower']) & (df['mtm'] < 0)
    condition2 = df['close'].shift(1) >= df['lower'].shift(1)
    df.loc[condition1 & condition2, 'signal_short'] = -1

    condition1 = df['close'] > df['median']
    condition2 = df['close'].shift(1) <= df['median'].shift(1)
    df.loc[condition1 & condition2, 'signal_short'] = 0

    info_dict = {
        'pre_signal': 0,
        'stop_lose_price': None,
        'holding_times': 0,
        'stop_win_times': 0,
        'stop_win_price': 0
    }

    for i in range(df.shape[0]):
        if info_dict['pre_signal'] == 0:
            if df.at[i, 'signal_long'] == 1:
                df.at[i, 'signal'] = 1
                pre_signal = 1
                stop_lose_price = df.at[i, 'close'] * (1 - stop_loss_pct / 100)
                info_dict = {
                    'pre_signal': pre_signal,
                    'stop_lose_price': stop_lose_price,
                    'holding_times': 0,
                    'stop_win_times': 0,
                    'stop_win_price': 0
                }
            elif df.at[i, 'signal_short'] == -1:
                df.at[i, 'signal'] = -1
                pre_signal = -1
                stop_lose_price = df.at[i, 'close'] * (1 + stop_loss_pct / 100)
                info_dict = {
                    'pre_signal': pre_signal,
                    'stop_lose_price': stop_lose_price,
                    'holding_times': 0,
                    'stop_win_times': 0,
                    'stop_win_price': 0
                }
            else:
                info_dict = {
                    'pre_signal': 0,
                    'stop_lose_price': None,
                    'holding_times': 0,
                    'stop_win_times': 0,
                    'stop_win_price': 0
                }
        elif info_dict['pre_signal'] == 1:
            holding_times = info_dict['holding_times']
            if df.at[i, 'atr'] < df.at[i - 1, 'atr']:
                info_dict['holding_times'] = holding_times + 1
            if df.at[i, 'close'] > df.at[i - 1, 'close']:
                if holding_times > 0:
                    info_dict['holding_times'] = holding_times - 1
                else:
                    info_dict['holding_times'] = 0
            ma_temp = max(n - int(n / 50) * 10 * holding_times,
                          holding_times_min)
            if ma_temp in ma_dict:
                df_ma_temp = ma_dict[ma_temp]
            else:
                df_ma_temp = df['close'].rolling(ma_temp, min_periods=1).mean()
                ma_dict[ma_temp] = df_ma_temp

            df.at[i, 'flash_stop_win'] = df_ma_temp.at[i]

            if df.at[i, 'close'] < df.at[i, 'flash_stop_win']:
                if df.at[i, 'close'] > info_dict[
                        'stop_win_price'] or info_dict['stop_win_times'] == 0:
                    info_dict['stop_win_price'] = df.at[i, 'close']
                    info_dict[
                        'stop_win_times'] = info_dict['stop_win_times'] + 1
                    info_dict['holding_times'] = 0
                else:
                    df.at[i, 'signal_long'] = 0
            if (df.at[i, 'signal_long'] == 0) or (
                    df.at[i, 'close'] < info_dict['stop_lose_price']):
                df.at[i, 'signal'] = 0
                info_dict = {
                    'pre_signal': 0,
                    'stop_lose_price': None,
                    'holding_times': 0,
                    'stop_win_times': 0,
                    'stop_win_price': 0
                }
            if df.at[i, 'signal_short'] == -1:
                df.at[i, 'signal'] = -1
                pre_signal = -1
                stop_lose_price = df.at[i, 'close'] * (1 + stop_loss_pct / 100)
                info_dict = {
                    'pre_signal': pre_signal,
                    'stop_lose_price': stop_lose_price,
                    'holding_times': 0,
                    'stop_win_times': 0,
                    'stop_win_price': 0
                }
        elif info_dict['pre_signal'] == -1:
            holding_times = info_dict['holding_times']
            if df.at[i, 'atr'] < df.at[i - 1, 'atr']:
                info_dict['holding_times'] = holding_times + 1
            if df.at[i, 'close'] < df.at[i - 1, 'close']:
                if holding_times > 0:
                    info_dict['holding_times'] = holding_times - 1
                else:
                    info_dict['holding_times'] = 0
            ma_temp = max(n - int(n / 50) * 10 * holding_times,
                          holding_times_min)
            if ma_temp in ma_dict:
                df_ma_temp = ma_dict[ma_temp]
            else:
                df_ma_temp = df['close'].rolling(ma_temp, min_periods=1).mean()
                ma_dict[ma_temp] = df_ma_temp
            df.at[i, 'flash_stop_win'] = df_ma_temp.at[i]
            if df.at[i, 'close'] > df.at[i, 'flash_stop_win']:
                if df.at[i, 'close'] < info_dict[
                        'stop_win_price'] or info_dict['stop_win_times'] == 0:
                    info_dict['stop_win_price'] = df.at[i, 'close']
                    info_dict[
                        'stop_win_times'] = info_dict['stop_win_times'] + 1
                    info_dict['holding_times'] = 0
                else:
                    df.at[i, 'signal_short'] = 0

            if (df.at[i, 'signal_short'] == 0) or (
                    df.at[i, 'close'] > info_dict['stop_lose_price']):
                df.at[i, 'signal'] = 0
                info_dict = {
                    'pre_signal': 0,
                    'stop_lose_price': None,
                    'holding_times': 0,
                    'stop_win_times': 0,
                    'stop_win_price': 0
                }
            if df.at[i, 'signal_long'] == 1:
                df.at[i, 'signal'] = 1
                pre_signal = 1
                stop_lose_price = df.at[i, 'close'] * (1 - stop_loss_pct / 100)
                info_dict = {
                    'pre_signal': pre_signal,
                    'stop_lose_price': stop_lose_price,
                    'holding_times': 0,
                    'stop_win_times': 0,
                    'stop_win_price': 0
                }
        else:
            raise ValueError('不可能出现其他的情况，如果出现，说明代码逻辑有误，报错')
    df['pos'] = df['signal'].shift()
    df['pos'].fillna(method='ffill', inplace=True)
    df['pos'].fillna(value=0, inplace=True)
    signal_data = generate_signal_data(df)
    return df, signal_data


def signal_dual_thrust(*args):
    # dual thrust
    df = args[0]
    n = args[1]

    df['hh'] = df['high'].rolling(n, min_periods=1).max()
    df['lc'] = df['close'].rolling(n, min_periods=1).min()
    df['hc'] = df['close'].rolling(n, min_periods=1).max()
    df['ll'] = df['low'].rolling(n, min_periods=1).min()

    condition1 = (df['hh'] - df['lc']) > (df['hc'] - df['ll'])
    condition2 = (df['hh'] - df['lc']) <= (df['hc'] - df['ll'])

    df.loc[condition1, 'range'] = df['hh'] - df['lc']
    df.loc[condition2, 'range'] = df['hc'] - df['ll']

    df['upper_open'] = 2 * abs(df['close'] -
                               df['open'].shift()) / df['range'].rolling(
                                   n, min_periods=1).max()
    df['lower_open'] = 2 * abs(df['open'].shift() -
                               df['close']) / df['range'].rolling(
                                   n, min_periods=1).max()

    df['upper'] = df['open'].shift() + df['upper_open'] * df['range']
    df['lower'] = df['open'].shift() - df['lower_open'] * df['range']

    #close >open + upper_open * range  upper_open <(close - open)/range
    #close <open - lower_open*range lower_open< (open -close)/range
    condition = df['close'] > df['upper']
    # condition &= df['close'].shift()  <= df['upper'].shift()
    # condition &= (df['upper'].shift() - df['lower'].shift())  > df['high'].shift() - df['low'].shift()
    condition &= (df['upper'].shift() -
                  df['lower'].shift()) / df['upper'].shift() > 0.05

    df.loc[condition, 'signal_long'] = 1

    condition = df['close'] < df['lower']
    # condition &= df['close'].shift()  >= df['lower'].shift()
    # condition &= (df['upper'].shift() - df['lower'].shift())  > df['high'].shift() - df['low'].shift()
    condition &= (df['upper'].shift() -
                  df['lower'].shift()) / df['upper'].shift() > 0.05

    df.loc[condition, 'signal_short'] = -1

    condition = (df['upper'].shift() -
                 df['lower'].shift()) < df['high'].shift() - df['low'].shift()
    condition |= (df['upper'].shift() -
                  df['lower'].shift()) / df['upper'].shift() < 0.05

    df.loc[condition, 'signal_short'] = 0
    df.loc[condition, 'signal_long'] = 0

    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1,
                                                           min_count=1,
                                                           skipna=True)

    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]

    df['signal'] = temp['signal']

    signal_data = generate_signal_data(df)
    return df, signal_data


def signal_takerby(*args):
    df = args[0]
    n = args[1]

    df = df.copy()
    df['volume'] = df['quote_volume'].rolling(n, min_periods=1).sum()
    df['buy_volume'] = df['taker_buy_quote_asset_volume'].rolling(
        n, min_periods=1).sum()
    df['takerby'] = df['buy_volume'] / df['volume']

    df['takerby_h'] = df['takerby'].rolling(n, min_periods=1).max()
    df['takerby_l'] = df['takerby'].rolling(n, min_periods=1).min()
    df['takerby_c'] = df['takerby'].rolling(n, min_periods=1).mean()

    df['takerby_c1'] = df['takerby_h'] - df['takerby_l']
    df['takerby_c2'] = abs(df['takerby_h'] - df['takerby_c'].shift(1))
    df['takerby_c3'] = abs(df['takerby_l'] - df['takerby_c'].shift(1))

    df['takerby_tr'] = df[['takerby_c1', 'takerby_c2',
                           'takerby_c3']].max(axis=1)
    df['takerby_atr'] = df['takerby_tr'].rolling(window=n,
                                                 min_periods=1).mean()

    # 删除无关变量
    df.drop([
        'volume', 'buy_volume', 'takerby', 'takerby_h', 'takerby_l',
        'takerby_c', 'takerby_c1', 'takerby_c2', 'takerby_c3', 'takerby_tr'
    ],
            axis=1,
            inplace=True)
    return df


def signal_bias(*args):
    df = args[0]
    n = args[1]

    df['ma'] = df['close'].rolling(n, min_periods=1).mean()
    df['bias_c'] = (df['close'] / df['ma'] - 1)

    df['ma'] = df['high'].rolling(n, min_periods=1).mean()
    df['bias_h'] = (df['high'] / df['ma'] - 1)

    df['ma'] = df['low'].rolling(n, min_periods=1).mean()
    df['bias_l'] = (df['low'] / df['ma'] - 1)

    df['bias_c1'] = df['bias_h'] - df['bias_l']
    df['bias_c2'] = abs(df['bias_h'] - df['bias_c'].shift(1))
    df['bias_c3'] = abs(df['bias_l'] - df['bias_c'].shift(1))
    df['bias_tr'] = df[['bias_c1', 'bias_c2', 'bias_c3']].max(axis=1)
    df['bias_atr'] = df['bias_tr'].rolling(window=n, min_periods=1).mean()

    # 参考ATR，对MTM mean指标，计算波动率因子
    df['bias_l_mean'] = df['bias_l'].rolling(window=n, min_periods=1).mean()
    df['bias_h_mean'] = df['bias_h'].rolling(window=n, min_periods=1).mean()
    df['bias_c_mean'] = df['bias_c'].rolling(window=n, min_periods=1).mean()
    df['bias_c1'] = df['bias_h_mean'] - df['bias_l_mean']
    df['bias_c2'] = abs(df['bias_h_mean'] - df['bias_c_mean'].shift(1))
    df['bias_c3'] = abs(df['bias_l_mean'] - df['bias_c_mean'].shift(1))
    df['bias_tr'] = df[['bias_c1', 'bias_c2', 'bias_c3']].max(axis=1)
    df['bias_atr_mean'] = df['bias_tr'].rolling(window=n, min_periods=1).mean()

    # 删除无关变量
    df.drop([
        'ma', 'bias_c', 'bias_h', 'bias_l', 'bias_c1', 'bias_c2', 'bias_c3',
        'bias_tr', 'bias_l_mean', 'bias_h_mean', 'bias_c_mean'
    ],
            axis=1,
            inplace=True)
    return df


def signal_zhangdiefu_std(*args):
    df = args[0]
    n = args[1]

    # 涨跌幅std，振幅的另外一种形式
    change = df['close'].pct_change()
    df['zhf_c'] = pd.Series(change).rolling(n).std()

    change = df['high'].pct_change()
    df['zhf_h'] = pd.Series(change).rolling(n).std()

    change = df['low'].pct_change()
    df['zhf_l'] = pd.Series(change).rolling(n).std()

    df['zhf_c1'] = df['zhf_h'] - df['zhf_l']
    df['zhf_c2'] = abs(df['zhf_h'] - df['zhf_c'].shift(1))
    df['zhf_c3'] = abs(df['zhf_l'] - df['zhf_c'].shift(1))
    df['zhf_tr'] = df[['zhf_c1', 'zhf_c2', 'zhf_c3']].max(axis=1)
    df['zdf_atr'] = df['zhf_tr'].rolling(window=n, min_periods=1).mean()

    # 参考ATR，对MTM mean指标，计算波动率因子
    df['zdf_l_mean'] = df['zhf_l'].rolling(window=n, min_periods=1).mean()
    df['zdf_h_mean'] = df['zhf_h'].rolling(window=n, min_periods=1).mean()
    df['zdf_c_mean'] = df['zhf_c'].rolling(window=n, min_periods=1).mean()
    df['zdf_c1'] = df['zdf_h_mean'] - df['zdf_l_mean']
    df['zdf_c2'] = abs(df['zdf_h_mean'] - df['zdf_c_mean'].shift(1))
    df['zdf_c3'] = abs(df['zdf_l_mean'] - df['zdf_c_mean'].shift(1))
    df['zdf_tr'] = df[['zdf_c1', 'zdf_c2', 'zdf_c3']].max(axis=1)
    df['zdf_atr_mean'] = df['zdf_tr'].rolling(window=n, min_periods=1).mean()

    # 删除无关变量
    df.drop([
        'zhf_c', 'zhf_h', 'zhf_l', 'zhf_c1', 'zhf_c2', 'zhf_c3', 'zhf_tr',
        'zdf_l_mean', 'zdf_h_mean', 'zdf_c_mean'
    ],
            axis=1,
            inplace=True)
    return df


def signal_vwap(*args):
    df = args[0]
    n = args[1]

    df['vwap'] = df['quote_volume'] / df['volume']  # 在周期内成交额除以成交量等于成交均价
    ma = df['vwap'].rolling(n, min_periods=1).mean()  # 求移动平均线
    df['vwapbias_c'] = df['vwap'] / (ma + eps) - 1  # 去量纲

    ma = df['vwap'].rolling(n, min_periods=1).max()  # 求移动平均线
    df['vwapbias_h'] = df['vwap'] / (ma + eps) - 1  # 去量纲

    ma = df['vwap'].rolling(n, min_periods=1).min()  # 求移动平均线
    df['vwapbias_l'] = df['vwap'] / (ma + eps) - 1  # 去量纲

    df['vwapbias_c1'] = df['vwapbias_h'] - df['vwapbias_l']
    df['vwapbias_c2'] = abs(df['vwapbias_h'] - df['vwapbias_c'].shift(1))
    df['vwapbias_c3'] = abs(df['vwapbias_l'] - df['vwapbias_c'].shift(1))
    df['vwapbias_tr'] = df[['vwapbias_c1', 'vwapbias_c2',
                            'vwapbias_c3']].max(axis=1)
    df['vwapbias_atr'] = df['vwapbias_tr'].rolling(window=n,
                                                   min_periods=1).mean()

    df['vwapbias_l_mean'] = df['vwapbias_l'].rolling(window=n,
                                                     min_periods=1).mean()
    df['vwapbias_h_mean'] = df['vwapbias_h'].rolling(window=n,
                                                     min_periods=1).mean()
    df['vwapbias_c_mean'] = df['vwapbias_c'].rolling(window=n,
                                                     min_periods=1).mean()
    df['vwapbias_c1'] = df['vwapbias_h_mean'] - df['vwapbias_l_mean']
    df['vwapbias_c2'] = abs(df['vwapbias_h_mean'] -
                            df['vwapbias_c_mean'].shift(1))
    df['vwapbias_c3'] = abs(df['vwapbias_l_mean'] -
                            df['vwapbias_c_mean'].shift(1))
    df['vwapbias_tr'] = df[['vwapbias_c1', 'vwapbias_c2',
                            'vwapbias_c3']].max(axis=1)
    df['vwapbias_atr_mean'] = df['vwapbias_tr'].rolling(window=n,
                                                        min_periods=1).mean()
    # 删除无关变量
    df.drop([
        'vwap', 'vwapbias_c', 'vwapbias_h', 'vwapbias_l', 'vwapbias_c1',
        'vwapbias_c2', 'vwapbias_c3', 'vwapbias_l_mean', 'vwapbias_h_mean',
        'vwapbias_c_mean', 'vwapbias_tr'
    ],
            axis=1,
            inplace=True)
    return df


def signal_rsi(*args):
    df = args[0]
    n = args[1]

    # rsi
    df['rtn'] = df['close'].diff()
    df['up'] = np.where(df['rtn'] > 0, df['rtn'], 0)
    df['down'] = np.where(df['rtn'] < 0, abs(df['rtn']), 0)
    df['A'] = df['up'].rolling(n).sum()
    df['B'] = df['down'].rolling(n).sum()
    df['rsi_c'] = df['A'] / (df['A'] + df['B']) * 100

    df['rtn'] = df['high'].diff()
    df['up'] = np.where(df['rtn'] > 0, df['rtn'], 0)
    df['down'] = np.where(df['rtn'] < 0, abs(df['rtn']), 0)
    df['A'] = df['up'].rolling(n).sum()
    df['B'] = df['down'].rolling(n).sum()
    df['rsi_h'] = df['A'] / (df['A'] + df['B']) * 100

    df['rtn'] = df['low'].diff()
    df['up'] = np.where(df['rtn'] > 0, df['rtn'], 0)
    df['down'] = np.where(df['rtn'] < 0, abs(df['rtn']), 0)
    df['A'] = df['up'].rolling(n).sum()
    df['B'] = df['down'].rolling(n).sum()
    df['rsi_l'] = df['A'] / (df['A'] + df['B']) * 100

    df['rsi_c1'] = df['rsi_h'] - df['rsi_l']
    df['rsi_c2'] = abs(df['rsi_h'] - df['rsi_c'].shift(1))
    df['rsi_c3'] = abs(df['rsi_l'] - df['rsi_c'].shift(1))
    df['rsi_tr'] = df[['rsi_c1', 'rsi_c2', 'rsi_c3']].max(axis=1)
    df['rsi_atr'] = df['rsi_tr'].rolling(window=n, min_periods=1).mean()

    df['rsi_l_mean'] = df['rsi_l'].rolling(window=n, min_periods=1).mean()
    df['rsi_h_mean'] = df['rsi_h'].rolling(window=n, min_periods=1).mean()
    df['rsi_c_mean'] = df['rsi_c'].rolling(window=n, min_periods=1).mean()
    df['rsi_c1'] = df['rsi_h_mean'] - df['rsi_l_mean']
    df['rsi_c2'] = abs(df['rsi_h_mean'] - df['rsi_c_mean'].shift(1))
    df['rsi_c3'] = abs(df['rsi_l_mean'] - df['rsi_c_mean'].shift(1))
    df['rsi_tr'] = df[['rsi_c1', 'rsi_c2', 'rsi_c3']].max(axis=1)
    df['rsi_atr_mean'] = df['rsi_tr'].rolling(window=n, min_periods=1).mean()

    # 删除无关变量
    df.drop([
        'rtn', 'up', 'down', 'A', 'B', 'rsi_c', 'rsi_h', 'rsi_l', 'rsi_c_mean',
        'rsi_c1', 'rsi_c2', 'rsi_c3', 'rsi_c3', 'rsi_tr', 'rsi_l_mean',
        'rsi_h_mean'
    ],
            axis=1,
            inplace=True)
    return df


def signal_mtm(*args):
    df = args[0]
    n = args[1]

    df['mtm'] = df['close'] / df['close'].shift(n) - 1
    df['mtm_mean'] = df['mtm'].rolling(window=n, min_periods=1).mean()

    # 参考ATR，对MTM指标，计算波动率因子
    df['mtm_l'] = df['low'] / df['low'].shift(n) - 1
    df['mtm_h'] = df['high'] / df['high'].shift(n) - 1
    df['mtm_c'] = df['close'] / df['close'].shift(n) - 1
    df['mtm_c1'] = df['mtm_h'] - df['mtm_l']
    df['mtm_c2'] = abs(df['mtm_h'] - df['mtm_c'].shift(1))
    df['mtm_c3'] = abs(df['mtm_l'] - df['mtm_c'].shift(1))
    df['mtm_tr'] = df[['mtm_c1', 'mtm_c2', 'mtm_c3']].max(axis=1)
    df['mtm_atr'] = df['mtm_tr'].rolling(window=n, min_periods=1).mean()

    # 参考ATR，对MTM mean指标，计算波动率因子
    df['mtm_l_mean'] = df['mtm_l'].rolling(window=n, min_periods=1).mean()
    df['mtm_h_mean'] = df['mtm_h'].rolling(window=n, min_periods=1).mean()
    df['mtm_c_mean'] = df['mtm_c'].rolling(window=n, min_periods=1).mean()
    df['mtm_c1'] = df['mtm_h_mean'] - df['mtm_l_mean']
    df['mtm_c2'] = abs(df['mtm_h_mean'] - df['mtm_c_mean'].shift(1))
    df['mtm_c3'] = abs(df['mtm_l_mean'] - df['mtm_c_mean'].shift(1))
    df['mtm_tr'] = df[['mtm_c1', 'mtm_c2', 'mtm_c3']].max(axis=1)
    df['mtm_atr_mean'] = df['mtm_tr'].rolling(window=n, min_periods=1).mean()
    # 删除无关变量
    df.drop([
        'mtm', 'mtm_mean', 'mtm_l', 'mtm_h', 'mtm_c', 'mtm_c1', 'mtm_c2',
        'mtm_c3', 'mtm_tr', 'mtm_l_mean', 'mtm_h_mean', 'mtm_c1', 'mtm_c2',
        'mtm_c3', 'mtm_tr'
    ],
            axis=1,
            inplace=True)
    return df


def signal_cci(*args):
    df = args[0]
    n = args[1]

    df['tp'] = (df['high'] + df['low'] + df['close']) / 3
    df['ma'] = df['tp'].rolling(window=n, min_periods=1).mean()
    df['md'] = abs(df['close'] - df['ma']).rolling(window=n,
                                                   min_periods=1).mean()
    df['cci_c'] = (df['tp'] - df['ma']) / df['md'] / 0.015

    df['cci_mean'] = df['cci_c'].rolling(window=n, min_periods=1).mean()

    df['ma_h'] = df['tp'].rolling(window=n, min_periods=1).max()
    df['md_h'] = abs(df['close'] - df['ma_h']).rolling(window=n,
                                                       min_periods=1).max()
    df['cci_h'] = (df['tp'] - df['ma_h']) / df['md_h'] / 0.015

    df['ma_l'] = df['tp'].rolling(window=n, min_periods=1).min()
    df['md_l'] = abs(df['close'] - df['ma_l']).rolling(window=n,
                                                       min_periods=1).min()
    df['cci_l'] = (df['tp'] - df['ma_l']) / df['md_l'] / 0.015

    df['cci_c1'] = df['cci_h'] - df['cci_l']
    df['cci_c2'] = abs(df['cci_h'] - df['cci_c'].shift(1))
    df['cci_c3'] = abs(df['cci_l'] - df['cci_c'].shift(1))
    df['cci_tr'] = df[['cci_c1', 'cci_c2', 'cci_c3']].max(axis=1)
    df['cci_atr'] = df['cci_tr'].rolling(window=n, min_periods=1).mean()

    df['cci_l_mean'] = df['cci_l'].rolling(window=n, min_periods=1).mean()
    df['cci_h_mean'] = df['cci_h'].rolling(window=n, min_periods=1).mean()
    df['cci_c_mean'] = df['cci_c'].rolling(window=n, min_periods=1).mean()
    df['cci_c1'] = df['cci_h_mean'] - df['cci_l_mean']
    df['cci_c2'] = abs(df['cci_h_mean'] - df['cci_c_mean'].shift(1))
    df['cci_c3'] = abs(df['cci_l_mean'] - df['cci_c_mean'].shift(1))
    df['cci_tr'] = df[['cci_c1', 'cci_c2', 'cci_c3']].max(axis=1)
    df['cci_atr_mean'] = df['cci_tr'].rolling(window=n, min_periods=1).mean()
    # 删除无关变量
    df.drop([
        'tp', 'ma', 'md', 'cci_c', 'cci_mean', 'ma_h', 'md_h', 'cci_h', 'ma_l',
        'md_l', 'cci_l', 'cci_c1', 'cci_c2', 'cci_c3', 'cci_tr', 'cci_l_mean',
        'cci_h_mean', 'cci_c_mean'
    ],
            axis=1,
            inplace=True)
    return df


def signal_vixbw(*args):
    df = args[0]
    n = args[1]

    df['vix'] = df['close'] / df['close'].shift(n) - 1
    df['vix_median'] = df['vix'].rolling(window=n, min_periods=1).mean()
    df['vix_std'] = df['vix'].rolling(n, min_periods=1).std()
    df['vix_score'] = abs(df['vix'] - df['vix_median']) / df['vix_std']
    df['max'] = df['vix_score'].rolling(window=n,
                                        min_periods=1).mean().shift(1)
    df['min'] = df['vix_score'].rolling(window=n, min_periods=1).min().shift(1)
    df['vix_upper'] = df['vix_median'] + df['max'] * df['vix_std']
    df['vix_lower'] = df['vix_median'] - df['max'] * df['vix_std']
    df['vixbw'] = (df['vix_upper'] - df['vix_lower']) * np.sign(
        df['vix_median'].diff(n))
    # 删除无关变量
    df.drop([
        'vix', 'vix_median', 'vix_std', 'vix_score', 'min', 'vix_upper',
        'vix_lower'
    ],
            axis=1,
            inplace=True)
    return df


def signal_volume(*args):
    df = args[0]
    n = args[1]

    df['volume_c'] = df['quote_volume'].rolling(n, min_periods=1).mean()
    df['volume_l'] = df['quote_volume'].rolling(n, min_periods=1).min()
    df['volume_h'] = df['quote_volume'].rolling(n, min_periods=1).max()

    df['volume_c1'] = df['volume_h'] - df['volume_l']
    df['volume_c2'] = abs(df['volume_h'] - df['volume_c'].shift(1))
    df['volume_c3'] = abs(df['volume_l'] - df['volume_c'].shift(1))
    df['volume_tr'] = df[['volume_c1', 'volume_c2', 'volume_c3']].max(axis=1)
    df['volume_atr'] = df['volume_tr'].rolling(window=n, min_periods=1).mean()

    df['volume_l_mean'] = df['volume_l'].rolling(window=n,
                                                 min_periods=1).mean()
    df['volume_h_mean'] = df['volume_h'].rolling(window=n,
                                                 min_periods=1).mean()
    df['volume_c_mean'] = df['volume_c'].rolling(window=n,
                                                 min_periods=1).mean()
    df['volume_c1'] = df['volume_h_mean'] - df['volume_l_mean']
    df['volume_c2'] = abs(df['volume_h_mean'] - df['volume_c_mean'].shift(1))
    df['volume_c3'] = abs(df['volume_l_mean'] - df['volume_c_mean'].shift(1))
    df['volume_tr'] = df[['volume_c1', 'volume_c2', 'volume_c3']].max(axis=1)
    df['volume_atr_mean'] = df['volume_tr'].rolling(window=n,
                                                    min_periods=1).mean()
    # 删除无关变量
    df.drop([
        'volume_c', 'volume_l', 'volume_h', 'volume_c1', 'volume_c2',
        'volume_c3', 'volume_tr', 'volume_l_mean', 'volume_h_mean',
        'volume_c_mean'
    ],
            axis=1,
            inplace=True)
    return df


def adaptboll_with_cci(*args):
    '''
    cci_atr + cci_atr_mean
    '''
    df = args[0]
    n = args[1]
    n2 = 35 * n  #35

    df['median'] = df['close'].rolling(window=n2).mean()
    df['std'] = df['close'].rolling(n2,
                                    min_periods=1).std(ddof=0)  # ddof代表标准差自由度
    df['z_score'] = abs(df['close'] - df['median']) / df['std']
    df['m'] = df['z_score'].rolling(window=n2).mean()
    df['upper'] = df['median'] + df['std'] * df['m']
    df['lower'] = df['median'] - df['std'] * df['m']

    condition_long = df['close'] > df['upper']
    condition_short = df['close'] < df['lower']

    indicator = 'cci_atr'  #短线

    df = signal_cci(df, n)

    df[indicator] = df[indicator] * df['cci_atr_mean']  #1

    # 对新策略因子计算自适应布林
    df['median'] = df[indicator].rolling(window=n).mean()
    df['std'] = df[indicator].rolling(n, min_periods=1).apply(np.std)  # 配合精度修改std
    df['z_score'] = abs(df[indicator] - df['median']) / df['std']
    # df['m'] = df['z_score'].rolling(window=n).max().shift(1)
    # df['m'] = df['z_score'].rolling(window=n).mean()
    df['m'] = df['z_score'].rolling(window=n).min().shift(1)
    df['up'] = df['median'] + df['std'] * df['m']
    df['dn'] = df['median'] - df['std'] * df['m']

    # 突破上轨做多
    condition1 = df[indicator] > df['up']
    condition2 = df[indicator].shift(1) <= df['up'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_long'] = 1

    # 突破下轨做空
    condition1 = df[indicator] < df['dn']
    condition2 = df[indicator].shift(1) >= df['dn'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_short'] = -1

    # 均线平仓(多头持仓)
    condition1 = df[indicator] < df['median']
    condition2 = df[indicator].shift(1) >= df['median'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_long'] = 0

    # 均线平仓(空头持仓)
    condition1 = df[indicator] > df['median']
    condition2 = df[indicator].shift(1) <= df['median'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_short'] = 0

    df.loc[condition_long, 'signal_short'] = 0
    df.loc[condition_short, 'signal_long'] = 0

    # ===由signal计算出实际的每天持有仓位
    # signal的计算运用了收盘价，是每根K线收盘之后产生的信号，到第二根开盘的时候才买入，仓位才会改变。
    df['signal_short'].fillna(method='ffill', inplace=True)
    df['signal_long'].fillna(method='ffill', inplace=True)
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1)
    df['signal'].fillna(value=0, inplace=True)
    # df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1, min_count=1,
    #                                                        skipna=True)  # 若你的pandas版本是最新的，请使用本行代码代替上面一行

    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    df.drop(['signal_long', 'signal_short', 'z_score'], axis=1, inplace=True)

    signal_data = generate_signal_data(df)

    return df, signal_data


def adaptboll_with_mtm_cci_zdf(*args):
    '''
    cci_atr + cci_atr_mean + mtm_atr + zdf_atr_mean
    '''
    df = args[0]
    n = args[1]
    n2 = 35 * n  #35

    df['median'] = df['close'].rolling(window=n2).mean()
    df['std'] = df['close'].rolling(n2,
                                    min_periods=1).std(ddof=0)  # ddof代表标准差自由度
    df['z_score'] = abs(df['close'] - df['median']) / df['std']
    df['m'] = df['z_score'].rolling(window=n2).mean()
    df['upper'] = df['median'] + df['std'] * df['m']
    df['lower'] = df['median'] - df['std'] * df['m']

    condition_long = df['close'] > df['upper']
    condition_short = df['close'] < df['lower']

    # 基于价格atr，计算波动率因子wd_atr
    df['c1'] = df['high'] - df['low']
    df['c2'] = abs(df['high'] - df['close'].shift(1))
    df['c3'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['c1', 'c2', 'c3']].max(axis=1)
    df['atr'] = df['tr'].rolling(window=n, min_periods=1).mean()
    df['avg_price'] = df['close'].rolling(window=n, min_periods=1).mean()
    df['wd_atr'] = df['atr'] / df['avg_price']

    indicator = 'cci_atr'  #短线
    df = signal_zhangdiefu_std(df, n)
    df = signal_cci(df, n)
    df = signal_mtm(df, n)

    # mtm_mean 指标分别乘以三个波动率因子 2-10
    df[indicator] = df[indicator] * df['cci_atr_mean']
    df[indicator] = df[indicator] * df['mtm_atr']
    df[indicator] = df[indicator] * df['zdf_atr_mean']

    # 对新策略因子计算自适应布林
    df['median'] = df[indicator].rolling(window=n).mean()
    df['std'] = df[indicator].rolling(n, min_periods=1).apply(np.std)  # 配合精度修改std
    df['z_score'] = abs(df[indicator] - df['median']) / df['std']
    # df['m'] = df['z_score'].rolling(window=n).max().shift(1)
    # df['m'] = df['z_score'].rolling(window=n).mean()
    df['m'] = df['z_score'].rolling(window=n).min().shift(1)
    df['up'] = df['median'] + df['std'] * df['m']
    df['dn'] = df['median'] - df['std'] * df['m']

    # 突破上轨做多
    condition1 = df[indicator] > df['up']
    condition2 = df[indicator].shift(1) <= df['up'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_long'] = 1

    # 突破下轨做空
    condition1 = df[indicator] < df['dn']
    condition2 = df[indicator].shift(1) >= df['dn'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_short'] = -1

    # 均线平仓(多头持仓)
    condition1 = df[indicator] < df['median']
    condition2 = df[indicator].shift(1) >= df['median'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_long'] = 0

    # 均线平仓(空头持仓)
    condition1 = df[indicator] > df['median']
    condition2 = df[indicator].shift(1) <= df['median'].shift(1)
    condition = condition1 & condition2
    df.loc[condition, 'signal_short'] = 0

    df.loc[condition_long, 'signal_short'] = 0
    df.loc[condition_short, 'signal_long'] = 0

    # ===由signal计算出实际的每天持有仓位
    # signal的计算运用了收盘价，是每根K线收盘之后产生的信号，到第二根开盘的时候才买入，仓位才会改变。
    df['signal_short'].fillna(method='ffill', inplace=True)
    df['signal_long'].fillna(method='ffill', inplace=True)
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1)
    df['signal'].fillna(value=0, inplace=True)
    # df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1, min_count=1,
    #                                                        skipna=True)  # 若你的pandas版本是最新的，请使用本行代码代替上面一行

    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    df.drop(['signal_long', 'signal_short', 'z_score'], axis=1, inplace=True)

    signal_data = generate_signal_data(df)

    return df, signal_data


def signal_mtmbbw_bolling(*args):
    df = args[0]
    n = args[1]

    # 求上、下轨的倍数
    df['diff_c'] = df['close'] / df['close'].shift(n)

    # ===计算指标
    # 计算均线
    df['median'] = df['close'].rolling(n, min_periods=1).mean()
    # 计算上轨、下轨道
    df['std'] = df['close'].rolling(n, min_periods=1).std(ddof=0)  # ddof代表标准差自由度
    df['upper'] = df['median'] + df['std'] * (df['diff_c'] + df['diff_c'] ** (-1))
    df['lower'] = df['median'] - df['std'] * (df['diff_c'] + df['diff_c'] ** (-1))
    df['mouth'] = df['upper'] - df['lower']
    df['mouth_m'] = df['mouth'].rolling(n).mean()

    # ===计算信号
    # 找出做多信号
    condition1 = df['close'] > df['upper']  # 当前K线的收盘价 > 上轨
    condition2 = df['close'].shift(1) <= df['upper'].shift(1)  # 之前K线的收盘价 <= 上轨
    df.loc[condition1 & condition2, 'signal_long'] = 1  # 将产生做多信号的那根K线的signal设置为1，1代表做多

    # 找出做多平仓信号
    condition1 = df['mouth'] < df['mouth_m']
    condition2 = df['mouth'].shift(1) >= df['mouth_m'].shift(1)  # 之前K线的收盘价 >= 跌幅信号线
    condition3 = df['close'] < df['median']  # 当前K线的收盘价 < 跌幅信号线
    condition4 = df['close'].shift(1) >= df['median'].shift(1)  # 之前K线的收盘价 >= 跌幅信号线
    df.loc[(condition1 & condition2) | (condition3 & condition4), 'signal_long'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓
    # 找出做空信号
    condition1 = df['close'] < df['lower']  # 当前K线的收盘价 < 下轨
    condition2 = df['close'].shift(1) >= df['lower'].shift(1)  # 之前K线的收盘价 >= 下轨
    df.loc[condition1 & condition2, 'signal_short'] = -1  # 将产生做空信号的那根K线的signal设置为-1，-1代表做空

    # 找出做空平仓信号
    condition1 = df['mouth'] < df['mouth_m']
    condition2 = df['mouth'].shift(1) >= df['mouth_m'].shift(1)  # 之前K线的收盘价 >= 跌幅信号线
    condition3 = df['close'] > df['median']  # 当前K线的收盘价 > 涨幅信号线
    condition4 = df['close'].shift(1) <= df['median'].shift(1)  # 之前K线的收盘价 <= 涨幅信号线
    df.loc[(condition1 & condition2) | (condition3 & condition4), 'signal_short'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # 合并做多做空信号，去除重复信号
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1, min_count=1, skipna=True)  # 若你的pandas版本是最新的，请使用本行代码代替上面一行
    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    # ===删除无关变量
    df.drop(
        ['std', 'signal_long', 'signal_short', 'diff_c', 'mouth', 'mouth_m'], axis=1,
        inplace=True)
    
    df['median'].fillna(method='bfill', inplace=True)
    df['upper'].fillna(method='bfill', inplace=True)
    df['lower'].fillna(method='bfill', inplace=True)

    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
    ), signal_data

def keltner_channel_formatter(*args):
    df = args[0]
    n = args[1]
    indicator = args[2]
    '''
    计算KC
    TR=MAX(ABS(HIGH-LOW),ABS(HIGH-REF(CLOSE,1)),ABS(REF(CLOSE,1)-REF(LOW,1)))
    ATR=MA(TR,N)
    Middle=EMA(CLOSE,20)
    自适应转换
    UPPER=MIDDLE+2*ATR
    LOWER=MIDDLE-2*ATR
    '''
    # 基于指标计算KC通道
    df['kc_high'] = df[indicator].rolling(n).max().shift()
    df['kc_low'] = df[indicator].rolling(n).min().shift()
    
    df['TR'] = np.max([abs(df['kc_high'] - df['kc_low'])], axis=0)
    df['ATR'] = df['TR'].rolling(n, min_periods=1).mean()
    df['median'] = df[indicator].ewm(span=20, min_periods=1, adjust=False).mean()
    df['z_score'] = abs(df[indicator] - df['median']) / df['ATR']
    df['m'] = df['z_score'].rolling(window=n).max().shift(1)
    df['upper'] = df['median'] + df['ATR'] * df['m']
    df['lower'] = df['median'] - df['ATR'] * df['m']

    # 找出做多信号
    condition1 = (df[indicator] > df['upper'])
    condition2 = (df[indicator].shift() <= df['upper'].shift(1))
    df.loc[condition1 & condition2, 'signal_long'] = 1

    # 找出做多平仓信号
    condition1 = (df[indicator] < df['lower'])
    condition2 = (df[indicator].shift() >= df['lower'].shift())
    df.loc[condition1 & condition2, 'signal_long'] = 0

    # 找出做空信号
    condition1 = (df[indicator] < df['lower'])
    condition2 = (df[indicator].shift(1) >= df['lower'].shift(1))
    df.loc[condition1 & condition2, 'signal_short'] = -1

    # 找出做空平仓信号
    condition1 = (df[indicator] > df['upper'])
    condition2 = (df[indicator].shift() <= df['upper'].shift())
    df.loc[condition1 & condition2, 'signal_short'] = 0

    # ========================= 固定代码 =========================

    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1,
                                                           min_count=1,
                                                           skipna=True)

    temp = df[df['signal'].notnull()][['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp['signal']

    # ========================= 固定代码 =========================

    # 删除无关变量
    df.drop(['TR', 'ATR', 'kc_high', 'kc_low', 'm', 'z_score', 'signal_long', 'signal_short'],
            axis=1,
            inplace=True)

    df['median'].fillna(method='bfill', inplace=True)
    df['upper'].fillna(method='bfill', inplace=True)
    df['lower'].fillna(method='bfill', inplace=True)

    return df


def dc_tunnel_formatter(*args):
    # 基础dc通道模板
    df = args[0]
    n = args[1]
    indicator = args[2]

    df['mean'] = df[indicator].rolling(n).mean()
    df['max'] = df[indicator].rolling(n).max().shift()
    df['min'] = df[indicator].rolling(n).min().shift()

    # 做多信号
    condition1 = df[indicator] > df['max']
    condition2 = df[indicator].shift() <= df['max'].shift()
    df.loc[condition1 & condition2, 'signal_long'] = 1  # 1代表做多
    # 平多信号
    condition1 = df[indicator] < df['mean']
    condition2 = df[indicator].shift() >= df['mean'].shift()
    df.loc[condition1 & condition2, 'signal_long'] = 0
    # 做空信号
    condition1 = df[indicator] < df['min']
    condition2 = df[indicator].shift() >= df['min'].shift()
    df.loc[condition1 & condition2, 'signal_short'] = -1
    # 平空信号
    condition1 = df[indicator] > df['mean']
    condition2 = df[indicator].shift() <= df['mean'].shift()
    df.loc[condition1 & condition2, 'signal_short'] = 0

    # ===将long和short合并为signal
    df['signal_short'].fillna(method='ffill', inplace=True)
    df['signal_long'].fillna(method='ffill', inplace=True)
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1)
    df['signal'].fillna(value=0, inplace=True)

    temp = df[['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp
    df['mean'].fillna(method='bfill', inplace=True)
    df['max'].fillna(method='bfill', inplace=True)
    df['min'].fillna(method='bfill', inplace=True)
    
    return df


def bolling_formatter(*args):
    # 布林通道模板
    df = args[0]
    n = args[1]
    indicator = args[2]
    # 使用自适应 m
    df['median'] = df[indicator].rolling(n, min_periods=1).mean()
    df['std'] = df[indicator].rolling(n,
                                    min_periods=1).std(ddof=0)  # ddof代表标准差自由度
    df['z_score'] = abs(df[indicator] - df['median']) / df['std']
    # df['m'] = df['z_score'].rolling(window=n).max().shift()
    # df['m'] = df['z_score'].rolling(window=n).min().shift()
    df['m'] = df['z_score'].rolling(n, min_periods=1).mean().shift()

    # ===计算指标
    # 计算均线
    # 计算上轨、下轨道
    df['upper'] = df['median'] + df['m'] * df['std']
    df['lower'] = df['median'] - df['m'] * df['std']

    df.fillna(method='backfill', inplace=True)

    # 计算bias
    df['bias'] = df['close'] / df['median'] - 1

    # bias_pct 自适应
    df['bias_pct'] = abs(df['bias']).rolling(window=n,
                                             min_periods=1).max().shift()

    # ===计算原始布林策略信号
    # 找出做多信号
    condition1 = df[indicator] > df['upper']  # 当前K线的收盘价 > 上轨
    condition2 = df[indicator].shift(1) <= df['upper'].shift(1)  # 之前K线的收盘价 <= 上轨
    df.loc[condition1 & condition2,
           'signal_long'] = 1  # 将产生做多信号的那根K线的signal设置为1，1代表做多

    # 找出做多平仓信号
    condition1 = df[indicator] < df['median']  # 当前K线的收盘价 < 中轨
    condition2 = df[indicator].shift(1) >= df['median'].shift(
        1)  # 之前K线的收盘价 >= 中轨
    df.loc[condition1 & condition2,
           'signal_long'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # 找出做空信号
    condition1 = df[indicator] < df['lower']  # 当前K线的收盘价 < 下轨
    condition2 = df[indicator].shift(1) >= df['lower'].shift(1)  # 之前K线的收盘价 >= 下轨
    df.loc[condition1 & condition2,
           'signal_short'] = -1  # 将产生做空信号的那根K线的signal设置为-1，-1代表做空

    # 找出做空平仓信号
    condition1 = df[indicator] > df['median']  # 当前K线的收盘价 > 中轨
    condition2 = df[indicator].shift(1) <= df['median'].shift(
        1)  # 之前K线的收盘价 <= 中轨
    df.loc[condition1 & condition2,
           'signal_short'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # ===将long和short合并为signal
    df['signal_short'].fillna(method='ffill', inplace=True)
    df['signal_long'].fillna(method='ffill', inplace=True)
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1)
    df['signal'].fillna(value=0, inplace=True)
    df['raw_signal'] = df['signal']

    # ===根据bias，修改开仓时间
    df['temp'] = df['signal']

    # 将原始信号做多时，当bias大于阀值，设置为空
    condition1 = (df['signal'] == 1)
    condition2 = (df['bias'] > df['bias_pct'])
    df.loc[condition1 & condition2, 'temp'] = None

    # 将原始信号做空时，当bias大于阀值，设置为空
    condition1 = (df['signal'] == -1)
    condition2 = (df['bias'] < -df['bias_pct'])
    df.loc[condition1 & condition2, 'temp'] = None

    # 原始信号刚开仓，并且大于阀值，将信号设置为0
    condition1 = (df['signal'] != df['signal'].shift(1))
    condition2 = (df['temp'].isnull())
    df.loc[condition1 & condition2, 'temp'] = 0

    # 使用之前的信号补全原始信号
    df['temp'].fillna(method='ffill', inplace=True)
    df['signal'] = df['temp']

    # ===将signal中的重复值删除
    temp = df[['signal']]
    temp = temp[temp['signal'] != temp['signal'].shift(1)]
    df['signal'] = temp

    df.drop(
        ['raw_signal', 'std', 'bias', 'temp', 'signal_long', 'signal_short'],
        axis=1,
        inplace=True)

    return df
    
    
def mtm_bolling(*args):
    df = args[0]
    n = args[1]
    
    df['mtm'] = (df['close'] / df['close'].shift(n) - 1) * 100
    indicator = "mtm"
    df = bolling_formatter(df, n, indicator)
    
    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data
    

def mtm_dc_tunnel(*args):
    df = args[0]
    n = args[1]
    
    df['mtm'] = (df['close'] / df['close'].shift(n) - 1) * 100
    indicator = "mtm"
    df = dc_tunnel_formatter(df, n, indicator)
    
    signal_data = generate_signal_data(df)
    return df, df['mean'].tolist(), df['max'].tolist(), df['min'].tolist(
        ), signal_data
    
    
def mtm_keltner_channel(*args):
    df = args[0]
    n = args[1]
    
    df['mtm'] = (df['close'] / df['close'].shift(n) - 1) * 100
    indicator = "mtm"
    df = keltner_channel_formatter(df, n, indicator)
    
    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data


def adx_bolling(*args):
    df = args[0]
    n = args[1]
    
    df['_adx'] = talib.ADX(df['high'], df['low'], df['close'], n)
    df['adx'] = df['_adx'] / df['_adx'].rolling(n, min_periods=1).mean().shift()
    indicator = "adx"
    df = bolling_formatter(df, n, indicator)

    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data
    

def adx_dc_tunnel(*args):
    df = args[0]
    n = args[1]
    
    df['_adx'] = talib.ADX(df['high'], df['low'], df['close'], n)
    df['adx'] = (df['_adx'] - df['_adx'].rolling(n).min()) / (df['_adx'].rolling(n).max() - df['_adx'].rolling(n).min())
    indicator = "adx"
    df = dc_tunnel_formatter(df, n, indicator)

    signal_data = generate_signal_data(df)
    return df, df['mean'].tolist(), df['max'].tolist(), df['min'].tolist(
        ), signal_data
    
    
def adx_keltner_channel(*args):
    df = args[0]
    n = args[1]
    
    df['_adx'] = talib.ADX(df['high'], df['low'], df['close'], n)
    df['adx'] = df['_adx'] / df['_adx'].rolling(n, min_periods=1).mean().shift()
    indicator = "adx"
    df = keltner_channel_formatter(df, n, indicator)

    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data 


def angle_bolling(*args):
    df = args[0]
    n = args[1]
    
    df['_angle'] = talib.LINEARREG_ANGLE(df['close'], timeperiod=n)
    df['angle'] = (df['_angle'] - df['_angle'].rolling(n).min()) / (df['_angle'].rolling(n).max() - df['_angle'].rolling(n).min())
    indicator = "angle"
    df = bolling_formatter(df, n, indicator)
    
    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data
    

def angle_dc_tunnel(*args):
    df = args[0]
    n = args[1]
    
    df['_angle'] = talib.LINEARREG_ANGLE(df['close'], timeperiod=n)
    df['angle'] = (df['_angle'] - df['_angle'].rolling(n).min()) / (df['_angle'].rolling(n).max() - df['_angle'].rolling(n).min())
    indicator = "angle"
    df = dc_tunnel_formatter(df, n, indicator)
    signal_data = generate_signal_data(df)
    
    return df, df['mean'].tolist(), df['max'].tolist(), df['min'].tolist(
        ), signal_data


def angle_keltner_channel(*args):
    df = args[0]
    n = args[1]
    
    df['_angle'] = talib.LINEARREG_ANGLE(df['close'], timeperiod=n)
    df['angle'] = (df['_angle'] - df['_angle'].rolling(n).min()) / (df['_angle'].rolling(n).max() - df['_angle'].rolling(n).min())
    indicator = "angle"
    df = keltner_channel_formatter(df, n, indicator)
    
    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data
 

def amv_bolling(*args):
    df = args[0]
    n = args[1]
    
    # AMV 指标
    """
    N1=13
    N2=34
    AMOV=VOLUME*(OPEN+CLOSE)/2
    AMV1=SUM(AMOV,N1)/SUM(VOLUME,N1)
    AMV2=SUM(AMOV,N2)/SUM(VOLUME,N2)
    AMV 指标用成交量作为权重对开盘价和收盘价的均值进行加权移动
    平均。成交量越大的价格对移动平均结果的影响越大，AMV 指标减
    小了成交量小的价格波动的影响。当短期 AMV 线上穿/下穿长期 AMV
    线时，产生买入/卖出信号。
    """
    df['AMOV'] = df['volume'] * (df['open'] + df['close']) / 2
    df['AMV1'] = df['AMOV'].rolling(n).sum() / df['volume'].rolling(n).sum()
    # df['AMV2'] = df['AMOV'].rolling(n * 3).sum() / df['volume'].rolling(n * 3).sum()
    # 去量纲
    df['amv'] = (df['AMV1'] - df['AMV1'].rolling(n).min()) / (df['AMV1'].rolling(n).max() - df['AMV1'].rolling(n).min()) # 标准化
    
    indicator = "amv"
    df = bolling_formatter(df, n, indicator)
    
    del df['AMOV']
    del df['AMV1']
    
    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data
    

def amv_dc_tunnel(*args):
    df = args[0]
    n = args[1]
    
    # AMV 指标
    """
    N1=13
    N2=34
    AMOV=VOLUME*(OPEN+CLOSE)/2
    AMV1=SUM(AMOV,N1)/SUM(VOLUME,N1)
    AMV2=SUM(AMOV,N2)/SUM(VOLUME,N2)
    AMV 指标用成交量作为权重对开盘价和收盘价的均值进行加权移动
    平均。成交量越大的价格对移动平均结果的影响越大，AMV 指标减
    小了成交量小的价格波动的影响。当短期 AMV 线上穿/下穿长期 AMV
    线时，产生买入/卖出信号。
    """
    df['AMOV'] = df['volume'] * (df['open'] + df['close']) / 2
    df['AMV1'] = df['AMOV'].rolling(n).sum() / df['volume'].rolling(n).sum()
    # df['AMV2'] = df['AMOV'].rolling(n * 3).sum() / df['volume'].rolling(n * 3).sum()
    # 去量纲
    df['amv'] = (df['AMV1'] - df['AMV1'].rolling(n).min()) / (df['AMV1'].rolling(n).max() - df['AMV1'].rolling(n).min()) # 标准化
    
    indicator = "amv"
    df = dc_tunnel_formatter(df, n, indicator)

    signal_data = generate_signal_data(df)
    return df, df['mean'].tolist(), df['max'].tolist(), df['min'].tolist(
        ), signal_data
    
    
def amv_keltner_channel(*args):
    df = args[0]
    n = args[1]
    
    # AMV 指标
    """
    N1=13
    N2=34
    AMOV=VOLUME*(OPEN+CLOSE)/2
    AMV1=SUM(AMOV,N1)/SUM(VOLUME,N1)
    AMV2=SUM(AMOV,N2)/SUM(VOLUME,N2)
    AMV 指标用成交量作为权重对开盘价和收盘价的均值进行加权移动
    平均。成交量越大的价格对移动平均结果的影响越大，AMV 指标减
    小了成交量小的价格波动的影响。当短期 AMV 线上穿/下穿长期 AMV
    线时，产生买入/卖出信号。
    """
    df['AMOV'] = df['volume'] * (df['open'] + df['close']) / 2
    df['AMV1'] = df['AMOV'].rolling(n).sum() / df['volume'].rolling(n).sum()
    # df['AMV2'] = df['AMOV'].rolling(n * 3).sum() / df['volume'].rolling(n * 3).sum()
    # 去量纲
    df['amv'] = (df['AMV1'] - df['AMV1'].rolling(n).min()) / (df['AMV1'].rolling(n).max() - df['AMV1'].rolling(n).min()) # 标准化
    
    indicator = "amv"
    df = keltner_channel_formatter(df, n, indicator)

    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data 


def ar_bolling(*args):
    df = args[0]
    n = args[1]
    
    v1 = (df['high'] - df['open']).rolling(n, min_periods=1).sum()
    v2 = (df['open'] - df['low']).rolling(n, min_periods=1).sum()
    _ar = 100 * v1 / v2
    df["ar"] = pd.Series(_ar)
    indicator = "ar"
    df = bolling_formatter(df, n, indicator)
    
    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data
    

def ar_dc_tunnel(*args):
    df = args[0]
    n = args[1]
    
    v1 = (df['high'] - df['open']).rolling(n, min_periods=1).sum()
    v2 = (df['open'] - df['low']).rolling(n, min_periods=1).sum()
    _ar = 100 * v1 / v2
    df["ar"] = pd.Series(_ar)
    indicator = "ar"
    df = dc_tunnel_formatter(df, n, indicator)
    
    signal_data = generate_signal_data(df)
    return df, df['mean'].tolist(), df['max'].tolist(), df['min'].tolist(
        ), signal_data
    
    
def ar_keltner_channel(*args):
    df = args[0]
    n = args[1]
    
    v1 = (df['high'] - df['open']).rolling(n, min_periods=1).sum()
    v2 = (df['open'] - df['low']).rolling(n, min_periods=1).sum()
    _ar = 100 * v1 / v2
    df["ar"] = pd.Series(_ar)
    indicator = "ar"
    df = keltner_channel_formatter(df, n, indicator)
    
    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data
    
    
def atr_bolling(*args):
    df = args[0]
    n = args[1]
    """
    N=20
    TR=MAX(HIGH-LOW,ABS(HIGH-REF(CLOSE,1)),ABS(LOW-REF(CLOSE,1)))
    ATR=MA(TR,N)
    MIDDLE=MA(CLOSE,N)
    """
    df['c1'] = df['high'] - df['low']  # HIGH-LOW
    df['c2'] = abs(df['high'] - df['close'].shift(1))  # ABS(HIGH-REF(CLOSE,1)
    df['c3'] = abs(df['low'] - df['close'].shift(1))  # ABS(LOW-REF(CLOSE,1))
    df['TR'] = df[['c1', 'c2', 'c3']].max(
        axis=1)  # TR=MAX(HIGH-LOW,ABS(HIGH-REF(CLOSE,1)),ABS(LOW-REF(CLOSE,1)))
    df['_ATR'] = df['TR'].rolling(n, min_periods=1).mean()  # ATR=MA(TR,N)
    df['middle'] = df['close'].rolling(n, min_periods=1).mean()  # MIDDLE=MA(CLOSE,N)
    # ATR指标去量纲
    df['atr'] = df['_ATR'] / (df['middle'] + eps)
    indicator = "atr"
    df = bolling_formatter(df, n, indicator)
    df.drop(['c1', 'c2', 'c3', 'TR', '_ATR', 'middle'],
        axis=1,
        inplace=True)
    
    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data
    

def atr_dc_tunnel(*args):
    df = args[0]
    n = args[1]
    """
    N=20
    TR=MAX(HIGH-LOW,ABS(HIGH-REF(CLOSE,1)),ABS(LOW-REF(CLOSE,1)))
    ATR=MA(TR,N)
    MIDDLE=MA(CLOSE,N)
    """
    df['c1'] = df['high'] - df['low']  # HIGH-LOW
    df['c2'] = abs(df['high'] - df['close'].shift(1))  # ABS(HIGH-REF(CLOSE,1)
    df['c3'] = abs(df['low'] - df['close'].shift(1))  # ABS(LOW-REF(CLOSE,1))
    df['TR'] = df[['c1', 'c2', 'c3']].max(
        axis=1)  # TR=MAX(HIGH-LOW,ABS(HIGH-REF(CLOSE,1)),ABS(LOW-REF(CLOSE,1)))
    df['_ATR'] = df['TR'].rolling(n, min_periods=1).mean()  # ATR=MA(TR,N)
    df['middle'] = df['close'].rolling(n, min_periods=1).mean()  # MIDDLE=MA(CLOSE,N)
    # ATR指标去量纲
    df['atr'] = df['_ATR'] / (df['middle'] + eps)
    indicator = "atr"
    df = dc_tunnel_formatter(df, n, indicator)
    df.drop(['c1', 'c2', 'c3', 'TR', '_ATR', 'middle'],
        axis=1,
        inplace=True)
    
    signal_data = generate_signal_data(df)
    return df, df['mean'].tolist(), df['max'].tolist(), df['min'].tolist(
        ), signal_data
    
    
def atr_keltner_channel(*args):
    df = args[0]
    n = args[1]

    """
    N=20
    TR=MAX(HIGH-LOW,ABS(HIGH-REF(CLOSE,1)),ABS(LOW-REF(CLOSE,1)))
    ATR=MA(TR,N)
    MIDDLE=MA(CLOSE,N)
    """
    df['c1'] = df['high'] - df['low']  # HIGH-LOW
    df['c2'] = abs(df['high'] - df['close'].shift(1))  # ABS(HIGH-REF(CLOSE,1)
    df['c3'] = abs(df['low'] - df['close'].shift(1))  # ABS(LOW-REF(CLOSE,1))
    df['TR'] = df[['c1', 'c2', 'c3']].max(
        axis=1)  # TR=MAX(HIGH-LOW,ABS(HIGH-REF(CLOSE,1)),ABS(LOW-REF(CLOSE,1)))
    df['_ATR'] = df['TR'].rolling(n, min_periods=1).mean()  # ATR=MA(TR,N)
    df['middle'] = df['close'].rolling(n, min_periods=1).mean()  # MIDDLE=MA(CLOSE,N)
    # ATR指标去量纲
    df['atr'] = df['_ATR'] / (df['middle'] + eps)
    indicator = "atr"
    df = keltner_channel_formatter(df, n, indicator)

    df.drop(['c1', 'c2', 'c3', '_ATR', 'middle'],
        axis=1,
        inplace=True)

    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data


def bbw_bolling(*args):
    df = args[0]
    n = args[1]
    
    df['median'] = df['close'].rolling(n, min_periods=1).mean()
    df['std'] = df['close'].rolling(n, min_periods=1).std(ddof=0)
    df['upper'] = df['median'] + df['std'] * 2
    df['lower'] = df['median'] - df['std'] * 2
    df['bbw'] = (df['upper'] - df['lower']) / df['median']
    indicator = "bbw"
    
    df.drop(['median', 'std', 'upper', 'lower'],
            axis=1,
            inplace=True)
    
    df = bolling_formatter(df, n, indicator)
    
    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data
    

def bbw_dc_tunnel(*args):
    df = args[0]
    n = args[1]
    
    df['median'] = df['close'].rolling(n, min_periods=1).mean()
    df['std'] = df['close'].rolling(n, min_periods=1).std(ddof=0)
    df['upper'] = df['median'] + df['std'] * 2
    df['lower'] = df['median'] - df['std'] * 2
    df['bbw'] = (df['upper'] - df['lower']) / df['median']
    indicator = "bbw"
    
    df.drop(['median', 'std', 'upper', 'lower'],
            axis=1,
            inplace=True)
    df = dc_tunnel_formatter(df, n, indicator)
    
    signal_data = generate_signal_data(df)
    return df, df['mean'].tolist(), df['max'].tolist(), df['min'].tolist(
        ), signal_data
    
    
def bbw_keltner_channel(*args):
    df = args[0]
    n = args[1]
    
    df['median'] = df['close'].rolling(n, min_periods=1).mean()
    df['std'] = df['close'].rolling(n, min_periods=1).std(ddof=0)
    df['upper'] = df['median'] + df['std'] * 2
    df['lower'] = df['median'] - df['std'] * 2
    df['bbw'] = (df['upper'] - df['lower']) / df['median']
    indicator = "bbw"
    
    df.drop(['median', 'std', 'upper', 'lower'],
            axis=1,
            inplace=True)
    df = keltner_channel_formatter(df, n, indicator)
    
    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data
    

def bias_bolling(*args):
    df = args[0]
    n = args[1]
    
    df['bias'] = (df['close'] / df['close'].rolling(n, min_periods=1).mean() - 1)
    indicator = "bias"
    
    df = bolling_formatter(df, n, indicator)
    
    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data
    

def bias_dc_tunnel(*args):
    df = args[0]
    n = args[1]
    
    df['bias'] = (df['close'] / df['close'].rolling(n, min_periods=1).mean() - 1)
    indicator = "bias"
    
    df = dc_tunnel_formatter(df, n, indicator)
    
    signal_data = generate_signal_data(df)
    return df, df['mean'].tolist(), df['max'].tolist(), df['min'].tolist(
        ), signal_data
    
    
def bias_keltner_channel(*args):
    df = args[0]
    n = args[1]
    
    df['bias'] = (df['close'] / df['close'].rolling(n, min_periods=1).mean() - 1)
    indicator = "bias"
    
    df = keltner_channel_formatter(df, n, indicator)
    
    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data


def bolling_width_bolling(*args):
    df = args[0]
    n = args[1]
    
    df['median'] = df['close'].rolling(window=n).mean()
    df['std'] = df['close'].rolling(n, min_periods=1).std(ddof=0)
    df['z_score'] = abs(df['close'] - df['median']) / df['std']
    df['m'] = df['z_score'].rolling(window=n).mean()
    df['upper'] = df['median'] + df['std'] * df['m']
    df['lower'] = df['median'] - df['std'] * df['m']
    df['bolling_width'] = df['std'] * df['m'] * 2 / (df['median'] + eps)

    # 删除多余列
    df.drop(['median', 'std', 'z_score', 'm'],
            axis=1,
            inplace=True)
    indicator = "bolling_width"
    
    df = bolling_formatter(df, n, indicator)
    
    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data
    

def bolling_width_dc_tunnel(*args):
    df = args[0]
    n = args[1]
    
    df['bias'] = (df['close'] / df['close'].rolling(n, min_periods=1).mean() - 1)
    indicator = "bias"
    
    df = dc_tunnel_formatter(df, n, indicator)
    
    signal_data = generate_signal_data(df)
    return df, df['mean'].tolist(), df['max'].tolist(), df['min'].tolist(
        ), signal_data
    
    
def bolling_width_keltner_channel(*args):
    df = args[0]
    n = args[1]
    
    df['bias'] = (df['close'] / df['close'].rolling(n, min_periods=1).mean() - 1)
    indicator = "bias"
    
    df = keltner_channel_formatter(df, n, indicator)
    
    signal_data = generate_signal_data(df)
    return df, df['median'].tolist(), df['upper'].tolist(), df['lower'].tolist(
        ), signal_data
