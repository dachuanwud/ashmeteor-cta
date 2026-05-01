import os
import pandas as pd
import numpy as np

def transfer_to_period_data(df:pd.DataFrame, rule_type='5T'):
    """
    将日线数据转换为相应的周期数据
    :param df:原始数据
    :param period_type:转换周期
    :param extra_agg_dict:
    :param offset:

    :return:
    """
    df.set_index('candle_begin_time', inplace=True)
    df['avg_price_1m'] = df['avg_price']
    agg_dict = {
        'symbol': 'first',
        'open':   'first',
        'high':   'max',
        'low':    'min',
        'close':  'last',
        'volume': 'sum',
        'quote_volume': 'sum',
        'trade_num':    'sum',
        'taker_buy_base_asset_volume':  'sum',
        'taker_buy_quote_asset_volume': 'sum',
        'avg_price': 'first'
    }
    # =====转换为其他分钟数据
    period_df = df.resample(rule=rule_type).agg(agg_dict)
    # =针对重采样后数据，补全空缺的数据。保证整张表没有空余数据
    period_df['symbol'].fillna(method='ffill',  inplace=True)
    # 对开、高、收、低、价格进行补全处理
    period_df['close'].fillna(method='ffill',   inplace=True)
    period_df['open'].fillna(value=period_df['close'], inplace=True)
    period_df['high'].fillna(value=period_df['close'], inplace=True)
    period_df['low'].fillna(value=period_df['close'],  inplace=True)
    # 将停盘时间的某些列，数据填补为0
    fill_0_list = ['volume', 'quote_volume', 'trade_num', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume']
    period_df.loc[:, fill_0_list] = period_df[fill_0_list].fillna(value=0)

    # 用1m均价代替重采样均价
    # period_df.set_index('candle_begin_time', inplace=True)
    period_df['avg_price'] = df['avg_price_1m']
    period_df['avg_price'].fillna(value=period_df['open'], inplace=True)

    # 计算轮动所需要的每根k线涨跌幅
    df['pct'] = df['close'].pct_change()
    df['pct'] = df['pct'].fillna(0)
    period_df_list = []
    # 通过持仓周期来计算需要多少个offset，遍历转换每一个offset数据
    for offset in range(int(rule_type[:-1])):
        period_df = df.resample(rule_type, offset=offset).agg(agg_dict)
        period_df['kline_pct'] = df['pct'].resample(rule_type, offset=offset).apply(lambda x: list(x))
        period_df['offset'] = offset
        period_df.reset_index(inplace=True)
        period_df.dropna(subset=['symbol'], inplace=True)
        period_df_list.append(period_df)
    # 将不同offset的数据，合并到一张表
    period_df = pd.concat(period_df_list, ignore_index=True)
    period_df.sort_values(by='candle_begin_time', inplace=True)
    period_df.dropna(subset=['open'], inplace=True)  # 去除一天都没有交易的周期
    period_df = period_df[period_df['volume'] > 0]  # 去除成交量为0的交易周期
    period_df.reset_index(inplace=True,drop=True)
    return period_df

# =====计算资金曲线
def cal_equity_curve(df, slippage=1 / 1000, c_rate=5 / 10000, leverage_rate=3,
                     min_amount=0.01,
                     min_margin_ratio=1 / 100):
    """
    :param df:
    :param slippage:  滑点 ，可以用百分比，也可以用固定值。建议币圈用百分比，股票用固定值
    :param c_rate:  手续费，commission fees，默认为万分之5。不同市场手续费的收取方法不同，对结果有影响。比如和股票就不一样。
    :param leverage_rate:  杠杆倍数
    :param min_amount:  最小下单量
    :param min_margin_ratio: 最低保证金率，低于就会爆仓
    :return:
    """
    # =====下根k线开盘价
    df['next_open'] = df['open'].shift(-1)  # 下根K线的开盘价
    df['next_open'].fillna(value=df['close'], inplace=True)

    # =====找出开仓、平仓的k线
    condition1 = df['pos'] != 0  # 当前周期不为空仓
    condition2 = df['pos'] != df['pos'].shift(1)  # 当前周期和上个周期持仓方向不一样。
    open_pos_condition = condition1 & condition2

    condition1 = df['pos'] != 0  # 当前周期不为空仓
    condition2 = df['pos'] != df['pos'].shift(-1)  # 当前周期和下个周期持仓方向不一样。
    close_pos_condition = condition1 & condition2

    # =====对每次交易进行分组
    df.loc[open_pos_condition, 'start_time'] = df['candle_begin_time']
    df['start_time'].fillna(method='ffill', inplace=True)
    df.loc[df['pos'] == 0, 'start_time'] = pd.NaT

    # =====开始计算资金曲线
    initial_cash = 10000  # 初始资金，默认为10000元
    # ===在开仓时
    # 在open_pos_condition的K线，以开盘价计算买入合约的数量。（当资金量大的时候，可以用5分钟均价）
    df.loc[open_pos_condition, 'contract_num'] = initial_cash * leverage_rate / (min_amount * df['open'])
    df['contract_num'] = np.floor(df['contract_num'])  # 对合约张数向下取整
    # 开仓价格：理论开盘价加上相应滑点
    df.loc[open_pos_condition, 'open_pos_price'] = df['open'] * (1 + slippage * df['pos'])
    # 开仓之后剩余的钱，扣除手续费
    df['cash'] = initial_cash - df['open_pos_price'] * min_amount * df['contract_num'] * c_rate  # 即保证金

    # ===开仓之后每根K线结束时
    # 买入之后cash，contract_num，open_pos_price不再发生变动
    for _ in ['contract_num', 'open_pos_price', 'cash']:
        df[_].fillna(method='ffill', inplace=True)
    df.loc[df['pos'] == 0, ['contract_num', 'open_pos_price', 'cash']] = None

    # ===在平仓时
    # 平仓价格
    df.loc[close_pos_condition, 'close_pos_price'] = df['next_open'] * (1 - slippage * df['pos'])
    # 平仓之后剩余的钱，扣除手续费
    df.loc[close_pos_condition, 'close_pos_fee'] = df['close_pos_price'] * min_amount * df['contract_num'] * c_rate

    # ===计算利润
    # 开仓至今持仓盈亏
    df['profit'] = min_amount * df['contract_num'] * (df['close'] - df['open_pos_price']) * df['pos']
    # 平仓时理论额外处理
    df.loc[close_pos_condition, 'profit'] = min_amount * df['contract_num'] * (df['close_pos_price'] - df['open_pos_price']) * df['pos']
    # 账户净值
    df['net_value'] = df['cash'] + df['profit']

    # ===计算爆仓
    # 至今持仓盈亏最小值
    df.loc[df['pos'] == 1, 'price_min'] = df['low']
    df.loc[df['pos'] == -1, 'price_min'] = df['high']
    df['profit_min'] = min_amount * df['contract_num'] * (df['price_min'] - df['open_pos_price']) * df['pos']
    # 账户净值最小值
    df['net_value_min'] = df['cash'] + df['profit_min']
    # 计算保证金率
    df['margin_ratio'] = df['net_value_min'] / (min_amount * df['contract_num'] * df['price_min'])
    # 计算是否爆仓
    df.loc[df['margin_ratio'] <= (min_margin_ratio + c_rate), '是否爆仓'] = 1

    # ===平仓时扣除手续费
    df.loc[close_pos_condition, 'net_value'] -= df['close_pos_fee']
    # 应对偶然情况：下一根K线开盘价格价格突变，在平仓的时候爆仓。此处处理有省略，不够精确。
    df.loc[close_pos_condition & (df['net_value'] < 0), '是否爆仓'] = 1

    # ===对爆仓进行处理
    df['是否爆仓'] = df.groupby('start_time')['是否爆仓'].fillna(method='ffill')
    df.loc[df['是否爆仓'] == 1, 'net_value'] = 0

    # =====计算资金曲线
    df['equity_change'] = df['net_value'].pct_change()
    df.loc[open_pos_condition, 'equity_change'] = df.loc[open_pos_condition, 'net_value'] / initial_cash - 1  # 开仓日的收益率
    df['equity_change'].fillna(value=0, inplace=True)
    df['equity_curve'] = (1 + df['equity_change']).cumprod()

    # =====删除不必要的数据，并存储
    df.drop(['next_open', 'contract_num', 'open_pos_price', 'cash', 'close_pos_price', 'close_pos_fee',
             'profit', 'net_value', 'price_min', 'profit_min', 'net_value_min', 'margin_ratio', '是否爆仓'],
            axis=1, inplace=True)

    return df

def process_stop_loss_close(df, stop_loss_pct, leverage_rate):
    """
    止损函数
    :param df:
    :param stop_loss_pct: 止损比例
    :param leverage_rate: 杠杆倍数
    :return:
    """

    '''
    止损函数示例
     candle_begin_time                选币                   open               close           signal        原始信号           止损价格
    2021-04-23 04:00:00            IOST-USDT...            3.69380            3.69380            -1            -1              4.06318
    2021-04-23 05:00:00            IOST-USDT...            3.75580            3.75580            nan            nan            4.06318
    2021-04-23 06:00:00            IOST-USDT...            3.70157            3.70157            nan            nan            4.06318
    2021-04-23 07:00:00            IOST-USDT...            3.59443            3.59443            nan            nan            4.06318
    2021-04-23 08:00:00            IOST-USDT...            3.78299            3.78299            nan            nan            4.06318
    2021-04-23 09:00:00            IOST-USDT...            3.73637            3.73637            -1            -1              4.06318
    2021-04-23 10:00:00            IOST-USDT...            3.92761            3.92761            nan            nan            4.06318
    2021-04-23 11:00:00            IOST-USDT...            4.02816            4.02816            nan            nan            4.06318
    2021-04-23 12:00:00            IOST-USDT...            3.85746            3.85746            nan            nan            4.06318
    2021-04-23 13:00:00            IOST-USDT...            3.84017            3.84017            nan            nan            4.06318
    2021-04-23 14:00:00            IOST-USDT...            3.94633            3.94633            nan            nan            4.06318
    2021-04-23 15:00:00            IOST-USDT...            3.96164            3.96164            nan            nan            4.06318
    2021-04-23 16:00:00            IOST-USDT...            3.95144            3.95144            nan            nan            4.06318
    2021-04-23 17:00:00            IOST-USDT...            3.91294            3.91294            nan            nan            4.06318
    2021-04-23 18:00:00            IOST-USDT...            4.02094            4.02094            nan            nan            4.06318
    2021-04-23 19:00:00            IOST-USDT...            4.04794            4.04794            nan            nan            4.06318
    2021-04-23 20:00:00            IOST-USDT...            3.99289            3.99289            nan            nan            4.06318
    2021-04-23 21:00:00            IOST-USDT...            3.96215            3.96215            nan            nan            4.06318
    2021-04-23 22:00:00            IOST-USDT...            4.01350            4.01350            nan            nan            4.06318
    2021-04-23 23:00:00            IOST-USDT...            4.14397            4.14397            0              nan            4.06318
    '''

    # ===初始化持仓方向与开仓价格
    position = 0  # 持仓方向
    open_price = np.nan  # 开仓价格

    for i in df.index:
        # 开平仓   当signal不为空的时候 并且 open_price为空 或 position与当前方向不同
        if not np.isnan(df.loc[i, 'signal']) and (np.isnan(open_price) or position != int(df.loc[i, 'signal'])):
            position = int(df.loc[i, 'signal'])
            if df.loc[i, 'signal']:  # 开仓
                # 获取开仓的价格，为了符合实盘，所以获取下一周期的开盘价
                open_price = df.loc[i + 1, 'open'] if i < df.shape[0] - 1 else df.loc[i, 'close']
            else:  # 平仓，因为在python中非0即真，所以这里直接写else即代表0
                open_price = np.nan
        # 持仓
        if position:  # 判断当天是否有持仓方向，即是否为非0的值
            # 计算止损的价格   开仓价格 * (1 - 持仓方向 * 止损比例 / 杠杆倍数)
            # 假设我们100元开仓，止损0.05，杠杆为2，那么实际上我们开仓的仓位价值是100*2=200元，那么当你的本金亏损%5的时候，实际上的亏损为 (95-100)/200 = -0.025
            # 假设我们开仓的价格：100 方向：做多    止损比例：5%     杠杆倍数：2 那么止损价格: 100 * (1 - 1 * 0.05 / 2) = 100 * (1 - 0.025) = 100 * 0.975 = 97.5
            # 即当前的价格小于95就触发止损
            stop_loss_price = open_price * (1 - position * stop_loss_pct / leverage_rate)
            # 止损条件等于 持仓方向 * (收盘价 - 止损价格) <= 0
            stop_loss_condition = position * (df.loc[i, 'close'] - stop_loss_price) <= 0  # 止损条件
            df.at[i, 'stop_loss_condition'] = stop_loss_price
            # 如果满足止损条件，并且当前的信号为空时将signal设置为0，避免覆盖其他信号
            if stop_loss_condition and np.isnan(df.loc[i, 'signal']):
                df.at[i, 'signal'] = 0
                position = 0
                open_price = np.nan

    return df

def write_file(content, path):
    """
    写入文件
    :param content: 写入内容
    :param path: 文件路径
    :return:
    """
    with open(path, 'w', encoding='utf8') as f:
        f.write(content)


# 将数字转为百分数
def num_to_pct(value):
    return '%.2f%%' % (value * 100)


def generate_fibonacci_sequence(min_number, max_number):
    """
    生成费拨那契数列，支持小数的生成
    注意：返回的所有数据都是浮点类型(小数)的，如果需要整数需要额外处理
    :param min_number: 最小值
    :param max_number: 最大值
    :return:
    """
    sequence = []
    base = 1
    if min_number < 1:
        base = 10 ** len(str(min_number).split('.')[1])
    last_number = 0
    new_number = 1
    while True:
        last_number, new_number = new_number, last_number + new_number
        if new_number / base > min_number:
            sequence.append(new_number / base)
        if new_number / base > max_number:
            break
    return sequence[:-1]

def revise_data_length(data, data_len):
    """
    校正数据长度
    原数据过长，则进行切片
    原数据果断，则使用0填充
    :param data: 原数据
    :param data_len: 资金曲线的数据长度
    :return: 校正后的数据
    """
    if len(data) > data_len:
        data = data[0:data_len]
    elif len(data) < data_len:
        data = data.append(pd.Series([0] * (data_len - len(data))))

    return data

def get_benchmark(start_date, end_date, freq):
    benchmark = pd.DataFrame(pd.date_range(start=start_date, end=end_date, freq=freq))
    benchmark.rename(columns={0: 'candle_begin_time'}, inplace=True)

    return benchmark
