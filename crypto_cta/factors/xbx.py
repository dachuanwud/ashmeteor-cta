from cta_api.function import *


# =====作者邢不行
# 策略
def signal(df, para=[200, 2, 0.05], proportion=1, leverage_rate=1):
    """
    针对原始布林策略进行修改。
    bias = close / 均线 - 1
    当开仓的时候，如果bias过大，即价格离均线过远，那么就先不开仓。等价格和均线距离小于bias_pct之后，才按照原计划开仓
    :param df: 原始数据
    :param para: n,m,bias_pct siganl计算的参数
    :return:
    """

    # ===== 获取策略参数
    n = int(para[0])  # 获取参数n，即para第一个元素
    m = float(para[1])  # 获取参数m，即para第二个元素
    bias_pct = float(para[2])  # 获取参数bias_pct，即para第三个元素

    # ===== 计算指标
    # 计算均线
    df['median'] = df['close'].rolling(n, min_periods=1).mean()  # 计算收盘价n个周期的均线，如果K线数据小于n就用K线的数量进行计算
    # 计算上轨、下轨道
    df['std'] = df['close'].rolling(n, min_periods=1).std(ddof=0)  # 计算收盘价n日的std，ddof代表标准差自由度
    df['upper'] = df['median'] + m * df['std']  # 计算上轨
    df['lower'] = df['median'] - m * df['std']  # 计算下轨
    # 计算bias
    df['bias'] = df['close'] / df['median'] - 1

    # ===== 找出交易信号
    # === 找出做多信号
    condition1 = df['close'] > df['upper']  # 当前K线的收盘价 > 上轨
    condition2 = df['close'].shift(1) <= df['upper'].shift(1)  # 之前K线的收盘价 <= 上轨
    df.loc[condition1 & condition2, 'signal_long'] = 1  # 将产生做多信号的那根K线的signal设置为1，1代表做多

    # === 找出做多平仓信号
    condition1 = df['close'] < df['median']  # 当前K线的收盘价 < 中轨
    condition2 = df['close'].shift(1) >= df['median'].shift(1)  # 之前K线的收盘价 >= 中轨
    df.loc[condition1 & condition2, 'signal_long'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # === 找出做空信号
    condition1 = df['close'] < df['lower']  # 当前K线的收盘价 < 下轨
    condition2 = df['close'].shift(1) >= df['lower'].shift(1)  # 之前K线的收盘价 >= 下轨
    df.loc[condition1 & condition2, 'signal_short'] = -1  # 将产生做空信号的那根K线的signal设置为-1，-1代表做空

    # === 找出做空平仓信号
    condition1 = df['close'] > df['median']  # 当前K线的收盘价 > 中轨
    condition2 = df['close'].shift(1) <= df['median'].shift(1)  # 之前K线的收盘价 <= 中轨
    df.loc[condition1 & condition2, 'signal_short'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # ===== 合并做多做空信号
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1, min_count=1, skipna=True)  # 合并多空信号，即signal_long与signal_short相加，得到真实的交易信号

    # ===== 根据bias，修改开仓时间
    df['temp'] = df['signal']
    # === 将原始信号做多时，当bias大于阀值，设置为空
    condition1 = (df['signal'] == 1)  # signal为1
    condition2 = (df['bias'] > bias_pct)  # bias大于bias_pct
    df.loc[condition1 & condition2, 'temp'] = None  # 将signal设置为空

    # === 将原始信号做空时，当bias大于阀值，设置为空
    condition1 = (df['signal'] == -1)  # signal为-1
    condition2 = (df['bias'] < -1 * bias_pct)  # bias小于 (-1 * bias_pct)
    df.loc[condition1 & condition2, 'temp'] = None  # 将signal设置为空

    # 原始信号刚开仓，并且大于阀值，将信号设置为0
    condition1 = (df['signal'] != df['signal'].shift(1))
    condition2 = (df['temp'].isnull())
    df.loc[condition1 & condition2, 'temp'] = 0

    # ===== 合去除重复信号
    # === 去除重复信号
    df['signal'] = df['temp']
    temp = df[df['signal'].notnull()][['signal']]  # 筛选siganal不为空的数据，并另存一个变量
    temp = temp[temp['signal'] != temp['signal'].shift(1)]  # 筛选出当前周期与上个周期持仓信号不一致的，即去除重复信号
    df['signal'] = temp['signal']  # 将处理后的signal覆盖到原始数据的signal列

    # ===== 删除无关变量
    df.drop(['raw_signal', 'median', 'std', 'upper', 'lower', 'bias', 'temp', 'signal_long', 'signal_short'], axis=1,
            inplace=True)  # 删除raw_signal、median、std、upper、lower、bias、temp、signal_long、signal_short列

    # ===== 止盈止损
    # 校验当前的交易是否需要进行止盈止损
    df = process_stop_loss_close(df, proportion, leverage_rate=leverage_rate)  # 调用函数，判断是否需要止盈止损，df需包含signal列

    return df



# 策略参数组合
def para_list(m_list=range(20, 1000 + 20, 20), n_list=[i / 10 for i in list(np.arange(3, 50 + 2, 2))],
                                bias_pct_list=[i / 100 for i in list(np.arange(5, 20 + 2, 2))]):
    """
    :param m_list: m值的列表
    :param n_list: n值的列表
    :param bias_pct_list: bias_pct值的列表
    :return:
        返回一个大的列表，格式为：[[20, 0.3, 0.05]]
    """

    # ===== 构建遍历的列表
    para_list = []  # 定义一个新的列表，用于存储遍历参数

    # === 遍历参数
    for bias_pct in bias_pct_list:  # 遍历bias_pct的参数
        for m in m_list:  # 遍历m的参数
            for n in n_list:  # 遍历n的参数
                para = [m, n, bias_pct]  # 构建每个遍历列表的每个参数
                para_list.append(para)  # 将参数累加到para_list
    # ===== 返回参数列表
    return para_list

