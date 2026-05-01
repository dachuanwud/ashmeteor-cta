import aiohttp
import asyncio
from lxml import objectify
from core.common import request_session, get_or_create_eventloop
import sys


async def get_symbols_by_session(session, params):
    data = await request_session(session, params)
    root = objectify.fromstring(data.encode('ascii'))
    result = []
    for item in root.CommonPrefixes:
        param = item.Prefix
        s = param.text.split('/')
        result.append(s[len(s) - 2])
    if root.IsTruncated:
        # 下一页的网址
        params['marker'] = root.NextMarker.text
        next = await get_symbols_by_session(session, params)
        result.extend(next)  # 初次循环时，link_lst 包含1000条以上的数据
    return result

async def get_symbols(params):
    connector = aiohttp.TCPConnector(
        ssl=False,
        use_dns_cache=False,  # 禁用DNS缓存
        ttl_dns_cache=0  # DNS缓存时间设为0
    )
    async with aiohttp.ClientSession(connector=connector) as session:
        result = await get_symbols_by_session(session, params)
        return result

def async_get_all_symbols(params):
    if sys.platform == 'win32':
        # Windows系统下使用SelectorEventLoop
        loop = get_or_create_eventloop()
        return loop.run_until_complete(get_symbols(params))
    return asyncio.run(get_symbols(params))

def async_get_usdt_symbols(params):
    all_symbols = async_get_all_symbols(params)
    usdt = set()
    [usdt.add(i) for i in all_symbols if i.endswith('USDT')]
    return usdt

def spot_symbols_filter(symbols):
    others = []
    stable_symbol = ['BKRW', 'USDC', 'USDP', 'TUSD', 'BUSD', 'FDUSD', 'DAI', 'EUR', 'GBP']
    # stable_symbols：稳定币交易对
    stable_symbols = [s + 'USDT' for s in stable_symbol]
    # special_symbols：容易误判的特殊交易对
    special_symbols = ['JUPUSDT']
    pure_spot_symbols = []
    for symbol in symbols:
        if symbol in special_symbols:
            pure_spot_symbols.append(symbol)
            continue
        if symbol.endswith('UPUSDT') or symbol.endswith('DOWNUSDT') or symbol.endswith('BULLUSDT') or symbol.endswith(
            'BEARUSDT'
        ):
            others.append(symbol)
            continue
        if symbol in stable_symbols:
            others.append(symbol)
            continue
        pure_spot_symbols.append(symbol)
    print('过滤掉的现货symbol', others)
    return pure_spot_symbols