'''
CTA核心回测程序
'''
import warnings
import pandas as pd
import os
from datetime import datetime
from joblib import Parallel,delayed
from config import *
from cta_api.function import cal_equity_curve
from cta_api.statistics import transfer_equity_curve_to_trade,strategy_evaluate
from cta_api.position import *
from cta_api.evaluate import *
from cta_api.tools import *

pd.set_option('display.max_rows', 1000)
pd.set_option('expand_frame_repr', False)  # 当列太多时不换行
pd.set_option('display.unicode.ambiguous_as_wide', True)  # 设置命令行输出时的列对齐功能
pd.set_option('display.unicode.east_asian_width', True)

def calculate_base_by_one_loop(symbol,rule_type,offset):
    """
    处理每个传递进来的币种
    :param symbol: 币种名称，是一个字符串，对应我们全量数据中币种的文件名，注意：不包含.csv
    :return:
        返回币种的回测结果，包含累积币种名称、净值、年化收益最大回撤、年化收益回撤比字段
    """
    warnings.filterwarnings('ignore')
    print(symbol)
    # ===== 读取数据
    # === 读取原始的csv数据
    df = pd.read_feather(os.path.join(data_path, rule_type, symbol + '.pkl'))
    df = df[df['offset']==offset]

    # ===== 计算资金曲线
    # === 设置持有信号
    df['pos'] = 1  # 强制设置持有为1，即从回测开始买入，一直持有

    # === 计算资金曲线
    min_amount = min_amount_dict[symbol]  # 获取最小下单量
    df = cal_equity_curve(df, slippage=slippage, c_rate=c_rate, leverage_rate=leverage_rate, min_amount=min_amount, min_margin_ratio=min_margin_ratio)  # 计算资金曲线

    # === 策略评价
    original_trade = transfer_equity_curve_to_trade(df)  # 将含有资金曲线的df转化为每笔交易
    original, _ = strategy_evaluate(df, original_trade, rule_type)  # 计算策略各种评价指标
    # === 保存需要的指标数据
    rtn = pd.DataFrame()  # 创建一个空的df对象
    rtn.loc[0, '币种'] = symbol  # 保存币种名称
    rtn.loc[0, '累积净值'] = original.loc['累积净值', 0]  # 保存累积净值
    rtn.loc[0, '年化收益'] = original.loc['年化收益', 0]  # 保存年化收益
    rtn.loc[0, '最大回撤'] = original.loc['最大回撤', 0]  # 保存最大回撤
    rtn.loc[0, '年化收益/回撤比'] = original.loc['年化收益/回撤比', 0]  # 保存年化收益回撤比
    return rtn

def calculate_signal_by_one_loop(symbol,rule_type,offset):
    """
    处理每个传递进来的币种
    :param symbol: 币种名称，是一个字符串，对应我们全量数据中币种的文件名，注意：不包含.csv
    :return:
        返回币种的回测结果，包含累积币种名称、净值、年化收益最大回撤、年化收益回撤比字段
    """
    warnings.filterwarnings('ignore')
    print(symbol)
    # ===== 读取数据
    # === 读取数据
    df_orgin = pd.read_feather(os.path.join(data_path, rule_type, symbol + '.pkl'))
    df_orgin = df_orgin[df_orgin['offset']==offset]
    
    # === 计算交易信号
    for signal_name in signal_name_list:
        df = df_orgin.copy()
        cls = __import__('factors.%s' % signal_name, fromlist=('',))
        df = cls.signal(df, para=para, proportion=proportion, leverage_rate=leverage_rate)

        # === 计算实际持仓
        df = position_for_future(df)  # 调用函数，计算实际的持仓

        # 过滤出我们所要计算的区间
        df = df[(df['candle_begin_time'] >= pd.to_datetime(date_start))&(df['candle_begin_time'] <= pd.to_datetime(date_end))]

        # === 计算资金曲线
        min_amount = min_amount_dict[symbol]  # 获取最小下单量
        try:
            df = cal_equity_curve(df, slippage=slippage, c_rate=c_rate, leverage_rate=leverage_rate, min_amount=min_amount, min_margin_ratio=min_margin_ratio)  # 计算资金曲线
        except Exception as e:
            print(f'错误代码:{e}，可能是策略没有开仓信号')
            return
        

        print('策略最终收益：', df.iloc[-1]['equity_curve'])  # 输出策略的最终收益，即最后一行的equity_curve
        # ==== 输出资金曲线文件
        # === 处理数据
        df_output = df[['candle_begin_time', 'open', 'high', 'low', 'close', 'signal', 'pos', 'quote_volume', 'kline_pct', 'equity_curve']]  # 筛选一下需要的列，避免把所有的列都存在内存中，避免加大内存的压力
        df_output.rename(columns={'median': 'line_median', 'upper': 'line_upper', 'lower': 'line_lower', 'quote_volume': 'b_bar_quote_volume', 'equity_curve': 'r_line_equity_curve'}, inplace=True)  # 对指定列名重命名，方便我们看数据是容易理解
        equity_path = os.path.join(root_path,'data/output/equity_curve')
        if os.path.exists(equity_path) == False:
            os.makedirs(equity_path)
        df_output.reset_index(drop=True, inplace=True)
        df_output.to_csv(os.path.join(equity_path,'%s&%s&%s&%s.csv') % (signal_name, symbol.split('-')[0], rule_type, str(para)), index=False, encoding='gbk')  # 以GBK编码并且删除index保存csv文件
        # df_output.to_feather(os.path.join(equity_path,'%s&%s&%s&%s.pkl') % (signal_name, symbol.split('-')[0], rule_type, str(para)))
        
        # ==== 策略评价
        # === 计算每笔交易
        trade = transfer_equity_curve_to_trade(df)  # 调用函数，通过带有资金曲线的df计算每笔交易
        # print('逐笔交易：\n', trade)  # 输出每笔交易

        # === 计算各类统计指标
        # 计算策略评价指标
        df_copy = df.copy()
        rtn, monthly_return = strategy_evaluate(df_copy, trade, rule_type)  # 调用函数策略评价指标，需要传入带有资金曲线的df以及每笔交易数据
        # 输出策略评价指标数据
        print(rtn)  # 输出策略评价指标
        # print(monthly_return)  # 输出每月收益率

        # === 绘制资金曲线
        # 拼接资金曲线的图片标题
        title = symbol + '_' + signal_name + '_' + str(para) + '_' + str(rule_type)  # 拼接一下资金曲线的图片标题，即币种名称+回测参数
        # 绘制资金曲线
        if os.path.exists(os.path.join(root_path,'data/output/pic')) == False:
            os.makedirs(os.path.join(root_path,'data/output/pic'))
        draw_equity_curve_mat_V1(df, rtn.T, trade, title, path=os.path.join(root_path,f'data/output/pic/{title}.html'),show=False)  # 调用函数绘制资金曲线，需要传入带有资金曲线的df、每笔交易数据以及图片的标题

    return

def fast_calculate_signal_by_one_loop(signal_name, symbol, para, rule_type, offset):
    """
    处理每个传递进来的币种
    :param symbol: 币种名称，是一个字符串，对应我们全量数据中币种的文件名，注意：不包含.csv
    :return:
        返回币种的回测结果，包含累积币种名称、净值、年化收益最大回撤、年化收益回撤比字段
    """
    warnings.filterwarnings('ignore')
    print(symbol)
    # ===== 读取数据
    # === 读取数据
    df_orgin = pd.read_feather(os.path.join(data_path, rule_type, symbol + '.pkl'))
    df_orgin = df_orgin[df_orgin['offset']==offset]
    
    # === 计算交易信号
    df = df_orgin.copy()
    cls = __import__('factors.%s' % signal_name, fromlist=('',))
    df = cls.signal(df, para=para, proportion=proportion, leverage_rate=leverage_rate)

    # === 计算实际持仓
    df = position_for_future(df)  # 调用函数，计算实际的持仓

    # 过滤出我们所要计算的区间
    df = df[(df['candle_begin_time'] >= pd.to_datetime(date_start))&(df['candle_begin_time'] <= pd.to_datetime(date_end))]

    # === 计算资金曲线
    min_amount = min_amount_dict[symbol]  # 获取最小下单量
    df = cal_equity_curve(df, slippage=slippage, c_rate=c_rate, leverage_rate=leverage_rate, min_amount=min_amount, min_margin_ratio=min_margin_ratio)  # 计算资金曲线

    # print(df)  # 输出计算资金曲线后的df
    print(f'{signal_name}_{symbol}_{para}_策略最终收益：', df.iloc[-1]['equity_curve'])  # 输出策略的最终收益，即最后一行的equity_curve
    # ==== 输出资金曲线文件
    # === 处理数据
    df_output = df[['candle_begin_time', 'open', 'high', 'low', 'close', 'signal', 'pos', 'quote_volume', 'kline_pct', 'equity_curve']]  # 筛选一下需要的列，避免把所有的列都存在内存中，避免加大内存的压力
    df_output.rename(columns={'median': 'line_median', 'upper': 'line_upper', 'lower': 'line_lower', 'quote_volume': 'b_bar_quote_volume', 'equity_curve': 'r_line_equity_curve'}, inplace=True)  # 对指定列名重命名，方便我们看数据是容易理解
    equity_path = os.path.join(root_path,'data/output/equity_curve')
    if os.path.exists(equity_path) == False:
        os.makedirs(equity_path)
    df_output.reset_index(drop=True, inplace=True)
    df_output.to_csv(os.path.join(equity_path,'%s&%s&%s&%s.csv') % (signal_name, symbol.split('-')[0], rule_type, str(para)), index=False, encoding='gbk')  # 以GBK编码并且删除index保存csv文件

    if is_pic:
        # ==== 策略评价
        # === 计算每笔交易
        trade = transfer_equity_curve_to_trade(df)  # 调用函数，通过带有资金曲线的df计算每笔交易

        # === 计算各类统计指标
        # 计算策略评价指标
        df_copy = df.copy()
        rtn, monthly_return = strategy_evaluate(df_copy, trade, rule_type)  # 调用函数策略评价指标，需要传入带有资金曲线的df以及每笔交易数据

        # === 绘制资金曲线
        # 拼接资金曲线的图片标题
        title = symbol + '_' + signal_name + '_' + str(para) + '_' + str(rule_type)  # 拼接一下资金曲线的图片标题，即币种名称+回测参数
        # 绘制资金曲线
        if os.path.exists(os.path.join(root_path,'data/output/pic')) == False:
            os.makedirs(os.path.join(root_path,'data/output/pic'))
        draw_equity_curve_mat_V1(df, rtn.T, trade, title, path=os.path.join(root_path,f'data/output/pic/{title}.html'),show=False)  # 调用函数绘制资金曲线，需要传入带有资金曲线的df、每笔交易数据以及图片的标题

    return
    
@timing_decorator
def base_data(symbol_list,rule_type,multiple_process):
    '''
    计算基准数据
    '''
    # === 开始进行回测
    if multiple_process:
        df_list = Parallel(os.cpu_count()-1)(delayed(calculate_base_by_one_loop)(symbol,rule_type,offset) for symbol in symbol_list)
    else:
        df_list = []  # 定义一个空的列表，用来保存回测的结果
        # 循环每个币种
        for symbol in symbol_list:
            res_df = calculate_base_by_one_loop(symbol,rule_type,offset)  # 调用回测的函数，返回回测结果
            df_list.append(res_df)  # 将回测结果累加到df_list，用于后续合并大表使用
    # ==== 整理回测后的数据
    # === 将df_list内所有的回测结果合并，作为一个大表，并重新设置一下index
    para_curve_df = pd.concat(df_list, ignore_index=True)  # 合并为一个大的DataFrame
    # === 对数据进行排序
    para_curve_df.sort_values(by='年化收益/回撤比', ascending=False, inplace=True)  # 将数据根据年化收益回撤比降序排序

    return para_curve_df

@timing_decorator
def stg_date(symbol,rule_type,multiple_process):
    # === 开始进行回测
    if multiple_process:
        Parallel(os.cpu_count()-1)(delayed(calculate_signal_by_one_loop)(symbol,rule_type,offset) for symbol in symbol_list)
    else:
        df_list = []  # 定义一个空的列表，用来保存回测的结果
        # 循环每个币种
        for symbol in symbol_list:
            calculate_signal_by_one_loop(symbol,rule_type,offset)  # 调用回测的函数，返回回测结果
