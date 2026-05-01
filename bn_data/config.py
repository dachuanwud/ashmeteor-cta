import os
import asyncio
from dateutil.relativedelta import relativedelta

root_path = os.path.dirname(__file__)
market_path = os.path.join(root_path,'output','market')
if not os.path.exists(market_path):
    os.makedirs(market_path)
funding_path = os.path.join(market_path,'funding')
if not os.path.exists(funding_path):
    os.makedirs(funding_path)
pickle_path = os.path.join(root_path,'output','pickle_data')
if not os.path.exists(pickle_path):
    os.makedirs(pickle_path)
cpu = 32  # 服务器CPU核心数，请根据自身条件更改
CONCURRENCY = max(cpu, 1)
semaphore = asyncio.Semaphore(value=min(2 * cpu, 8))
api_semaphore = asyncio.Semaphore(value=min(2 * cpu, 2))
trade_type = 'swap'
proxy = 'socks5h://127.0.0.1:1080'  # VPN配置，一定要改成自己的VPN
# 是否使用代理服务器下载数据
use_proxy_download_file = True
file_proxy = proxy if use_proxy_download_file else None

# 设置网络请求失败（超时）时是否打印异常，True: 不打印，False: 打印，建议老用户设为True
blind = False

# 是否快速更新
thunder = True
retry_times = 10

# 设置是否强制进行完整性分析，False 目录下文件改变才进行，True 强制进行
force_analyse = False

# 全局变量，记录需要完整性分析的目录
need_analyse_set = set()
daily_updated_set = set()

# 当上次更新在合并daily数据时异常中断，将daily_err_occur设为True，平时为False
daily_err_occur = False

# 是否要更新到最近时间，最近时间为运行脚本的前一个整点，具体以脚本打印日志为准
update_to_now = True

rolling_period = 7 * 24

BASE_URL = 'https://data.binance.vision/'
root_center_url = 'https://s3-ap-northeast-1.amazonaws.com/data.binance.vision'

# 结算期的symbol没有交易数据
# SETTLED_SYMBOLS字典保存了结算的开始时间和结束时间
# 若分析数据完整性有新的symbol报错日内数据不完整，需要更新SETTLED_SYMBOLS
SETTLED_SWAP_SYMBOLS = {
    'ICPUSDT': ['2022-06-10 09:00:00', '2022-09-27 02:30:00'],
    # https://www.binance.com/en/support/announcement/binance-futures-will-launch-usd%E2%93%A2-m-icp-perpetual-contracts-with-up-to-25x-leverage-adabdfbc53344094808a7bea464f101b
    #  'MINAUSDT': ['2023-02-06 03:30:00', '2023-02-07 11:00:00'], # https://www.binance.com/en/support/announcement/binance-futures-to-resume-trading-on-usdt-margined-mina-perpetual-contract-611746e5caf848889b132d9fdde6c47f # noqa: E501
    'BNXUSDT': ['2023-02-11 04:00:00', '2023-02-22 22:45:00'],
    # https://www.binance.com/en/support/announcement/binance-futures-to-relaunch-usd%E2%93%A2-m-bnx-perpetual-contracts-with-up-to-20x-leverage-940d0e48493e4627889c3f46371df70b
    'TLMUSDT': ['2022-06-09 23:59:00', '2023-03-30 12:30:00']
}
SETTLED_SPOT_SYMBOLS = {
}

swap_delist_symbol_set = {'1000BTTCUSDT', 'CVCUSDT', 'DODOUSDT', 'RAYUSDT', 'SCUSDT', 'SRMUSDT', 'LENDUSDT', 'NUUSDT',
                          'LUNAUSDT', 'YFIIUSDT', 'BTCSTUSDT'}

if trade_type == 'swap':
    # 警告：此处不能改动
    prefix = 'data/futures/um/daily/klines/'
    metrics_prefix = 'data/futures/um/daily/metrics/'
    SETTLED_SYMBOLS = SETTLED_SWAP_SYMBOLS
else:
    # 警告：此处不能改动
    prefix = 'data/spot/daily/klines/'
    SETTLED_SYMBOLS = SETTLED_SPOT_SYMBOLS

interval_microsecond = {
    '1m': 60000,
    '5m': 300000
}

interval_param = {
    '1m': relativedelta(minutes=1),
    '5m': relativedelta(minutes=5)
}