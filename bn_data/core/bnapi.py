import os
import pandas as pd
import aiohttp
import asyncio
import json
from config import *


async def get_klines_from_aio_api(symbol, interval, start_time, end_time, zip_path, overwrite=False):
    df = pd.DataFrame()
    if not overwrite and os.path.exists(zip_path):
        try:
            df = pd.read_csv(zip_path, header=None, encoding="utf-8", compression='zip')
            df.sort_values(by=0)
            df = df[df.iloc[:, 0] > start_time]
            if df.shape[0] > 0:
                latest_time = int(df.iloc[-1, 0])
                if latest_time + interval_microsecond[interval] == end_time + 1:
                    # 无需更新
                    return
                if latest_time > start_time:
                    start_time = latest_time
        except Exception as e:
            print(zip_path, '读取失败，请根据报错酌情处理，若文件损坏可删除该文件重新运行')
            raise e

    if trade_type == 'spot':
        spot_kline_url = 'https://api.binance.com/api/v3/klines'
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            async with api_semaphore:
                while start_time < end_time:
                    end = int(start_time) + 999 * interval_microsecond[interval]
                    if end > end_time:
                        end = end_time
                    param = {
                        'symbol': symbol,
                        'interval': interval,
                        'startTime': int(start_time),
                        'endTime': end,
                        'limit': 1000
                    }
                    while True:
                        try:
                            async with session.get(url=spot_kline_url, params=param, proxy=proxy,
                                                   timeout=5) as kline_response:
                                kline = await kline_response.text()
                                _df = pd.DataFrame(json.loads(kline))
                                df = pd.concat([df, _df], ignore_index=True)
                                break
                        except Exception as e:
                            if not blind:
                                print('spot klines请求失败，继续重试', e)
                            continue
                    start_time = end
                if df.shape[0] > 0:
                    compression_options = dict(method='zip', archive_name=f'{symbol}-{interval}-newest.csv')
                    df.to_csv(zip_path, header=None, index=None, compression=compression_options)
    elif trade_type == 'swap':
        if symbol in swap_delist_symbol_set:
            print(f'{symbol}已下架，无法获取数据')
            return
        swap_kline_url = 'https://fapi.binance.com/fapi/v1/klines'
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            async with api_semaphore:
                while start_time < end_time:
                    end = int(start_time) + 499 * interval_microsecond[interval]
                    if end > end_time:
                        end = end_time
                    param = {
                        'symbol': symbol,
                        'interval': interval,
                        'startTime': int(start_time),
                        'endTime': end,
                        'limit': 499
                    }
                    while True:
                        response_str = ''
                        try:
                            async with session.get(url=swap_kline_url, params=param, proxy=proxy,
                                                   timeout=5) as kline_response:
                                response_str = kline = await kline_response.text()
                                _df = pd.DataFrame(json.loads(kline))
                                df = pd.concat([df, _df], ignore_index=True)
                                break
                        except Exception as e:
                            if not blind:
                                print(f'swap klines请求失败 symbol {symbol}，返回结果：{response_str}，继续重试', e)
                            continue
                    start_time = end
                if df.shape[0] > 0:
                    compression_options = dict(method='zip', archive_name=f'{symbol}-{interval}-newest.csv')
                    df.to_csv(zip_path, header=None, index=None, compression=compression_options)

async def get_fundingRate_from_aio_api(symbol, start_time, end_time, delist=False):
    df = pd.DataFrame()
    funding_pkl_name = symbol.upper().replace('USDT', '-USDT')
    if not os.path.exists(funding_path):
        os.makedirs(funding_path)
    funding = os.path.join(funding_path, f'{funding_pkl_name}.pkl')
    if os.path.exists(funding):
        if delist:
            # 已下架币种若已存在fundingRate文件，直接返回
            return

        try:
            df = pd.read_feather(funding)
            df.sort_values(by='fundingTime')
            if df.shape[0] > 0:
                latest_time = int(df.iloc[-1, 0]) + 1
                if latest_time > start_time:
                    start_time = latest_time
        except Exception as e:
            print(funding, 'error')
            raise e

    funding_url = 'https://fapi.binance.com/fapi/v1/fundingRate'
    updated = False
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        while True:
            async with api_semaphore:
                await asyncio.sleep(1)
                param = {
                    'symbol': symbol,
                    'startTime': start_time,
                    'endTime': end_time,
                    'limit': 1000
                }
                try:
                    async with session.get(url=funding_url, params=param, proxy=proxy, timeout=5) as kline_response:
                        f_data = await kline_response.text()
                        if kline_response.status == 200:
                            _df = pd.DataFrame(json.loads(f_data), columns=['fundingTime', 'fundingRate'], index=None)
                            if _df.shape[0] == 0:
                                break
                            _df.sort_values(by='fundingTime', inplace=True)
                            start_time = int(_df.iloc[-1, 0]) + 1
                            _df['fundingTime'] = (_df['fundingTime'] // 1000) * 1000
                            df = pd.concat([df, _df], ignore_index=True)
                            updated = True

                            if _df.shape[0] < 1000:
                                break
                        else:
                            print(f'fundingRate {symbol} error response {f_data}')
                except Exception as e:
                    if not blind:
                        print('swap fundingRate请求失败，小问题不要慌，马上重试', e)
                    continue
        if updated:
            df.to_feather(funding)