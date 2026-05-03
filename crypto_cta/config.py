import os
import pandas as pd

root_path = os.path.dirname(os.path.abspath(__file__))

data_path = os.path.join(root_path,f'data/pickle_data')
if os.path.exists(data_path) == False:
    os.makedirs(data_path)

# k线数据路径
data_center_path = '/Users/houjl/Downloads/CTA回测/bn_data/output/market/swap_1m'
time_interval = '1m'    # k线数据周期

# 回测配置
# symbol_list = ['RARE-USDT','SUI-USDT','BNX-USDT','MEME-USDT','TURBO-USDT','DOGE-USDT','PEOPLE-USDT','1000SHIB-USDT','1000RATS-USDT','1000SATS-USDT','1000BONK-USDT','MEW-USDT','WIF-USDT','1000PEPE-USDT'] # 指定币种池
symbol_list = ['ETH-USDT']
para = [200, 20]  # 策略参数
proportion = 0.05  # 止盈止损比例
# signal_name_list = ['rsinmapctv1','rsinmapctv2','rsinmapctv3','rsinma_2parapct']
signal_name_list = ['adapt_bolling_anti_chase']  # 策略名
rule_type_list = ['4H']
date_start = '2021-01-01'  # 回测开始时间
date_end = '2026-05-02 04:59:59'  # 回测结束时间
offset = 1
c_rate = 8 / 10000  # 手续费，commission fees，默认为万分之5。不同市场手续费的收取方法不同，对结果有影响。比如和股票就不一样。
slippage = 1 / 1000  # 滑点 ，可以用百分比，也可以用固定值。建议币圈用百分比，股票用固定值
leverage_rate = 1  # 杠杆倍数
min_margin_ratio = 1 / 100  # 最低保证金率，低于就会爆仓
drop_days = 10  # 币种刚刚上线10天内不交易

# 是否分区间遍历
per_eva = 'a'       # y表示按年分区间遍历，m表示按月分区间遍历，w表示按周分区间遍历, a表示全部遍历
# 统一入口 run_configured.py 执行的任务：backtest=单次回测，sweep=参数遍历，plot=参数平原/热力图
run_task_list = ['backtest', 'visualize']
# 是否在生成策略可视化图后自动打开浏览器
visualize_show = False
# 删除模式
del_mode = True
# 是否绘制参数覆盖总资金曲线
cover_curve = False

# 最小下单量
min_amount_df = pd.read_csv(os.path.join(root_path, '最小下单量.csv'), encoding='gbk')
min_amount_dict = {}
for i in min_amount_df.index:
    min_amount_dict[min_amount_df.at[i, '合约']] = min_amount_df.at[i, '最小下单量']

head_column = ['candle_begin_time', 'open', 'high', 'low', 'close', 'volume', 'quote_volume', 'trade_num', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'offset', 'kline_pct']
