import aiohttp
import asyncio
import os
from config import proxy,thunder,root_center_url
import sys


async def ping(trade_type):
    """
    对币安api进行联通测试
    """
    if trade_type == 'spot':
        url = 'https://api.binance.com/api/v1/ping'
    else:
        url = 'https://fapi.binance.com/fapi/v1/ping'
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url=url, proxy=proxy, timeout=5) as response:
                t = await response.text()
                if t == '{}':
                    print('币安接口已连通')
                else:
                    print('币安接口连接异常，请检查网络配置后重新运行')
                    exit(0)
        except Exception as e:
            print('币安接口无法连接，请检查网络配置后重新运行', e)
            exit(0)

async def request_session(session, params):
    while True:
        if not thunder:
            await asyncio.sleep(0.2)
        try:
            async with session.get(root_center_url, params=params, proxy=proxy, timeout=20) as response:
                return await response.text()
        except aiohttp.ClientError as ae:
            print('请求失败，继续重试', ae)
        except Exception as e:
            print('请求失败，继续重试', e)

def get_download_prefix(trading_type, market_data_type, time_period, symbol, interval):
    trading_type_path = 'data/spot'
    if trading_type == 'swap':
        trading_type_path = 'data/futures/um'
    return f'{trading_type_path}/{time_period}/{market_data_type}/{symbol.upper()}/{interval}/'

def get_local_path(root_path, trading_type, market_data_type, time_period, symbol, interval='5m'):
    trade_type_folder = trading_type + '_' + interval
    path = os.path.join(root_path, trade_type_folder, f'{time_period}_{market_data_type}')

    if symbol:
        path = os.path.join(path, symbol.upper())
    return path

def get_or_create_eventloop():
    try:
        loop = asyncio.get_event_loop()
        if sys.platform == 'win32':
            # Windows系统下使用SelectorEventLoop
            if not isinstance(loop, asyncio.SelectorEventLoop):
                loop = asyncio.SelectorEventLoop()
                asyncio.set_event_loop(loop)
        return loop
    except RuntimeError as ex:
        if "There is no current event loop in thread" in str(ex):
            if sys.platform == 'win32':
                # Windows系统下使用SelectorEventLoop
                loop = asyncio.SelectorEventLoop()
            else:
                loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return asyncio.get_event_loop()
        else:
            raise ex