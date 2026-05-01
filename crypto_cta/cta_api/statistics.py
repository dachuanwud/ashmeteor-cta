import itertools

import numpy as np
import pandas as pd


# ======= 策略评价 =========
# 将资金曲线数据，转化为交易数据
def transfer_equity_curve_to_trade(equity_curve):
    """
    将资金曲线数据，转化为一笔一笔的交易
    :param equity_curve: 资金曲线函数计算好的结果，必须包含pos
    :return:
    """
    # =选取开仓、平仓条件
    condition1 = equity_curve['pos'] != 0
    condition2 = equity_curve['pos'] != equity_curve['pos'].shift(1)
    open_pos_condition = condition1 & condition2

    # =计算每笔交易的start_time
    if 'start_time' not in equity_curve.columns:
        equity_curve.loc[open_pos_condition, 'start_time'] = equity_curve['candle_begin_time']
        equity_curve['start_time'].fillna(method='ffill', inplace=True)
        equity_curve.loc[equity_curve['pos'] == 0, 'start_time'] = pd.NaT

    # =对每次交易进行分组，遍历每笔交易
    trade = pd.DataFrame()  # 计算结果放在trade变量中

    for _index, group in equity_curve.groupby('start_time'):

        # 记录每笔交易
        # 本次交易方向
        trade.loc[_index, 'signal'] = group['pos'].iloc[0]

        # 本次交易杠杆倍数
        if 'leverage_rate' in group:
            trade.loc[_index, 'leverage_rate'] = group['leverage_rate'].iloc[0]

        g = group[group['pos'] != 0]  # 去除pos=0的行
        # 本次交易结束那根K线的开始时间
        trade.loc[_index, 'end_bar'] = g.iloc[-1]['candle_begin_time']
        # 开仓价格
        trade.loc[_index, 'start_price'] = g.iloc[0]['open']
        # 平仓信号的价格
        trade.loc[_index, 'end_price'] = g.iloc[-1]['close']
        # 持仓k线数量
        trade.loc[_index, 'bar_num'] = g.shape[0]
        # 本次交易收益
        trade.loc[_index, 'change'] = (group['equity_change'] + 1).prod() - 1
        # 本次交易结束时资金曲线
        trade.loc[_index, 'end_equity_curve'] = g.iloc[-1]['equity_curve']
        # 本次交易中资金曲线最低值
        trade.loc[_index, 'min_equity_curve'] = g['equity_curve'].min()

    return trade


# 计算策略评价指标
def strategy_evaluate(equity_curve, trade, rule_type):
    """
    :param equity_curve: 带资金曲线的df
    :param trade: transfer_equity_curve_to_trade的输出结果，每笔交易的df
    :return:
    """

    # ===新建一个dataframe保存回测指标
    results = pd.DataFrame()

    # ===计算累积净值
    results.loc[0, '累积净值'] = round(equity_curve['equity_curve'].iloc[-1], 2)

    # ===计算年化收益
    if rule_type.endswith('T'):
        rule = int(rule_type[:-1])
        n = 24*60/rule
    if rule_type.endswith('H'):
        rule = int(rule_type[:-1])
        n = 24/rule

    # 计算总收益
    total_return = equity_curve['equity_curve'].iloc[-1] / equity_curve['equity_curve'].iloc[0]
    # 计算时间差，并转换为天数
    time_difference = (equity_curve['candle_begin_time'].iloc[-1] - equity_curve['candle_begin_time'].iloc[0])
    time_difference_in_days = int(time_difference.total_seconds() / (60 * 60 * 24))
    # 计算年化收益
    annual_return = (total_return ** (365 / time_difference_in_days)) - 1
    # annual_return = (equity_curve['equity_curve'].iloc[-1] / equity_curve['equity_curve'].iloc[0]) ** ('1 days 00:00:00' / (equity_curve['candle_begin_time'].iloc[-1] - equity_curve['candle_begin_time'].iloc[0]) * 365) - 1
    results.loc[0, '年化收益'] = str(round(annual_return, 2))

    # ===计算最大回撤，最大回撤的含义：《如何通过3行代码计算最大回撤》https://mp.weixin.qq.com/s/Dwt4lkKR_PEnWRprLlvPVw
    # 计算当日之前的资金曲线的最高点
    equity_curve['max2here'] = equity_curve['equity_curve'].expanding().max()
    # 计算到历史最高值到当日的跌幅，drowdwon
    equity_curve['dd2here'] = equity_curve['equity_curve'] / equity_curve['max2here'] - 1
    # 计算最大回撤，以及最大回撤结束时间
    end_date, max_draw_down = tuple(equity_curve.sort_values(by=['dd2here']).iloc[0][['candle_begin_time', 'dd2here']])
    # 计算最大回撤开始时间
    start_date = \
        equity_curve[equity_curve['candle_begin_time'] <= end_date].sort_values(by='equity_curve',
                                                                                ascending=False).iloc[0][
            'candle_begin_time']
    # 将无关的变量删除
    equity_curve.drop(['max2here', 'dd2here'], axis=1, inplace=True)
    results.loc[0, '最大回撤'] = format(max_draw_down, '.2%')
    results.loc[0, '最大回撤开始时间'] = str(start_date)
    results.loc[0, '最大回撤结束时间'] = str(end_date)

    # ===年化收益/回撤比
    results.loc[0, '年化收益/回撤比'] = round(annual_return / abs(max_draw_down), 2)

    # ===统计每笔交易
    results.loc[0, '盈利笔数'] = len(trade.loc[trade['change'] > 0])  # 盈利笔数
    results.loc[0, '亏损笔数'] = len(trade.loc[trade['change'] <= 0])  # 亏损笔数
    results.loc[0, '胜率'] = format(results.loc[0, '盈利笔数'] / len(trade), '.2%')  # 胜率

    results.loc[0, '每笔交易平均盈亏'] = format(trade['change'].mean(), '.2%')  # 每笔交易平均盈亏
    results.loc[0, '盈亏收益比'] = round(trade.loc[trade['change'] > 0]['change'].mean() / \
                                         trade.loc[trade['change'] < 0]['change'].mean() * (-1), 2)  # 盈亏比

    results.loc[0, '单笔最大盈利'] = format(trade['change'].max(), '.2%')  # 单笔最大盈利
    results.loc[0, '单笔最大亏损'] = format(trade['change'].min(), '.2%')  # 单笔最大亏损

    # ===统计持仓时间，会比实际时间少一根K线的是距离
    trade['持仓时间'] = trade['end_bar'] - trade.index
    max_days, max_seconds = trade['持仓时间'].max().days, trade['持仓时间'].max().seconds
    max_hours = max_seconds // 3600
    max_minute = (max_seconds - max_hours * 3600) // 60
    results.loc[0, '单笔最长持有时间'] = str(max_days) + ' 天 ' + str(max_hours) + ' 小时 ' + str(
        max_minute) + ' 分钟'  # 单笔最长持有时间

    min_days, min_seconds = trade['持仓时间'].min().days, trade['持仓时间'].min().seconds
    min_hours = min_seconds // 3600
    min_minute = (min_seconds - min_hours * 3600) // 60
    results.loc[0, '单笔最短持有时间'] = str(min_days) + ' 天 ' + str(min_hours) + ' 小时 ' + str(
        min_minute) + ' 分钟'  # 单笔最短持有时间

    mean_days, mean_seconds = trade['持仓时间'].mean().days, trade['持仓时间'].mean().seconds
    mean_hours = mean_seconds // 3600
    mean_minute = (mean_seconds - mean_hours * 3600) // 60
    results.loc[0, '平均持仓周期'] = str(mean_days) + ' 天 ' + str(mean_hours) + ' 小时 ' + str(
        mean_minute) + ' 分钟'  # 平均持仓周期

    # ===连续盈利亏算
    results.loc[0, '最大连续盈利笔数'] = max(
        [len(list(v)) for k, v in itertools.groupby(np.where(trade['change'] > 0, 1, np.nan))])  # 最大连续盈利笔数
    results.loc[0, '最大连续亏损笔数'] = max(
        [len(list(v)) for k, v in itertools.groupby(np.where(trade['change'] < 0, 1, np.nan))])  # 最大连续亏损笔数

    # ===每月收益率
    equity_curve.set_index('candle_begin_time', inplace=True)
    monthly_return = equity_curve[['equity_change']].resample(rule='M').apply(lambda x: (1 + x).prod() - 1)

    # ===平均月化收益
    monthly_return_mean = (total_return ** (30 / time_difference_in_days)) - 1
    results['月化收益'] = monthly_return_mean

    return results.T, monthly_return


def return_drawdown_ratio(equity_curve):
    """
    :param equity_curve: 带资金曲线的df
    :param trade: transfer_equity_curve_to_trade的输出结果，每笔交易的df
    :return:
    """

    # ===计算年化收益
    annual_return = (equity_curve['equity_curve'].iloc[-1] / equity_curve['equity_curve'].iloc[0]) ** (
            '1 days 00:00:00' / (
            equity_curve['candle_begin_time'].iloc[-1] - equity_curve['candle_begin_time'].iloc[0]) * 365) - 1

    # ===计算最大回撤，最大回撤的含义：《如何通过3行代码计算最大回撤》https://mp.weixin.qq.com/s/Dwt4lkKR_PEnWRprLlvPVw
    # 计算当日之前的资金曲线的最高点
    equity_curve['max2here'] = equity_curve['equity_curve'].expanding().max()
    # 计算到历史最高值到当日的跌幅，drowdwon
    equity_curve['dd2here'] = equity_curve['equity_curve'] / equity_curve['max2here'] - 1
    # 计算最大回撤，以及最大回撤结束时间
    end_date, max_draw_down = tuple(equity_curve.sort_values(by=['dd2here']).iloc[0][['candle_begin_time', 'dd2here']])

    # ===年化收益/回撤比
    sharpe = annual_return / abs(max_draw_down)

    return annual_return, max_draw_down, sharpe


def shift_evaluate(equity, net_col='shift_equity', pct_col='shift_pct'):
    '''
    评估轮动策略整体表现
    :param equity: 资金曲线表
    :param net_col: 净值列名
    :param pct_col: 净值涨跌幅列名
    '''
    # ===新建一个dataframe保存回测指标
    results = pd.DataFrame()

    # 将数字转为百分数
    def num_to_pct(value):
        return '%.2f%%' % (value * 100)
    
    # ===计算累积净值
    results.loc[0, '累积净值'] = round(equity[net_col].iloc[-1], 2)

    # ===计算总收益
    total_return = equity[net_col].iloc[-1] / equity[net_col].iloc[0]
    # 计算时间差，并转换为天数
    time_difference = (equity['candle_begin_time'].iloc[-1] - equity['candle_begin_time'].iloc[0])
    time_difference_in_days = int(time_difference.total_seconds() / (60 * 60 * 24))

    # ===计算年化收益
    annual_return = (total_return ** (365 / time_difference_in_days)) - 1
    results.loc[0, '年化收益'] = str(round(annual_return, 2))

    # ===计算回撤
    # 计算当日之前的资金曲线的最高点
    equity['max2here'] = equity[net_col].expanding().max()
    # 计算到历史最高值到当日的跌幅，drowdwon
    equity['dd2here'] = equity[net_col] / equity['max2here'] - 1
    # 计算最大回撤，以及最大回撤结束时间
    end_date, max_draw_down = tuple(equity.sort_values(by=['dd2here']).iloc[0][['candle_begin_time', 'dd2here']])
    # 计算最大回撤开始时间
    start_date = equity[equity['candle_begin_time'] <= end_date].sort_values(by=net_col, ascending=False).iloc[0]['candle_begin_time']
    # 将无关的变量删除
    # temp.drop(['max2here', 'dd2here'], axis=1, inplace=True)
    results.loc[0, '最大回撤'] = num_to_pct(max_draw_down)
    results.loc[0, '最大回撤开始时间'] = str(start_date)
    results.loc[0, '最大回撤结束时间'] = str(end_date)

    # ===年化收益/回撤比：我个人比较关注的一个指标
    results.loc[0, '年化收益/回撤比'] = round(annual_return / abs(max_draw_down), 2)

    # ===统计每个周期
    results.loc[0, '盈利周期数'] = len(equity.loc[equity[pct_col] > 0])  # 盈利笔数
    results.loc[0, '亏损周期数'] = len(equity.loc[equity[pct_col] <= 0])  # 亏损笔数
    results.loc[0, '胜率'] = num_to_pct(results.loc[0, '盈利周期数'] / len(equity))  # 胜率
    results.loc[0, '每周期平均收益'] = num_to_pct(equity[pct_col].mean())  # 每笔交易平均盈亏
    results.loc[0, '盈亏收益比'] = round(equity.loc[equity[pct_col] > 0][pct_col].mean() / equity.loc[equity[pct_col] <= 0][pct_col].mean() * (-1), 2)  # 盈亏比
    results.loc[0, '单周期最大盈利'] = num_to_pct(equity[pct_col].max())  # 单笔最大盈利
    results.loc[0, '单周期大亏损'] = num_to_pct(equity[pct_col].min())  # 单笔最大亏损

    # ===连续盈利亏损
    results.loc[0, '最大连续盈利周期数'] = max(
        [len(list(v)) for k, v in itertools.groupby(np.where(equity[pct_col] > 0, 1, np.nan))])  # 最大连续盈利次数
    results.loc[0, '最大连续亏损周期数'] = max(
        [len(list(v)) for k, v in itertools.groupby(np.where(equity[pct_col] <= 0, 1, np.nan))])  # 最大连续亏损次数

    # ===其他评价指标
    results.loc[0, '收益率标准差'] = num_to_pct(equity[pct_col].std())

    # ===每年、每月收益率
    temp = equity.copy()
    temp.set_index('candle_begin_time', inplace=True)
    year_return = temp[[pct_col]].resample(rule='A').apply(lambda x: (1 + x).prod() - 1)
    month_return = temp[[pct_col]].resample(rule='M').apply(lambda x: (1 + x).prod() - 1)

    def num2pct(x):
        if str(x) != 'nan':
            return str(round(x * 100, 2)) + '%'
        else:
            return x

    year_return['涨跌幅'] = year_return[pct_col].apply(num2pct)

    # 对每月收益进行处理，做成二维表
    month_return.reset_index(inplace=True)
    month_return['year'] = month_return['candle_begin_time'].dt.year
    month_return['month'] = month_return['candle_begin_time'].dt.month
    month_return.set_index(['year', 'month'], inplace=True)
    del month_return['candle_begin_time']
    month_return_all = month_return[pct_col].unstack()
    month_return_all.loc['mean'] = month_return_all.mean(axis=0)
    month_return_all = month_return_all.apply(lambda x: x.apply(num2pct))

    return results, year_return[['涨跌幅']], month_return_all

def shift_substg_evaluate(equity, net_col='shift_equity', pct_col='shift_pct'):
    '''
    计算每个
    '''

    return