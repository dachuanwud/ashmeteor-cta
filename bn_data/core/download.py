import datetime
import os
import tqdm
import asyncio
import aiohttp
import aiofiles
from dateutil.relativedelta import relativedelta
from glob import glob
from hashlib import sha256
from core.bnapi import get_klines_from_aio_api
from core.common import get_or_create_eventloop
from config import thunder, BASE_URL, semaphore, retry_times, file_proxy, blind, need_analyse_set, daily_updated_set



def clean_old_daily_zip(local_daily_path, symbols, interval):
    today = datetime.date.today()
    this_month_first_day = datetime.date(today.year, today.month, 1)
    daily_end = this_month_first_day - relativedelta(months=1)

    for symbol in symbols:
        local_daily_symbol_path = os.path.join(local_daily_path, symbol)
        if os.path.exists(local_daily_symbol_path):
            zip_file_path = os.path.join(local_daily_symbol_path, "{}-{}-{}.zip".format(symbol.upper(), interval, daily_end))
            for item in glob(os.path.join(local_daily_symbol_path, '*')):
                if item < zip_file_path:
                    os.remove(item)
            if not os.listdir(local_daily_symbol_path):
                # 删除空文件夹，即已下架的币种
                os.rmdir(local_daily_symbol_path)

async def download(local_path, download_checksum_url, local_sum_path, local_zip_path, pbar, error_info_list):
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        async with semaphore:
            retry = 0
            while True:
                if retry > retry_times and 'daily_klines' in local_path:
                    print('下载daily zip失败次数超过retry_times，当前网络状况不稳定或数据包异常', local_zip_path)
                    break
                try:
                    sum_file = await session.get(download_checksum_url, proxy=file_proxy, timeout=20)
                    sum_file_buffer = await sum_file.read()
                    async with aiofiles.open(local_sum_path, 'wb') as out_sum_file:
                        await out_sum_file.write(sum_file_buffer)

                    zip_file = await session.get(download_checksum_url[0:-9], proxy=file_proxy, timeout=20)
                    zip_file_buffer = await zip_file.read()
                    async with aiofiles.open(local_zip_path, 'wb') as out_zip_file:
                        await out_zip_file.write(zip_file_buffer)

                    async with aiofiles.open(local_sum_path, encoding='utf-8') as in_sum_file:
                        str_sum = await in_sum_file.read()
                        correct_sum = str_sum.split(' ')[0]
                    sha256_obj = sha256()
                    async with aiofiles.open(local_zip_path, 'rb') as in_zip_file:
                        sha256_obj.update(await in_zip_file.read())
                    if correct_sum == sha256_obj.hexdigest().lower():
                        # print(local_zip_path, 'is correct')
                        pbar.update(1)
                        break
                except aiohttp.ClientError as ae:
                    if not blind:
                        print(f'\n\r下载{local_zip_path}失败，继续重试', ae)
                    error_info_list.add(f'下载{local_zip_path}失败，错误原因{ae}，已重试下载，请确认')
                except Exception as e:
                    error_info_list.add(f'下载{local_zip_path}失败，错误类型{type(e)}，已重试下载，请确认')
                retry += 1

def download_file(params, pbar, error_info_list):
    tasks = []
    for param in params:
        key = param['key']
        download_checksum_url = f'{BASE_URL}{key}'
        sum_file_name = os.path.basename(param['key'])

        if not os.path.exists(param['local_path']):
            os.makedirs(param['local_path'])
        local_path = param['local_path']
        last_modified = param['last_modified']
        local_sum_path = os.path.join(local_path, sum_file_name)
        local_zip_path = os.path.join(local_path, sum_file_name[0:-9])
        if os.path.exists(local_sum_path):
            '''
            这里对checksum文件的更新时间与币安数据中心的更新时间作比较
            '''
            modify_utc_timestamp = datetime.datetime.utcfromtimestamp(os.path.getmtime(local_sum_path)).timestamp()
            if modify_utc_timestamp < last_modified:
                os.remove(local_sum_path)
        if os.path.exists(local_sum_path) and os.path.exists(local_zip_path):
            if not thunder:
                # 本地已有文件，进行校验
                with open(local_sum_path, encoding='utf-8') as in_sum_file:
                    correct_sum = in_sum_file.readline().split(' ')[0]
                sha256Obj = sha256()
                with open(local_zip_path, 'rb') as in_zip_file:
                    sha256Obj.update(in_zip_file.read())
                if correct_sum == sha256Obj.hexdigest().lower():
                    # print(local_zip_path, 'existed and is correct')
                    pbar.update(1)
                    continue  # 继续下一个zip的下载过程
            else:
                # 快速更新模式不校验本地已有文件
                pbar.update(1)
                continue  # 继续下一个zip的下载过程
        if 'monthly' in local_path:
            # 需要数据完整性分析的目录
            need_analyse_set.add(local_path)
        if 'daily_klines' in local_path:
            daily_updated_set.add(local_path)
        tasks.append(
            download(param['local_path'], download_checksum_url, local_sum_path, local_zip_path, pbar, error_info_list))
    return tasks

def async_download_file(all_list, error_info_list):
    pbar = tqdm.tqdm(total=len(all_list), ncols=50, mininterval=0.5)
    tasks = download_file(all_list, pbar, error_info_list)
    # asyncio.get_event_loop().run_until_complete(asyncio.gather(*tasks))
    get_or_create_eventloop().run_until_complete(asyncio.gather(*tasks))
    pbar.close()

async def download_miss_day_data(symbol, interval, day, local_path, sum_name, prefix, download_err_info):
    local_sum_path = os.path.join(local_path, sum_name)
    sum_url = BASE_URL + prefix + sum_name
    local_zip_path = local_sum_path[0:-9]
    err_times = 0
    retry_sum_404 = 0
    retry_zip_404 = 0
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        async with semaphore:
            while True:
                try:
                    sum_file = await session.get(sum_url, proxy=file_proxy, timeout=20)
                    if sum_file.status == 200:
                        sum_file_buffer = await sum_file.read()
                        async with aiofiles.open(local_sum_path, 'wb') as out_sum_file:
                            await out_sum_file.write(sum_file_buffer)
                    else:
                        retry_sum_404 += 1
                        if retry_sum_404 > 3:
                            # 重试3次确认不存在这个文件
                            break
                        else:
                            continue
                    zip_file = await session.get(sum_url[0:-9], proxy=file_proxy, timeout=20)
                    if zip_file.status == 200:
                        zip_file_buffer = await zip_file.read()
                        async with aiofiles.open(local_zip_path, 'wb') as out_zip_file:
                            await out_zip_file.write(zip_file_buffer)
                    else:
                        retry_zip_404 += 1
                        if retry_zip_404 > 3:
                            # 重试3次确认不存在这个文件
                            break
                        else:
                            continue

                    async with aiofiles.open(local_sum_path, encoding='utf-8') as in_sum_file:
                        str_sum = await in_sum_file.readline()
                        correct_sum = str_sum.split(' ')[0]
                    sha256_obj = sha256()
                    async with aiofiles.open(local_zip_path, 'rb') as in_zip_file:
                        sha256_obj.update(await in_zip_file.read())
                    if correct_sum == sha256_obj.hexdigest().lower():
                        # print(local_zip_path, 'is correct')
                        break
                except aiohttp.ClientError as ae:
                    if not blind:
                        print(f'下载{local_zip_path}失败，继续重试', ae)
                    download_err_info.add(f'下载{local_zip_path}失败，错误原因{ae}，已重试下载，请确认')
                    err_times += 1
                    if err_times > 5:
                        print('补漏下载重试超过5次')
                        raise ae
                except Exception as e:
                    print(f'下载{local_zip_path}失败，错误类型{type(e)}，已重试下载，请确认')
                    download_err_info.add(f'下载{local_zip_path}失败，错误类型{type(e)}，已重试下载，请确认')
                    err_times += 1
                    if err_times > 5:
                        print('补漏下载重试超过5次')
                        raise e
    if retry_sum_404 > 3 or retry_zip_404 > 3:
        print(f'{sum_name} not exist, request from api')
        format_day = datetime.datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
        start = int(format_day.timestamp()) * 1000
        end = int((format_day + datetime.timedelta(days=1)).timestamp()) * 1000 - 1
        await get_klines_from_aio_api(symbol, interval, start, end, local_zip_path)

