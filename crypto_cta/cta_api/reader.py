import pandas as pd
import numpy as np
import os
import ast
from config import root_path, para_equity

def read_csv(path):
    '''
    读取csv文件，如果路径不存在则返回空表
    '''
    if os.path.exists(path):
        df = pd.read_csv(path, encoding="gbk", parse_dates=['candle_begin_time'])
    else:
        df = pd.DataFrame()
    return df

def shift_read(equity_name):
    '''
    读取轮动子资金曲线，并进行一些预处理
    '''
    if para_equity:
        path = os.path.join(root_path,f'data/output/para_equity_curve/{equity_name}.csv')
    else:
        path = os.path.join(root_path,f'data/output/equity_curve/{equity_name}.csv')
    df = pd.read_csv(path,encoding='gbk',parse_dates=['candle_begin_time'])
    # 解析字符串并转换为 NumPy 数组
    df['kline_pct'] = df['kline_pct'].apply(lambda x: np.fromstring(x.strip('[]'), sep=' '))
    # 删除无用列
    # df = df[['candle_begin_time','close','signal','pos','r_line_equity_curve']]
    df.rename({'r_line_equity_curve':'equity'},axis=1,inplace=True)
    df['equity_pct'] = df['equity'].pct_change()
    symbol = equity_name.split('&')[1]
    df['symbol'] = symbol

    return df


