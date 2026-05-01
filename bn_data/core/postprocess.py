import os
import datetime
import time
import asyncio
import matplotlib.pyplot as plt
from dateutil.relativedelta import relativedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import groupby
from operator import itemgetter
from joblib import Parallel,delayed
import pandas as pd
import numpy as np
import tqdm
from glob import glob
from config import *
from core.common import get_local_path, get_download_prefix, get_or_create_eventloop
from core.download import download_miss_day_data
from core.bnapi import get_fundingRate_from_aio_api, get_klines_from_aio_api

hold_hour = '8h'

def transfer_daily_to_monthly_and_get_newest(newest_timestamp, daily_list, need_analyse_set):
    sorted_list = sorted(daily_list, key=lambda x: x['local_path'], reverse=False)

    tasks = []

    num = 0
    for local_path, items in groupby(sorted_list, key=itemgetter('local_path')):
        zip_files = []
        day_set = set()
        interval = ''
        symbol = os.path.basename(local_path)
        monthly_path = local_path.replace('daily_', 'monthly_')
        for i in items:
            interval = i['interval']
            zip_files.append(os.path.join(i['local_path'], os.path.basename(i['key'])[0:-9]))
            _day = datetime.datetime.strptime(i['key'][-23:-13], "%Y-%m-%d")
            day_set.add(_day.toordinal())

        days = pd.DataFrame(sorted(list(day_set)))
        if len(days.diff().value_counts()) > 1:
            # daily zip缺失某天或某几天的zip
            need_analyse_set.add(monthly_path)
        df_latest = pd.concat(Parallel(4)(
            delayed(pd.read_csv)(path_, header=None, encoding="utf-8", compression='zip') for path_ in zip_files),
            ignore_index=True)
        df_latest = df_latest[df_latest[0] != 'open_time']
        df_latest = df_latest.astype(dtype={0: np.int64})
        df_latest.sort_values(by=0)
        latest_monthly_zip = os.path.join(monthly_path, f'{symbol}-{interval}-latest.zip')
        if daily_err_occur or local_path in daily_updated_set or not os.path.exists(latest_monthly_zip) or max((os.path.getmtime(file) for file in zip_files)) > os.path.getmtime(latest_monthly_zip):
            if not os.path.exists(monthly_path):
                os.makedirs(monthly_path)
            compression_options = dict(method='zip', archive_name=f'{symbol}-{interval}-latest.csv')
            df_latest.to_csv(latest_monthly_zip, header=None, index=None, compression=compression_options)

        if update_to_now:
            tasks.append(get_klines_from_aio_api(symbol, interval, int(df_latest.iloc[-1, 0]), newest_timestamp,
                                                 os.path.join(monthly_path, f'{symbol}-{interval}-newest.zip')))
        num += 1
        print(f'\r合并完成数量: {num}', end='')
    print('\n合并结束')
    return tasks

def read_symbol_open_time(symbol, zip_path):
    '''
    只读取open_time 用来进行完整性分析
    '''
    zip_list = glob(os.path.join(zip_path, f'{symbol}*.zip'))
    _df = pd.concat(
        Parallel(CONCURRENCY)(delayed(pd.read_csv)(path_, header=None, encoding="utf-8", compression='zip', usecols=[0],
                                                   names=['open_time'], dtype=str, engine='c'
                                                   ) for path_ in zip_list), ignore_index=True)
    # 过滤表头行
    _df = _df[_df['open_time'] != 'open_time']
    # 规范数据类型，并将时间戳转化为可读时间
    _df = _df.astype(dtype={'open_time': np.int64})
    _df['candle_begin_time'] = pd.to_datetime(_df['open_time'], unit='ms')
    _df = _df.sort_values(by='open_time')  # 排序
    _df = _df.drop_duplicates(subset=['open_time'], keep='last')  # 去除重复值
    _df = _df.reset_index(drop=True)  # 重置index
    return _df

def build_analyse_download_task(download_folder, symbol, trading_type, data_type, interval, err_symbols,
                                download_err_info):
    zip_path = get_local_path(download_folder, trading_type, data_type, 'monthly', symbol, interval)
    tasks = []
    if not force_analyse and zip_path not in need_analyse_set:
        # 之前已经分析过数据完整性，本次跳过
        return tasks
    df = read_symbol_open_time(symbol, zip_path)
    df['open_time_diff_1'] = df['open_time'].diff()
    df['open_time_diff_-1'] = df['open_time'].diff(-1)
    df = df[(df['open_time_diff_1'] > interval_microsecond[interval]) | (
        df['open_time_diff_-1'] < -interval_microsecond[interval])]

    if df.size != 0:
        miss_day = []
        msg = []
        df = df.reset_index(drop=True)
        for row in df.index:
            if row % 2 != 0:
                continue
            start = df.loc[row]['candle_begin_time']
            end = df.loc[row + 1]['candle_begin_time']
            if trading_type == 'swap' and str(start) == '2023-08-16 09:03:00' and str(end) == '2023-08-16 09:06:00':
                # bn合约市场都缺了这几分钟
                continue
            if symbol in SETTLED_SYMBOLS:
                if (str(start + interval_param[interval]) >= SETTLED_SYMBOLS[symbol][0]) and (
                    str(end) <= SETTLED_SYMBOLS[symbol][1]
                ):
                    # 无交易期间的K线不用补全
                    continue
                if SETTLED_SYMBOLS[symbol][0] < str(end) <= SETTLED_SYMBOLS[symbol][1]:
                    end = datetime.datetime.strptime(SETTLED_SYMBOLS[symbol][0][0:10], '%Y-%m-%d') + relativedelta(
                        days=1)
                if SETTLED_SYMBOLS[symbol][0] < str(start) <= SETTLED_SYMBOLS[symbol][1]:
                    start = datetime.datetime.strptime(SETTLED_SYMBOLS[symbol][1][0:10], '%Y-%m-%d') + relativedelta(
                        days=1) - interval_param[interval]
            msg.append(f'\t{start + interval_param[interval]} to {end - interval_param[interval]}')
            if (str(start + interval_param[interval])[-8:] != '00:00:00') or (
                str(end - relativedelta(minutes=1))[-8:] != '23:59:00'
            ):
                print(symbol, f'日内数据不完整，缺失：{start} - {end}')
                if trading_type == 'swap':
                    raise Exception(f'{symbol}日内数据不完整')
                else:
                    # spot 遇到日内缺失的不做处理
                    continue

            while start + interval_param[interval] < end:
                start += relativedelta(days=1)
                miss_day.append(str(start)[0: -9])
        if len(miss_day) != 0:
            print('\n\r', symbol, interval, 'need candles:')
            [print(m) for m in msg]
            print('\tskip days', miss_day)
            err_symbols[symbol] = miss_day
            print('start to download skip zip')

            for day in miss_day:
                local_path = get_local_path(download_folder, trading_type, data_type, 'monthly', symbol, interval)
                sum_name = f'{symbol}-{interval}-{day}.zip.CHECKSUM'
                download_prefix = get_download_prefix(trading_type, data_type, 'daily', symbol, interval)
                tasks.append(download_miss_day_data(symbol, interval, day, local_path, sum_name, download_prefix,
                                                    download_err_info))
    return tasks

def analyse_download_data(download_folder, symbols, trading_type, data_type, intervals):
    err_symbols = dict()
    download_err_info = set()
    if len(need_analyse_set) > 0:
        print('需要分析数据完整性的目录：', need_analyse_set)
    print('开始分析数据完整性...')
    pbar = tqdm.tqdm(total=len(symbols) * len(intervals), ncols=50, mininterval=0.5)
    tasks = []
    for symbol in symbols:
        for interval in intervals:
            tasks.extend(
                build_analyse_download_task(download_folder, symbol, trading_type, data_type, interval, err_symbols,
                                            download_err_info))
            pbar.update(1)
    pbar.close()
    # asyncio.get_event_loop().run_until_complete(asyncio.gather(*tasks))
    get_or_create_eventloop().run_until_complete(asyncio.gather(*tasks))

    if len(err_symbols) > 0:
        print('数据缺失的交易对数量为', len(err_symbols))
        print(err_symbols)

def read_symbol_csv(symbol, zip_path):
    zip_list = glob(os.path.join(zip_path, symbol, f'{symbol}*.zip'))
    # 合并monthly daily 数据
    df = pd.concat(
        Parallel(1)(delayed(pd.read_csv)(path_, header=None, encoding="utf-8", compression='zip',
                                         names=['open_time', 'open', 'high', 'low', 'close', 'volume',
                                                'close_time', 'quote_volume', 'trade_num',
                                                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume',
                                                'ignore']
                                         ) for path_ in zip_list), ignore_index=True)
    # 过滤表头行
    df = df[df['open_time'] != 'open_time']
    # 规范数据类型，防止计算avg_price报错
    df = df.astype(
        dtype={'open_time': np.int64, 'open': np.float64, 'high': np.float64, 'low': np.float64, 'close': np.float64, 'volume': np.float64,
               'quote_volume': np.float64,
               'trade_num': int, 'taker_buy_base_asset_volume': np.float64, 'taker_buy_quote_asset_volume': np.float64})
    df['avg_price'] = df['quote_volume'] / df['volume']  # 增加 均价
    # df['candle_begin_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.drop(columns=['close_time', 'ignore'])
    df = df.sort_values(by='open_time')  # 排序
    df = df.drop_duplicates(subset=['open_time'], keep='last')  # 去除重复值
    df = df.reset_index(drop=True)  # 重置index
    # df = df.set_index('candle_begin_time')
    return df

def data_center_symbol_process(symbol, trading_type, zip_path_1m, zip_path_5m):
    pkl_path = os.path.join(pickle_path, f'{trading_type}', f'{symbol.upper().replace("USDT", "-USDT")}.pkl')
    if not os.path.exists(os.path.join(zip_path_5m, symbol, f'{symbol}-5m-latest.zip')) and os.path.exists(pkl_path):
        # 下架超过2个月的币种，并且之前已经生成过pkl的币种，选择跳过，减少重复工作量
        print('skip pkl', pkl_path)
        df = pd.read_feather(pkl_path, columns=['candle_begin_time', 'symbol', 'avg_price'])
        df['pct_chg'] = df['avg_price'].pct_change(periods=int(hold_hour[:-1]))
        df = df.dropna(subset=['pct_chg'])
        return df[['candle_begin_time', 'symbol', 'pct_chg']]
    df_big = read_symbol_csv(symbol, zip_path_5m)
    # 读取1分钟数据
    df_1m = read_symbol_csv(symbol, zip_path_1m)

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
    # =将数据转换为1小时周期
    df_big['candle_begin_time'] = pd.to_datetime(df_big['open_time'], unit='ms')
    df_big = df_big.set_index('candle_begin_time')
    del df_big['open_time']
    df = df_big.resample(rule='1h').agg(agg_dict)

    # =针对1小时数据，补全空缺的数据。保证整张表没有空余数据
    # 对开、高、收、低、价格进行补全处理
    df['close'] = df['close'].ffill()
    df['open'] = df['open'].fillna(value=df['close'])
    df['high'] = df['high'].fillna(value=df['close'])
    df['low'] = df['low'].fillna(value=df['close'])
    # 将停盘时间的某些列，数据填补为0
    fill_0_list = ['volume', 'quote_volume', 'trade_num', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume']
    df.loc[:, fill_0_list] = df[fill_0_list].fillna(value=0)

    df_1m['candle_begin_time'] = pd.to_datetime(df_1m['open_time'], unit='ms')
    df_1m = df_1m.set_index('candle_begin_time')
    df['avg_price_1m'] = df_1m['avg_price']
    df['avg_price_5m'] = df['avg_price']

    # =计算最终的均价
    # 默认使用1分钟均价
    df['avg_price'] = df['avg_price_1m']
    # 没有1分钟均价就使用5分钟均价
    df['avg_price'] = df['avg_price'].fillna(value=df['avg_price_5m'])
    # 没有5分钟均价就使用开盘价
    df['avg_price'] = df['avg_price'].fillna(value=df['open'])
    del df['avg_price_5m'], df['avg_price_1m']
    df['symbol'] = symbol.upper()
    symbol = symbol.upper().replace('USDT', '-USDT')

    if trading_type == 'swap':
        # 读取fundingRate
        funding_df = pd.read_feather(os.path.join(funding_path, f'{symbol}.pkl'))
        funding_df = funding_df.astype(dtype={'fundingRate': np.float64})
        funding_df['candle_begin_time'] = pd.to_datetime(funding_df['fundingTime'], unit='ms')
        funding_df = funding_df.sort_values(by='candle_begin_time')  # 排序
        funding_df = funding_df.drop_duplicates(subset=['candle_begin_time'], keep='last')  # 去除重复值
        funding_df = funding_df.reset_index(drop=True)  # 重置index
        funding_df = funding_df.set_index('candle_begin_time')
        # 合并fundingRate
        df['fundingRate'] = funding_df['fundingRate']
        df['fundingRate'] = df['fundingRate'].ffill()
        df['funding_rate_raw'] = funding_df['fundingRate']

        funding_df = funding_df.reset_index()  # 重置index
        funding_df['candle_begin_time'] = pd.to_datetime(funding_df['fundingTime'], unit='ms') - datetime.timedelta(hours=1)
        funding_df = funding_df.set_index('candle_begin_time')
        df['funding_rate_r'] = funding_df['fundingRate']
        df['funding_rate_r'] = df['funding_rate_r'].fillna(value=0)

        # 读取 合约持仓量
        ''' # 去掉持仓量数据
        openInterestHist = os.path.join(openInterestHist_path, f'{symbol}.pkl')
        if os.path.exists(openInterestHist):
            openInterestHist_df = pd.read_feather(openInterestHist)
            openInterestHist_df = openInterestHist_df.astype(dtype={'sumOpenInterest': np.float64, 'sumOpenInterestValue': np.float64})
            openInterestHist_df['candle_begin_time'] = pd.to_datetime(openInterestHist_df['timestamp'], unit='ms')
            openInterestHist_df = openInterestHist_df.sort_values(by='candle_begin_time')  # 排序
            openInterestHist_df = openInterestHist_df.drop_duplicates(subset=['candle_begin_time'], keep='last')  # 去除重复值
            openInterestHist_df = openInterestHist_df.reset_index(drop=True)  # 重置index
            openInterestHist_df = openInterestHist_df.set_index('candle_begin_time')
            # 合并 合约持仓量
            df['sumOpenInterest'] = openInterestHist_df['sumOpenInterest'] # 持仓总数量
            df['sumOpenInterestValue'] = openInterestHist_df['sumOpenInterestValue'] # 持仓总价值
        '''

        # 读取 合约主动买卖量
        ''' # 去掉主买主卖数据
        takerlongshortRatio = os.path.join(takerlongshortRatio_path, f'{symbol}.pkl')
        if os.path.exists(takerlongshortRatio):
            takerlongshortRatio_df = pd.read_feather(takerlongshortRatio)
            takerlongshortRatio_df = takerlongshortRatio_df.astype(dtype={'buyVol': np.float64, 'sellVol': np.float64, 'buySellRatio': np.float64})
            takerlongshortRatio_df['candle_begin_time'] = pd.to_datetime(takerlongshortRatio_df['timestamp'], unit='ms')
            takerlongshortRatio_df = takerlongshortRatio_df.sort_values(by='candle_begin_time')  # 排序
            takerlongshortRatio_df = takerlongshortRatio_df.drop_duplicates(subset=['candle_begin_time'], keep='last')  # 去除重复值
            takerlongshortRatio_df = takerlongshortRatio_df.reset_index(drop=True)  # 重置index
            takerlongshortRatio_df = takerlongshortRatio_df.set_index('candle_begin_time')
            # 合并 合约持仓量
            df['buyVol'] = takerlongshortRatio_df['buyVol'] # 主动买入量
            df['sellVol'] = takerlongshortRatio_df['sellVol'] # 主动卖出量
            df['buySellRatio'] = takerlongshortRatio_df['buySellRatio'] # 主买主卖比值
        '''

        # 读取 metrics

    df = df.reset_index()
    if not os.path.exists(os.path.join(pickle_path, f'{trading_type}')):
        os.makedirs(os.path.join(pickle_path, f'{trading_type}'))

    original_symbol = symbol.replace('-USDT', 'USDT')
    if trading_type == 'swap' and original_symbol in SETTLED_SWAP_SYMBOLS:
        df_old = df[df['candle_begin_time'] < SETTLED_SWAP_SYMBOLS[original_symbol][0]].copy()
        old_symbol = symbol.replace('-USDT', '1-USDT')
        df_old.loc[:, 'symbol'] = old_symbol.replace('-', '')
        df_old.to_feather(os.path.join(pickle_path, f'{trading_type}', f'{old_symbol}.pkl'))
        df_new = df[df['candle_begin_time'] > SETTLED_SWAP_SYMBOLS[original_symbol][1]].copy()
        df_new = df_new.reset_index(drop=True)
        df_new.to_feather(os.path.join(pickle_path, f'{trading_type}', f'{symbol}.pkl'))
        print('pkl process success', symbol)
        df_old['pct_chg'] = df_old['avg_price'].pct_change(periods=int(hold_hour[:-1]))
        df_old = df_old.dropna(subset=['pct_chg'])
        df_new.loc[:, 'pct_chg'] = df_new['avg_price'].pct_change(periods=int(hold_hour[:-1]))
        df_new = df_new.dropna(subset=['pct_chg'])
        return pd.concat(
            [df_old[['candle_begin_time', 'symbol', 'pct_chg']], df_new[['candle_begin_time', 'symbol', 'pct_chg']]],
            ignore_index=True)
    df.to_feather(pkl_path)
    print('pkl process success', symbol)
    df['pct_chg'] = df['avg_price'].pct_change(periods=int(hold_hour[:-1]))
    df = df.dropna(subset=['pct_chg'])
    return df[['candle_begin_time', 'symbol', 'pct_chg']]

def data_center_data_to_pickle_data(trading_type, path, _njobs, metrics_symbols):
    monthly_zip_path_1m = get_local_path(path, trading_type, 'klines', 'monthly', None, '1m')
    daily_zip_path_1m = get_local_path(path, trading_type, 'klines', 'daily', None, '1m')
    monthly_zip_path_5m = get_local_path(path, trading_type, 'klines', 'monthly', None, '5m')
    monthly_symbols = os.listdir(monthly_zip_path_1m)
    # 剔除monthly_symbols中的.DS_Store
    exclusion = ['.DS_Store']
    monthly_symbols = [symbol for symbol in monthly_symbols if symbol not in exclusion]
    daily_symbol_set = set(os.listdir(daily_zip_path_1m))

    now = datetime.datetime.now()
    start = now - relativedelta(days=25)
    start_timestamp = int(time.mktime(start.timetuple()) * 1000) + 60000
    newest_timestamp = int(time.mktime(now.timetuple()) * 1000) - 1
    if trading_type == 'swap':
        tasks = []
        print('start download other data')
        start_time = datetime.datetime.strptime('2017-09-17 00:00:00', "%Y-%m-%d %H:%M:%S")
        oldest_timestamp = int(time.mktime(start_time.timetuple())) * 1000
        for symbol in monthly_symbols:
            if symbol in daily_symbol_set:
                tasks.append(get_fundingRate_from_aio_api(symbol, oldest_timestamp, newest_timestamp))
                # tasks.append(get_openInterestHist_from_aio_api(symbol, start_timestamp, newest_timestamp))
                # tasks.append(get_takerlongshortRatio_from_aio_api(symbol, start_timestamp, newest_timestamp))
            else:
                tasks.append(get_fundingRate_from_aio_api(symbol, oldest_timestamp, newest_timestamp, True))
                # tasks.append(get_openInterestHist_from_aio_api(symbol, start_timestamp, newest_timestamp, True))
                # tasks.append(get_takerlongshortRatio_from_aio_api(symbol, start_timestamp, newest_timestamp, True))
        if len(tasks) > 0:
            # asyncio.get_event_loop().run_until_complete(asyncio.gather(*tasks))
            get_or_create_eventloop().run_until_complete(asyncio.gather(*tasks))

    print('进程池大小', _njobs)

    results = []
    # 创建进程池，最多维护_njobs个线程
    threadpool = ProcessPoolExecutor(_njobs)
    for symbol in monthly_symbols:
        # 串行运行
        # data_center_symbol_process(symbol, trading_type, monthly_zip_path_1m, monthly_zip_path_5m)
        # 并发执行
        future = threadpool.submit(data_center_symbol_process, symbol, trading_type, monthly_zip_path_1m,
                                   monthly_zip_path_5m)
        results.append(future)

    dfa = pd.DataFrame()
    for job in as_completed(results):
        dfa = pd.concat([dfa, job.result()], ignore_index=True)
    threadpool.shutdown(True)

    if trading_type == 'spot':
        # 下载现货数据不展示横截面差异指数
        return
    dfa['pct_rank'] = dfa.groupby('candle_begin_time')['pct_chg'].rank(pct=True, ascending=True)
    dfa = dfa.sort_values('candle_begin_time').reset_index(drop=True)

    df_top_5 = dfa[dfa['pct_rank'] >= 0.97].groupby('candle_begin_time')['pct_chg'].mean()
    df_bot_5 = dfa[dfa['pct_rank'] <= 0.03].groupby('candle_begin_time')['pct_chg'].mean()
    df_top_10 = dfa[dfa['pct_rank'] >= 0.92].groupby('candle_begin_time')['pct_chg'].mean()
    df_bot_10 = dfa[dfa['pct_rank'] <= 0.08].groupby('candle_begin_time')['pct_chg'].mean()

    df_diff: pd.Series = (df_top_5 + df_top_10) / 2 - (df_bot_5 + df_bot_10) / 2
    # df_diff: pd.Series = df_top_5 - df_bot_5
    df = pd.DataFrame()
    df['candle_begin_time'] = df_diff.index
    df['cross_diff'] = df_diff.values
    # 头部会有空值要drop，不要填0
    df = df.dropna(subset=['cross_diff'])
    df['cross_diff'] = df['cross_diff'].ewm(span=rolling_period).mean()
    # 去掉头部几行
    df = df[24:].reset_index(drop=True)
    df.to_feather(os.path.join(market_path,f'{trading_type}横截面差异指数.pkl'))
    df = df.set_index('candle_begin_time')
    df.plot(figsize=(16, 9), grid=True)
    # plt.show()
    plt.savefig(os.path.join(path,f'{trading_type}横截面差异指数.pdf'))