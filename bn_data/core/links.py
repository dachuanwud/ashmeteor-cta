import aiohttp
import asyncio
from lxml import objectify
import datetime
import time
from dateutil.relativedelta import relativedelta
from core.common import get_download_prefix,request_session,get_local_path,get_or_create_eventloop

async def download_daily_list(download_folder, symbols, trading_type, data_type, interval):
    today = datetime.date.today()
    this_month_first_day = datetime.date(today.year, today.month, 1)
    daily_end = this_month_first_day - relativedelta(months=1)

    result = []
    param_list = []
    for symbol in symbols:
        daily_prefix = get_download_prefix(trading_type, data_type, 'daily', symbol, interval)
        checksum_file_name = "{}-{}-{}.zip.CHECKSUM".format(symbol.upper(), interval, daily_end - relativedelta(days=1))
        first_checksum_file_uri = '{}{}'.format(daily_prefix, checksum_file_name)
        param = {
            'delimiter': '/',
            'prefix': daily_prefix,
            'marker': first_checksum_file_uri
        }
        param_list.append(param)
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        tasks = [asyncio.create_task(request_session(session, p)) for p in param_list]
        await asyncio.wait(tasks)

    for task in tasks:
        data = task.result()

        root = objectify.fromstring(data.encode('ascii'))
        if getattr(root, 'Contents', None) is None:
            continue
        symbol = root.Prefix.text.split('/')[-3]
        local_path = get_local_path(download_folder, trading_type, data_type, 'daily', symbol, interval)
        for item in root.Contents:
            key = item.Key.text
            if key.endswith('CHECKSUM'):
                struct_time = time.strptime(item.LastModified.text, '%Y-%m-%dT%H:%M:%S.%fZ')
                _tmp = {
                    'key': key,
                    'last_modified': time.mktime(struct_time),
                    'local_path': local_path,
                    'interval': interval
                }
                result.append(_tmp)
    return result

def async_get_daily_list(download_folder, symbols, trading_type, data_type, interval):
    loop = get_or_create_eventloop()
    return loop.run_until_complete(download_daily_list(download_folder, symbols, trading_type, data_type, interval))

async def build_download_monthly_list(download_folder, symbols, trading_type, data_type, interval):
    today = datetime.date.today()
    this_month_first_day = datetime.date(today.year, today.month, 1)
    daily_end = this_month_first_day - relativedelta(months=2)
    end_month = str(daily_end)[0:-3]

    param_list = []
    for symbol in symbols:
        monthly_prefix = get_download_prefix(trading_type, data_type, 'monthly', symbol, interval)
        param = {
            'delimiter': '/',
            'prefix': monthly_prefix
        }
        param_list.append(param)

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        tasks = [asyncio.create_task(request_session(session, p)) for p in param_list]
        await asyncio.wait(tasks)

    result = []
    for task in tasks:
        data = task.result()

        root = objectify.fromstring(data.encode('ascii'))
        if getattr(root, 'Contents', None) is None:
            continue
        symbol = root.Prefix.text.split('/')[-3]
        local_path = get_local_path(download_folder, trading_type, data_type, 'monthly', symbol, interval)
        for item in root.Contents:
            key = item.Key.text
            if key.endswith('CHECKSUM') and (key[-20:-13] <= end_month):
                struct_time = time.strptime(item.LastModified.text, '%Y-%m-%dT%H:%M:%S.%fZ')
                _tmp = {
                    'key': key,
                    'last_modified': time.mktime(struct_time),
                    'local_path': local_path
                }
                result.append(_tmp)
    return result

def async_get_monthly_list(download_folder, symbols, trading_type, data_type, interval):
    # loop = asyncio.get_event_loop()
    loop = get_or_create_eventloop()
    return loop.run_until_complete(build_download_monthly_list(download_folder, symbols, trading_type, data_type, interval))