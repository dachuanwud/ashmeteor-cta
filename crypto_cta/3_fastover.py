import warnings
from datetime import datetime
from datetime import timedelta
from functools import partial
from multiprocessing import Pool, cpu_count
from config import *
from cta_api.evaluate import *
from cta_api.position import *
from cta_api.function import *
from cta_api.statistics import *
from cta_api.cta_core import *
from dateutil.relativedelta import relativedelta

def calculate_by_one_loop(para, df, signal_name, symbol, rule_type, min_amount, start, end):
    """
    回测每个传递进来的数据
    :param para:    回测参数
    :param df:  原始数据
    :param signal_name: 策略名称
    :param symbol:  币种名称
    :param rule_type:   回测时间周期
    :param min_amount:  最小下单量
    :return:
        返回币种的回测结果，包含累积币种名称、净值、年化收益最大回撤、年化收益回撤比字段
    """
    warnings.filterwarnings('ignore')
    # ==== 获取数据
    # === 对原始数据进行copy
    _df = df.copy()  # 先对数据进行copy，避免修改原始数据

    # === 计算交易信号
    cls = __import__('factors.%s' % signal_name, fromlist=('',))
    _df = cls.signal(_df, para=para, proportion=proportion,leverage_rate=leverage_rate)  # 调用传递过来的signal名称生成signal信号

    # === 计算实际持仓
    _df = position_for_future(_df)  # 调用函数，计算实际的持仓

    # 过滤出我们所要计算的区间
    _df = _df[(_df['candle_begin_time'] >= pd.to_datetime(start))&(_df['candle_begin_time'] <= pd.to_datetime(end))]

    # ===== 计算资金曲线
    # === 计算资金曲线
    try:
        _df = cal_equity_curve(_df, slippage=slippage, c_rate=c_rate, leverage_rate=leverage_rate, min_amount=min_amount, min_margin_ratio=min_margin_ratio)  # 计算资金曲线
    except Exception as e:
        print(f'错误代码:{e},可能是没有开仓导致')
        return pd.DataFrame()

    if cover_curve == True:
        _df_output = _df[['candle_begin_time', 'open', 'high', 'low', 'close', 'signal', 'pos', 'quote_volume', 'equity_curve']].copy()
        _df_output.rename(columns={'median': 'line_median', 'upper': 'line_upper', 'lower': 'line_lower', 'quote_volume': 'b_bar_quote_volume', 'equity_curve': 'r_line_equity_curve'}, inplace=True)  # 对指定列名重命名，方便我们看数据是容易理解
        _df_output.to_csv(os.path.join(root_path,'data/output/para_equity_curve/%s&%s&%s&%s.csv') % (signal_name, symbol.split('-')[0], rule_type, str(para)), index=False, encoding='gbk')  # 以GBK编码并且删除index保存csv文件
    # ==== 策略评价
    # === 计算每笔交易
    trade = transfer_equity_curve_to_trade(_df)  # 调用函数，通过带有资金曲线的df计算每笔交易
    # 判断每笔交易是否为空，如果为空即为没有触发信号，直接返回空的数据
    if trade.empty:  # 判断trade是否为空
        return pd.DataFrame()  # 返回一个空的df

    # === 计算各类统计指标
    # 计算策略评价指标
    r, monthly_return = strategy_evaluate(_df, trade,rule_type)  # 调用函数策略评价指标，需要传入带有资金曲线的df以及每笔交易数据
    # 保存策略收益
    rtn = pd.DataFrame()  # 创建一个新的df，用于保存回测的指标数据
    rtn.loc[0, 'para'] = str(para)  # 保存回测的参数
    # 遍历所有计算出来的策略评价指标，进行保存
    for i in r.index:  # 遍历所有的index
        rtn.loc[0, i] = r.loc[i, 0]  # 进行保存
    # 输出一下回测的结果
    print(signal_name, symbol, rule_type, para, '策略收益：', r.loc['累积净值', 0])  # 输出策略名称、币种、回测时间周期、策略的累积净值
    # 返回回测的详情数据
    return rtn

def run_playblack(signal_name,symbol,rule_type,start,end):
    # ===== 输出一下回测的详情
    print('开始遍历该策略参数：', signal_name, symbol, rule_type,start,end)  # 输出当前要回测的策略名称、币种、回测时间周期
    # ==== 读入数据
    df = pd.read_feather(os.path.join(data_path, rule_type, symbol + '.pkl'))

    # 检测回测区间是否有数据
    df_ = df.copy()
    df_ = df_[df_['candle_begin_time'] >= pd.to_datetime(start)]  # 筛选时间大于等于我们指定的回测开始时间
    df_ = df_[df_['candle_begin_time'] <= pd.to_datetime(end)]  # 筛选时间小于等于我们指定的回测结束时间

    if df_.empty:
        print(f'{start}-{end},该区间没有数据')
        return

    # ==== 读取信号
    cls = __import__('factors.%s' % signal_name, fromlist=('',))
    # === 获取策略参数组合
    para_list = cls.para_list()  # 根据遍历到的策略名称，获取当前策略的遍历参数
    # === 并行回测
    # 标记开始时间
    start_time = datetime.now()  # 标记开始时间
    # 利用partial指定参数值
    part = partial(calculate_by_one_loop, df=df, signal_name=signal_name, symbol=symbol, rule_type=rule_type, min_amount=min_amount, start=start, end=end)  # 使用便函数指定所有固定的参数
    
    multiple_process = True  # 设置是否并行，True为并行，False为串行
    # === 开始进行回测
    if multiple_process:
        with Pool(max(cpu_count() - 1, 1)) as pool:
            # 使用并行批量获得data frame的一个列表
            df_list = pool.map(part, para_list)
    else:
        df_list = []  # 定义一个空的列表，用来保存回测的结果
         # 循环每个参数
        for para in para_list:
            res_df = calculate_by_one_loop(para=para, df=df, signal_name=signal_name, symbol=symbol, rule_type=rule_type, min_amount=min_amount, start=start, end=end)  # 调用回测的函数，返回回测结果
            df_list.append(res_df)  # 将回测结果累加到df_list，用于后续合并大表使用

    print('读入完成, 开始合并', datetime.now() - start_time)  # 回测结束，输出一下使用的时间

    # ==== 整理回测后的数据
    # === 将df_list内所有的回测结果合并，作为一个大表，并重新设置一下index
    para_curve_df = pd.concat(df_list, ignore_index=True)  # 合并为一个大的DataFrame

    # ==== 读取基准数据，即从回测开始持有到回测结束的结果
    # 拼接一下基本数据的路径
    p = root_path + '/data/output/para/基准&%s&%s.csv' % (leverage_rate, rule_type)  # 拼接数据保存的路径
    original = pd.read_csv(p, encoding='gbk')  # 以GBK编码读取基本数据的csv文件
    # ==== 合并基准数据
    para_curve_df['币种原始累积净值'] = original.loc[original['币种'] == symbol].iloc[0]['累积净值']  # 合并基准累积净值
    para_curve_df['币种原始年化收益'] = original.loc[original['币种'] == symbol].iloc[0]['年化收益']  # 合并基准年化收益
    para_curve_df['币种原始最大回撤'] = original.loc[original['币种'] == symbol].iloc[0]['最大回撤']  # 合并基准最大回撤
    para_curve_df['币种原始年化收益/回撤比'] = original.loc[original['币种'] == symbol].iloc[0]['年化收益/回撤比']  # 合并基准年化收益回撤比

    # ==== 标记回测区间
    para_curve_df['回测区间'] = f'{start}_{end}'

    # ==== 整理回测后的数据
    # === 对数据进行排序
    para_curve_df.sort_values(by='年化收益/回撤比', ascending=False, inplace=True)  # 将数据根据年化收益回撤比降序排序
    print(para_curve_df.head(10))  # 输出前10行数据

    # === 保存回测后的结果
    result_path = root_path + '/data/output/para/%s&%s&%s&%s.csv' % (signal_name, symbol, leverage_rate, rule_type)  # 拼接数据保存的路径
    
    # === 保存文件
    if os.path.exists(result_path):  # 如果文件存在，往原有的文件中添加新的结果
        para_curve_df.to_csv(result_path, index=False, header=False, mode='a', encoding='gbk')
    else:
        para_curve_df.to_csv(result_path, index=False, encoding='gbk')
    if cover_curve == True:
        equity_df_list = []
        for para in para_list:
            equity_df = pd.read_csv(os.path.join(root_path,'data/output/para_equity_curve/%s&%s&%s&%s.csv') % (signal_name, symbol.split('-')[0], rule_type, str(para)),encoding='gbk')
            equity_df['equity_pct'] = equity_df['r_line_equity_curve'].pct_change()
            equity_df.fillna(0,inplace=True)
            equity_df_list.append(equity_df)
        tot_equity_df = pd.concat(equity_df_list,ignore_index=True,axis=0)
        cover_df = tot_equity_df.groupby('candle_begin_time',as_index=False)['equity_pct'].mean()
        cover_df['equity'] = (1 + cover_df['equity_pct']).cumprod()
        cover_df['maxh'] = cover_df['equity'].cummax()
        cover_df['回撤'] = cover_df['equity'] / cover_df['maxh'] - 1
        title = f'{symbol}_{signal_name}_{rule_type}_{start}_{end}_cover'
        draw_equity_curve_plotly(cover_df, data_dict={'equity':'equity'}, date_col='candle_begin_time', right_axis={'最大回撤':'回撤'}, title=title, path=os.path.join(root_path,f'data/output/para_pic/{title}.html'), show=False)
    
    # ==== 输出一下本轮回测使用的时间
    print(datetime.now() - start_time)  # 输出回测时间

    return

if __name__ == '__main__':
    # 计算基准数据
    print('计算基准数据')
    multiple_process = True  # 设置是否并行，True为并行，False为串行
    for rule_type in rule_type_list:
        para_curve_df = base_data(symbol_list,rule_type,multiple_process)
        # === 保存回测后的结果
        result_path = root_path + '/data/output/para/'
        if os.path.exists(result_path) == False:
            os.makedirs(result_path)
        para_curve_df.to_csv(os.path.join(result_path,f'基准&{leverage_rate}&{rule_type}.csv'), index=False, encoding='gbk')  # 以GBK编码并且删除index保存csv文件

    # ==== 遍历所有的策略
    # 遍历指定的策略
    for signal_name in signal_name_list:
        # 遍历不同的币种
        for symbol in symbol_list:
            # 获取当前币种的最小下单量
            min_amount = min_amount_dict[symbol]  # 获取最小下单量
            # 遍历不同的周期
            for rule_type in rule_type_list:
                result_path = root_path + '/data/output/para/%s&%s&%s&%s.csv' % (signal_name, symbol, leverage_rate, rule_type)  # 拼接数据保存的路径
                if del_mode:
                    # 启动删除模式
                    print('删除模式')
                    if os.path.exists(result_path):
                        print('存在历史文件，正在删除')
                        os.remove(result_path)
                if per_eva == 'm':
                    # 按月遍历
                    start = pd.to_datetime(date_start)
                    end = start + relativedelta(months=+1)
                    while end <= pd.to_datetime(date_end):
                        run_playblack(signal_name,symbol,rule_type,start,end)
                        start = end
                        end += relativedelta(months=+1)
                elif per_eva == 'y':
                    # 按年遍历
                    start = pd.to_datetime(date_start)
                    end = start + relativedelta(years=+1)
                    while end <= pd.to_datetime(date_end):
                        run_playblack(signal_name,symbol,rule_type,start,end)
                        start = end
                        end += relativedelta(years=+1)
                elif per_eva == 'w':
                    # 按年遍历
                    start = pd.to_datetime(date_start)
                    end = start + relativedelta(weeks=+1)
                    while end <= pd.to_datetime(date_end):
                        run_playblack(signal_name,symbol,rule_type,start,end)
                        start = end
                        end += relativedelta(weeks=+1)
                else:
                    start = date_start
                    end = date_end
                    run_playblack(signal_name,symbol,rule_type,start,end)

                        
