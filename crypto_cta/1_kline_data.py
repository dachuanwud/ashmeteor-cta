'''
这是一个依赖于新版数据中心的数据处理脚本
本数据处理脚本利用新版数据中心原始数据进行处理
'''
import pandas as pd
import numpy as np
import sys
import ast
from config import *
from glob import glob
from joblib import Parallel,delayed
import os
from cta_api.function import transfer_to_period_data, get_benchmark
from datetime import timedelta

def read_symbol_csv(path):
    df = pd.read_csv(path,encoding='utf-8',compression='zip',
                     names=['open_time', 'open', 'high', 'low', 'close', 'volume',
                            'close_time', 'quote_volume', 'trade_num',
                            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume',
                            'ignore'])
    return df

if __name__ == '__main__':
    if len(sys.argv)>1:
        symbol_list = sys.argv[1]
        symbol_list = ast.literal_eval(symbol_list)

    # 从数据中心读取原始数据
    for symbol in symbol_list:
        if '-' in symbol:
            symbol = symbol.replace('-','')
        for rule_type in rule_type_list:
            print(symbol,rule_type)
            path_list = glob(os.path.join(data_center_path,'*',symbol,'*'))
            path_list = [_ for _ in path_list if not _.endswith('.CHECKSUM')]
            df_list = Parallel(os.cpu_count() - 1)(delayed(read_symbol_csv)(path) for path in path_list)
            df = pd.concat(df_list,ignore_index=True)
            df = df[df['open_time'] != 'open_time']
            # 规范数据类型，防止计算avg_price报错
            df = df.astype(
                dtype={'open_time': np.int64, 'open': np.float64, 'high': np.float64, 'low': np.float64, 'close': np.float64, 'volume': np.float64,
                    'quote_volume': np.float64,
                    'trade_num': int, 'taker_buy_base_asset_volume': np.float64, 'taker_buy_quote_asset_volume': np.float64})
            df['avg_price'] = df['quote_volume'] / df['volume']  # 增加 均价
            df = df.drop(columns=['close_time', 'ignore'])
            df = df.sort_values(by='open_time')  # 排序
            df = df.drop_duplicates(subset=['open_time'], keep='last')  # 去除重复值
            df = df.reset_index(drop=True)  # 重置index
            agg_dict = {
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum',
                'quote_volume': 'sum',
                'trade_num': 'sum',
                'taker_buy_base_asset_volume': 'sum',
                'taker_buy_quote_asset_volume': 'sum',
                'avg_price': 'first'
            }
            df['candle_begin_time'] = pd.to_datetime(df['open_time'], unit='ms')
            del df['open_time']
            # 增加因子名列
            df['symbol'] = symbol.replace('-USDT','USDT')
            df = transfer_to_period_data(df,rule_type)
            # 对数据进行一些容错处理
            _benchmark = get_benchmark(df['candle_begin_time'].min(), df['candle_begin_time'].max(), freq=rule_type)
            df = pd.merge(left=_benchmark,right=df,on='candle_begin_time',how='left')
            df = df.ffill()
            if rule_type == '1H':
                df['kline_pct'] = df['close'].pct_change()
                df['kline_pct'] = df['kline_pct'].apply(lambda x:[x])
            df = df[df['candle_begin_time'] >= pd.to_datetime('2020-01-01')]
            df.reset_index(inplace=True, drop=True)
            df = df[head_column]

            # === 对数据进行时间筛选
            # 保留币种上线N天之后的日期
            t = df.iloc[0]['candle_begin_time'] + timedelta(days=drop_days)  # 获取第一行数据的日期，并且加上我们指定的天数
            df = df[df['candle_begin_time'] > t]  # 筛选时间
            df = df[df['candle_begin_time'] >= pd.to_datetime('2020-01-01')]  # 约定一下，基准时间为2020年01月01日
            df = df[df['candle_begin_time'] <= pd.to_datetime(date_end)]  # 筛选时间小于等于我们指定的回测结束时间
            df.reset_index(inplace=True, drop=True)     # 重新设置一下index

            # 导出完整数据
            data_save_path = os.path.join(data_path,rule_type)
            if os.path.exists(data_save_path) == False:
                os.makedirs(data_save_path)
            symbol = symbol.replace('USDT','-USDT')
            df.to_feather(os.path.join(data_save_path,f'{symbol}.pkl'))


