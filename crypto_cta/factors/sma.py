from cta_api.function import *
from numba import jit


def signal(df, para=[200, 2], proportion=1, leverage_rate=1):
    """
    :param df: 原始数据
    :param para: n, m   siganl计算的参数
    :return:
        返回包含signal的数据

    # 双均线策略
    短线上穿长线做多
    短线下穿长线做空
    """

    # ===== 获取策略参数
    if isinstance(para, list):
        n = para[0]
    else:
        n = int(para)  # 获取参数n，即para第一个元素
    # n = para[0]
    # m = para[1]
    # ===== 计算指标
    # 计算短线

    df['ma_short'] = df['close'].rolling(n,min_periods=1).mean()
    df['ma_long'] = df['ma_short'].rolling(n,min_periods=1).mean()


    # ===== 找出交易信号
    # === 找出做多信号
    condition1 = df['ma_short'] > df['ma_long']
    condition2 = df['ma_short'].shift(1) <= df['ma_long'].shift(1)  
    df.loc[condition1 & condition2, 'signal_long'] = 1  # 将产生做多信号的那根K线的signal设置为1，1代表做多

    # === 找出做多平仓信号
    condition1 = df['ma_short'] < df['ma_long']
    condition2 = df['ma_short'].shift(1) >= df['ma_long'].shift(1)
    df.loc[condition1 & condition2, 'signal_long'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # === 找出做空信号
    condition1 = df['ma_short'] < df['ma_long']
    condition2 = df['ma_short'].shift(1) >= df['ma_long'].shift(1)  # 之前K线的收盘价 >= 下轨
    df.loc[condition1 & condition2, 'signal_short'] = -1  # 将产生做空信号的那根K线的signal设置为-1，-1代表做空

    # === 找出做空平仓信号
    condition1 = df['ma_short'] > df['ma_long']
    condition2 = df['ma_short'].shift(1) <= df['ma_long'].shift(1)  # 之前K线的收盘价 <= 中轨
    df.loc[condition1 & condition2, 'signal_short'] = 0  # 将产生平仓信号当天的signal设置为0，0代表平仓

    # ===== 合并做多做空信号，去除重复信号
    # === 合并做多做空信号
    df['signal'] = df[['signal_long', 'signal_short']].sum(axis=1, min_count=1, skipna=True)  # 合并多空信号，即signal_long与signal_short相加，得到真实的交易信号
    # === 去除重复信号
    temp = df[df['signal'].notnull()][['signal']]  # 筛选siganla不为空的数据，并另存一个变量
    temp = temp[temp['signal'] != temp['signal'].shift(1)]  # 筛选出当前周期与上个周期持仓信号不一致的，即去除重复信号
    df['signal'] = temp['signal']  # 将处理后的signal覆盖到原始数据的signal列

    # ===== 删除无关变量
    df.drop(['ma_long', 'ma_short', 'signal_long', 'signal_short'], axis=1, inplace=True)  # 删除std、signal_long、signal_short列

    # ===== 止盈止损
    # 校验当前的交易是否需要进行止盈止损
    df = process_stop_loss_close(df, proportion, leverage_rate=leverage_rate)  # 调用函数，判断是否需要止盈止损，df需包含signal列

    return df

# 策略参数组合
def para_list(m_list=range(2, 500, 2), n_list=range(2, 200, 2)):
    """
    产生布林 策略的参数范围
    :param m_list:  m值的列表
    :param n_list:  n值的列表
    :return:
        返回一个大的列表，格式为：[[20, 0.3]]
    """

    # ===== 构建遍历的列表
    para_list = list(m_list)  # 定义一个新的列表，用于存储遍历参数
    # para_list = [[i,j] for i in m_list for j in n_list]

    # ===== 返回参数列表
    return para_list