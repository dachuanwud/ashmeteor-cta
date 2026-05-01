import datetime
import asyncio
import os
import random
import time
from core.symbols import async_get_usdt_symbols, spot_symbols_filter
from core.common import ping, get_local_path, get_or_create_eventloop
from core.links import async_get_daily_list, async_get_monthly_list
from core.download import clean_old_daily_zip, async_download_file
from core.postprocess import transfer_daily_to_monthly_and_get_newest, analyse_download_data, data_center_data_to_pickle_data
from config import *


def run():
    print(f'CPU核心数: {cpu}')
    start_time = datetime.datetime.now()
    params = {
        'delimiter': '/',
        'prefix': prefix
    }
    symbols = async_get_usdt_symbols(params)
    if trade_type == 'spot':
        symbols = spot_symbols_filter(symbols)
    print('usdt交易对数量', len(symbols))
    get_or_create_eventloop().run_until_complete(ping(trade_type))

    metrics_daily_list = []
    metrics_symbols = []
    # 几何数据接口

    print('开始获取数据目录')

    daily_list_1m = async_get_daily_list(market_path, symbols, trade_type, 'klines', '1m')
    daily_list_5m = async_get_daily_list(market_path, symbols, trade_type, 'klines', '5m')
    print('daily zip num in latest 2 months =', len(daily_list_1m) + len(daily_list_5m))

    monthly_list_1m = async_get_monthly_list(market_path, symbols, trade_type, 'klines', '1m')
    monthly_list_5m = async_get_monthly_list(market_path, symbols, trade_type, 'klines', '5m')
    print('monthly zip num =', len(monthly_list_1m) + len(monthly_list_5m))

    all_list = daily_list_1m + monthly_list_1m + metrics_daily_list + daily_list_5m + monthly_list_5m
    random.shuffle(all_list)  # 打乱monthly和daily的顺序，合理利用网络带宽

    get_time = datetime.datetime.now()
    print('所有数据包个数为', len(all_list), "获取目录耗费 {} s".format((get_time - start_time).seconds))

    print('开始清理daily旧数据...')
    clean_old_daily_zip(get_local_path(market_path, trade_type, 'klines', 'daily', None, '1m'), symbols, '1m')
    clean_old_daily_zip(get_local_path(market_path, trade_type, 'klines', 'daily', None, '5m'), symbols, '5m')
    print('清理完成')

    print('start download:')
    error_info_list = set()
    async_download_file(all_list, error_info_list)
    print('need analyse', need_analyse_set)
    if len(error_info_list) > 0:
        print('下载过程发生错误，已完成重试下载，请核实')
        print(error_info_list)
    end_time = datetime.datetime.now()
    print(f'download end cost {(end_time - get_time).seconds} s = {(end_time - get_time).seconds / 60} min')
    print('开始将daily数据合并为monthly数据...')
    # 获取当前时间
    end_time = datetime.datetime.now()
    if end_time.minute < 5:
        # 截止时间，若当前时间离整点没过5分钟则取上个整点，容错处理，防止K线未闭合，15点04分 end_time取14点整
        end_time -= datetime.timedelta(hours=1)
    end_time = end_time.replace(minute=0, second=0, microsecond=0)
    print('最新数据正在更新至', end_time - datetime.timedelta(seconds=1))
    global newest_timestamp
    # 将时间转换为时间戳
    newest_timestamp = int(time.mktime(end_time.timetuple()) * 1000) - 1
    tasks = transfer_daily_to_monthly_and_get_newest(newest_timestamp, daily_list_1m + daily_list_5m, need_analyse_set)
    if len(tasks) > 0:
        get_or_create_eventloop().run_until_complete(asyncio.gather(*tasks))

    if force_analyse or len(need_analyse_set) > 0:
        analyse_download_data(market_path, symbols, trade_type, 'klines', ['1m', '5m'])

    print('开始生成中性PKL数据...')
    data_center_data_to_pickle_data(trade_type, market_path, CONCURRENCY, metrics_symbols)
    print(f'结束运行，总耗时{(datetime.datetime.now() - start_time).seconds / 60}min')


if __name__ == '__main__':
    run()