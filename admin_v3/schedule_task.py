from flask_apscheduler import APScheduler
from config import sql_uri, fapi_path, dapi_path, alpha_path, blacklist_hours, takeprofit_drawdown_percentage, cta_tpsl_time
from decimal import Decimal
from factors import adapt_bolling
from functions import *
from sqlalchemy import create_engine
from datetime import datetime
import pandas as pd
import numpy as np
import factors
import time
import os
from model import CtaUsdt
import config

scheduler = APScheduler()

base_bnb_dict = {}


def account_net_value(*args):
    engine = create_engine(sql_uri)
    all_usd_in = 0
    all_usd_out = 0
    all_account_margin_balance = 0
    for binance in args:
        exchange = binance['exchange']
        strategy = binance['strategy']
        log_print(f'{strategy} start')
        # 获取该账户过去10分钟的转入转出数据
        usd_in, usd_out = get_transfer_info(exchange)
        all_usd_in += usd_in
        all_usd_out += usd_out
        # 获取账户当前的净值
        account_info = exchange.fapiPrivateV2_get_account()
        totalMarginBalance = float(account_info['totalMarginBalance'])
        all_account_margin_balance += totalMarginBalance

        sql = f'select * from {strategy}_value'
        try:
            df = pd.read_sql(sql, con=engine, index_col='index')
        except:
            df = pd.DataFrame()

        df = df.append(
            {
                'candle_begin_time':
                datetime.now().replace(second=0, microsecond=0),
                'net_value':
                float(totalMarginBalance),
                'usd_in':
                float(usd_in),
                'usd_out':
                float(usd_out),
                'init_value':
                0.0,
                'accumulate_value':
                1.0,
                'pct_change':
                1.0
            },
            ignore_index=True)
        if len(df) <= 1:
            df.iloc[0, df.columns.get_loc('init_value')] = totalMarginBalance
        else:
            df.iloc[-1, df.columns.get_loc('init_value')] = df.iloc[-2][
                'net_value'] + df.iloc[-1]['usd_in'] - df.iloc[-1]['usd_out']

            df.iloc[-1, df.columns.get_loc(
                'pct_change')] = df.iloc[-1]['net_value'] / df.iloc[-1][
                    'init_value'] if df.iloc[-1]['init_value'] > 0 else 1
            df.iloc[-1, df.columns.get_loc('accumulate_value')] = df.iloc[-2][
                'accumulate_value'] * df.iloc[-1]['pct_change']
        df = df[-1:]
        df.to_sql(name=f'{strategy}_value',
                  con=engine,
                  if_exists='append',
                  index=True)

    # 主账户合并
    sql = f'select * from all_account_value'
    try:
        df = pd.read_sql(sql, con=engine, index_col='index')
    except:
        df = pd.DataFrame()

    df = df.append(
        {
            'candle_begin_time': datetime.now().replace(second=0,
                                                        microsecond=0),
            'net_value': float(all_account_margin_balance),
            'usd_in': float(all_usd_in),
            'usd_out': float(all_usd_out),
            'init_value': 0.0,
            'accumulate_value': 1.0,
            'pct_change': 1.0
        },
        ignore_index=True)
    if len(df) <= 1:
        df.iloc[0,
                df.columns.get_loc('init_value')] = all_account_margin_balance
    else:
        df.iloc[-1, df.columns.get_loc('init_value')] = df.iloc[-2][
            'net_value'] + df.iloc[-1]['usd_in'] - df.iloc[-1]['usd_out']

        df.iloc[-1, df.columns.
                get_loc('pct_change')] = df.iloc[-1]['net_value'] / df.iloc[
                    -1]['init_value'] if df.iloc[-1]['init_value'] > 0 else 1
        df.iloc[-1, df.columns.get_loc('accumulate_value')] = df.iloc[-2][
            'accumulate_value'] * df.iloc[-1]['pct_change']
    df = df[-1:]
    df.to_sql(name=f'all_account_value',
              con=engine,
              if_exists='append',
              index=True)


def total_account_net_value(*args):
    engine = create_engine(sql_uri)
    binance_list = args[0]
    all_usd_in = 0
    all_usd_out = 0
    account_total = 0
    for binance in binance_list:
        exchange = binance['exchange']
        strategy = binance['strategy']
        log_print(f'total binance account: {strategy} start')
        # 获取该账户过去10分钟的转入转出数据
        usd_in, usd_out = get_deposit_withdraw_info(binance)
        all_usd_in += usd_in
        all_usd_out += usd_out

    total_account_value = get_account_management_balance(binance_list)
    for account_info in total_account_value['data']['items']:
        if account_info['strategy_name'] == '账户汇总':
            account_total = account_info['account_total']
            break
        else:
            continue

    # 主账户合并
    sql = f'select * from total_binance_account_value'
    try:
        df = pd.read_sql(sql, con=engine, index_col='index')
    except:
        df = pd.DataFrame()

    df = df.append(
        {
            'candle_begin_time': datetime.now(),
            'net_value': float(account_total),
            'usd_in': float(all_usd_in),
            'usd_out': float(all_usd_out),
            'init_value': 0.0,
            'accumulate_value': 1.0,
            'pct_change': 1.0
        },
        ignore_index=True)
    if len(df) <= 1:
        df.iloc[0, df.columns.get_loc('init_value')] = account_total
    else:
        df.iloc[-1, df.columns.get_loc('init_value')] = df.iloc[-2][
            'net_value'] + df.iloc[-1]['usd_in'] - df.iloc[-1]['usd_out']

        df.iloc[-1, df.columns.
                get_loc('pct_change')] = df.iloc[-1]['net_value'] / df.iloc[
                    -1]['init_value'] if df.iloc[-1]['init_value'] > 0 else 1
        df.iloc[-1, df.columns.get_loc('accumulate_value')] = df.iloc[-2][
            'accumulate_value'] * df.iloc[-1]['pct_change']
    df = df[-1:]
    df.to_sql(name=f'total_binance_account_value',
              con=engine,
              if_exists='append',
              index=True)


def dapi_account_net_value(*args):
    engine = create_engine(sql_uri)
    all_usd_in = 0
    all_usd_out = 0
    all_account_margin_balance = 0

    for binance in args:
        exchange = binance['exchange']
        strategy = binance['strategy']
        log_print(f'dapi {strategy} start')

        # 获取该账户过去10分钟的转入转出数据
        usd_in, usd_out = get_dapi_transfer_info(exchange)
        all_usd_in += usd_in
        all_usd_out += usd_out
        items = get_dapi_account_balance(
            exchange,
            binance.get('account_type', ACCOUNT_TYPE_STANDARD))['data']['items']
        margin_balance_usd = 0
        for i in items:
            margin_balance_usd += i['margin_balance_usd']
        if margin_balance_usd == 0:
            continue
        all_account_margin_balance += margin_balance_usd

        sql = f'select * from dapi_{strategy}_value'
        try:
            df = pd.read_sql(sql, con=engine, index_col='index')
        except:
            df = pd.DataFrame()

        df = df.append(
            {
                'candle_begin_time':
                datetime.now().replace(second=0, microsecond=0),
                'net_value':
                float(margin_balance_usd),
                'usd_in':
                float(usd_in),
                'usd_out':
                float(usd_out),
                'init_value':
                0.0,
                'accumulate_value':
                1.0,
                'pct_change':
                1.0
            },
            ignore_index=True)
        if len(df) <= 1:
            df.iloc[0, df.columns.get_loc('init_value')] = margin_balance_usd
        else:
            df.iloc[-1, df.columns.get_loc('init_value')] = df.iloc[-2][
                'net_value'] + df.iloc[-1]['usd_in'] - df.iloc[-1]['usd_out']

            df.iloc[-1, df.columns.get_loc(
                'pct_change')] = df.iloc[-1]['net_value'] / df.iloc[-1][
                    'init_value'] if df.iloc[-1]['init_value'] > 0 else 1
            df.iloc[-1, df.columns.get_loc('accumulate_value')] = df.iloc[-2][
                'accumulate_value'] * df.iloc[-1]['pct_change']
        df = df[-1:]
        df.to_sql(name=f'dapi_{strategy}_value',
                  con=engine,
                  if_exists='append',
                  index=True)

    # 主账户合并
    sql = f'select * from dapi_all_account_value'
    try:
        df = pd.read_sql(sql, con=engine, index_col='index')
    except:
        df = pd.DataFrame()

    df = df.append(
        {
            'candle_begin_time': datetime.now().replace(second=0,
                                                        microsecond=0),
            'net_value': float(all_account_margin_balance),
            'usd_in': float(all_usd_in),
            'usd_out': float(all_usd_out),
            'init_value': 0.0,
            'accumulate_value': 1.0,
            'pct_change': 1.0
        },
        ignore_index=True)
    if len(df) <= 1:
        df.iloc[0,
                df.columns.get_loc('init_value')] = all_account_margin_balance
    else:
        df.iloc[-1, df.columns.get_loc('init_value')] = df.iloc[-2][
            'net_value'] + df.iloc[-1]['usd_in'] - df.iloc[-1]['usd_out']

        df.iloc[-1, df.columns.
                get_loc('pct_change')] = df.iloc[-1]['net_value'] / df.iloc[
                    -1]['init_value'] if df.iloc[-1]['init_value'] > 0 else 1
        df.iloc[-1, df.columns.get_loc('accumulate_value')] = df.iloc[-2][
            'accumulate_value'] * df.iloc[-1]['pct_change']
    df = df[-1:]
    df.to_sql(name=f'dapi_all_account_value',
              con=engine,
              if_exists='append',
              index=True)


def cta_excute_init(*args):
    with scheduler.app.app_context():
        exchange = args[0]
        symbol = args[1]
        interval = args[2]
        cta = args[3]
        period = args[4]

        # 初始化获取10000条K线
        symbol_data = get_kline(exchange, symbol, interval, 10000)
        cta_key = '_'.join(args[1:])
        symbol_data.to_csv(f'{fapi_path}/{cta_key}.csv', index=False)

        if interval.find('m') >= 0:  # 添加循环间隔是分钟的子类的定时任务
            scheduler.add_job(id=cta_key,
                              func=cta_excute_period,
                              args=args,
                              trigger='cron',
                              minute='*/' + interval.split('m')[0],
                              misfire_grace_time=300,
                              max_instances=1)
        elif interval.find('h') >= 0:  # 添加循环间隔是小时的子类的定时任务
            scheduler.add_job(id=cta_key,
                              func=cta_excute_period,
                              args=args,
                              trigger='cron',
                              hour='*/' + interval.split('h')[0],
                              misfire_grace_time=300,
                              max_instances=1)
        else:  # 注意暂时未判断按天的策略
            log_print(cta_key, '时间间隔格式错误，请修改')
        cta_usdt_update_trade_info(cta_key, data={'is_running': 1})
        log_print(f'{cta_key}策略启动成功')
        send_wechat(f'{cta_key}策略启动成功')
        time.sleep(1)


def cta_excute_init_all(params_list):
    for params in params_list:
        exchange = params[0]
        symbol = params[1]
        interval = params[2]
        cta = params[3]
        period = params[4]
        cta_excute_init(exchange, symbol, interval, cta, period)


def cta_signal_check_all(*args):
    with scheduler.app.app_context():
        params_list = cta_usdt_get_all_running_strategy()
        binance_list = args[0]
        for params in params_list:
            strategy = params[0]
            symbol = params[1]
            interval = params[2]
            cta = params[3]
            period = params[4]

            cta_key = '_'.join((symbol, interval, cta, period))

            if params[6] == 1:  # is_tpsl
                log_print(f'账户{strategy}标的{cta_key}已止盈止损，跳过信号检查')
                continue
            if not os.path.exists(f'{fapi_path}/{cta_key}.csv'):
                continue

            exchange = get_exchange(binance_list, strategy)

            cta_excute_period(exchange,
                              symbol,
                              interval,
                              cta,
                              period,
                              pos_infer=config.pos_infer)

        # 仓位校准部分
        # 获取开启CTA的strategy, 对每个strategy逐个处理
        params_list = cta_usdt_get_all_running_strategy()
        cta_strategy_list = list(set([params[0] for params in params_list]))
        for cta_strategy in cta_strategy_list:
            exchange = get_exchange(binance_list, cta_strategy)
            cta_check_position(exchange, params_list, cta_strategy)


def cta_check_position(exchange, params_list, cta_strategy):
    # 整理策略持仓
    columns = {
        0: 'strategy',
        1: 'symbol',
        2: 'interval',
        3: 'cta',
        4: 'period',
        5: '策略持仓量'
    }
    all_strategy_info = pd.DataFrame(data=params_list, dtype=float)
    all_strategy_info.rename(columns=columns, inplace=True)
    all_strategy_info = all_strategy_info[['strategy', 'symbol', '策略持仓量']]
    strategy_info = all_strategy_info[all_strategy_info['strategy'] ==
                                      cta_strategy]
    strategy_info['策略持仓量'].fillna(0, inplace=True)
    symbol_list = list(set(strategy_info['symbol'].to_list()))
    strategy_info_by_symbol = pd.DataFrame(index=symbol_list,
                                           columns=['策略持仓量'])
    strategy_info_by_symbol['策略持仓量'] = strategy_info.groupby(
        'symbol')['策略持仓量'].sum()

    # 整理当前持仓
    position_risk = robust(exchange.fapiPrivateV2_get_positionrisk,
                           func_name='fapiPrivateV2_get_positionrisk')
    # 将原始数据转化为dataframe
    position_risk = pd.DataFrame(position_risk, dtype='float')
    # 整理数据
    position_risk.rename(columns={'positionAmt': '当前持仓量'}, inplace=True)
    position_risk = position_risk[position_risk['当前持仓量'] != 0]  # 只保留有仓位的币种
    position_risk.set_index('symbol', inplace=True)  # 将symbol设置为index
    # 创建symbol_info
    symbol_info = pd.DataFrame(index=symbol_list, columns=['当前持仓量'])
    symbol_info['当前持仓量'] = position_risk['当前持仓量']
    symbol_info['当前持仓量'].fillna(value=0, inplace=True)

    # 整理待校准结果
    symbol_info['策略持仓量'] = strategy_info_by_symbol['策略持仓量']
    symbol_info['下单量'] = symbol_info['策略持仓量'] - symbol_info['当前持仓量']
    symbol_info = symbol_info[symbol_info['下单量'] != 0]

    for symbol, row in symbol_info.dropna(subset=['下单量']).iterrows():

        # 计算下单量：按照最小下单量向下取整
        order_amount = row['下单量']
        min_qty, price_precision = get_exchange_info(exchange)  # 下单量精度，价格精度
        last_price = fetch_binance_ticker_data(exchange, symbol)  # 最新价格
        order_amount = float(f'{order_amount:.{min_qty[symbol]}f}')
        if order_amount == 0:
            continue
        log_print(f'标的{symbol}所需下单量={order_amount}')
        if abs(order_amount) * last_price < 5:
            log_print(f'{symbol}仓位校准偏差低于最小下单量5U，请手动处理或忽略')
            send_wechat(f'{symbol}仓位校准偏差低于最小下单量5U，请手动处理或忽略')
            continue
        # 下单
        if cta_usdt_open_limit_order(exchange, symbol, order_amount, min_qty,
                                     price_precision, last_price):
            log_print(f'{symbol}仓位校准下单成功')
            send_wechat(f'{symbol}仓位校准下单成功')
        else:
            log_print(f'{symbol}仓位校准下单失败')
            send_wechat(f'{symbol}仓位校准下单失败')


def cta_excute_period(*args, **kwargs):
    with scheduler.app.app_context():
        exchange = args[0]
        symbol = args[1]
        interval = args[2]
        cta = args[3]
        period = args[4]
        pos_infer = kwargs.get('pos_infer', False)

        cta_key = '_'.join(args[1:])

        run_time = datetime.now()
        run_time = run_time.replace(second=0, microsecond=0)
        if interval.find('h') >= 0:
            interval_num = int(interval.split('h')[0])
            hour = run_time.hour // interval_num * interval_num
            run_time = run_time.replace(hour=hour, minute=0)
        elif interval.find('m') >= 0:
            interval_num = int(interval.split('m')[0])
            minute = run_time.minute // interval_num * interval_num
            run_time = run_time.replace(minute=minute)

        symbol_data = pd.read_csv(f'{fapi_path}/{cta_key}.csv',
                                  parse_dates=['candle_begin_time'])
        # 增量获取50条K线
        new_kline = get_kline(exchange, symbol, interval, 50)

        symbol_data = pd.concat([symbol_data, new_kline])
        symbol_data.sort_values(by=['candle_begin_time'], inplace=True)
        symbol_data.drop_duplicates(subset=['candle_begin_time'],
                                    keep='last',
                                    inplace=True)

        # 删除runtime那行的数据，如果有的话
        symbol_data = symbol_data[symbol_data['candle_begin_time'] < run_time]
        symbol_data.reset_index(drop=True, inplace=True)
        symbol_data.iloc[-10000:].to_csv(f'{fapi_path}/{cta_key}.csv',
                                         index=False)

        df, *_ = getattr(factors, cta)(symbol_data.copy(), int(period))

        # 是否开启信号定期校准, 校准数据库与实盘信号差异
        if pos_infer:
            df['signal'].fillna(method='ffill', inplace=True)
            log_print(f'{cta_key}信号定期校准开始')

        signal = df.iloc[-1]['signal']
        log_print(f'{cta_key}本次下单信号为{signal}')

        if signal is None or np.isnan(signal):
            pass
        elif signal == 1 or signal == -1:
            # 获取应该开仓的金额及杠杆率及策略当前持仓量
            trade_info = cta_usdt_get_trade_info(cta_key)
            if trade_info is None:
                log_print(f'{cta_key} 获取trade_info执行失败，请修复问题')
                send_wechat(f'{cta_key} 获取trade_info执行失败，请修复问题')
                return
            # 上次交易信号为0的情况，比较简单，直接获取净值计算并下单就可以
            elif signal == trade_info['signal']:
                log_print(f'{cta_key}上次信号与本次信号相同，无需操作')
            elif trade_info['signal'] == 0:
                net_value = trade_info['net_value']  # 策略当前净值
                trade_ratio = trade_info['trade_ratio']  # 策略杠杆
                position_amount = trade_info['position_amount']  # 策略当前持仓
                min_qty, price_precision = get_exchange_info(
                    exchange)  # 下单量精度，价格精度
                last_price = fetch_binance_ticker_data(exchange,
                                                       symbol)  # 最新价格
                target_amount = net_value * trade_ratio * Decimal(
                    signal) / Decimal(last_price)  # 目标下单量
                order_amount = target_amount - position_amount  # 所需下单量 = 目标下单量 - 当前持仓量
                target_amount = float(f'{target_amount:.{min_qty[symbol]}f}')
                order_amount = float(f'{order_amount:.{min_qty[symbol]}f}')
                log_print(f'标的{symbol}所需下单量={order_amount}')
                # 下单并更新数据库
                if cta_usdt_open_limit_order(exchange, symbol, order_amount,
                                             min_qty, price_precision,
                                             last_price):
                    log_print(f'{cta_key}下单成功')
                    send_wechat(f'{cta_key}下单成功，signal = {signal}')
                    data = {
                        'signal': signal,
                        'signal_time': datetime.now(),
                        'open_price': last_price,
                        'position_amount': target_amount,
                        'is_tpsl': 0,
                    }
                    log_print(f'交易信息{data}')
                    cta_usdt_update_trade_info(cta_key, data)
                else:
                    log_print(f'{cta_key}下单失败，signal={signal}')
                    send_wechat(f'{cta_key}下单失败，signal={signal}')
                    return
            elif trade_info['signal'] != 0:
                open_price = trade_info['open_price']  # 策略上次开仓价
                init_value = trade_info['init_value']
                net_value = trade_info['net_value']  # 策略当前净值
                trade_ratio = trade_info['trade_ratio']  # 策略杠杆
                position_amount = trade_info['position_amount']  # 策略当前持仓
                min_qty, price_precision = get_exchange_info(
                    exchange)  # 下单量精度，价格精度
                last_price = fetch_binance_ticker_data(exchange,
                                                       symbol)  # 最新价格
                net_value = (
                    (Decimal(last_price) / open_price - 1) *
                    trade_info['signal'] * trade_ratio + 1
                ) * net_value  # 计算最新的net_value，当前价格/开仓价格-1是涨跌幅，根据上一个signal类型及杠杆确定实际盈亏百分比，加1之后乘以之前记录的net_value，得到最新的net_value
                target_amount = net_value * trade_ratio * Decimal(
                    signal) / Decimal(last_price)  # 目标下单量
                order_amount = target_amount - position_amount  # 所需下单量 = 目标下单量 - 当前持仓量
                target_amount = float(f'{target_amount:.{min_qty[symbol]}f}')
                order_amount = float(f'{order_amount:.{min_qty[symbol]}f}')
                log_print(f'标的{symbol}所需下单量={order_amount}')
                # 下单并更新数据库
                if cta_usdt_open_limit_order(exchange, symbol, order_amount,
                                             min_qty, price_precision,
                                             last_price):
                    log_print(f'{cta_key}下单成功')
                    send_wechat(f'{cta_key}下单成功，signal = {signal}')
                    data = {
                        'signal': signal,
                        'signal_time': datetime.now(),
                        'open_price': last_price,
                        'close_price': last_price,
                        'profit': net_value - init_value,
                        'net_value': net_value,
                        'position_amount': target_amount,
                        'is_tpsl': 0,
                    }
                    log_print(f'交易信息{data}')
                    cta_usdt_update_trade_info(cta_key, data)
                else:
                    log_print(f'{cta_key}下单失败，signal={signal}')
                    send_wechat(f'{cta_key}下单失败，signal={signal}')
                    return
        elif signal == 0:
            # 获取应该开仓的金额及杠杆率及策略当前持仓量
            trade_info = cta_usdt_get_trade_info(cta_key)
            if trade_info is None:
                log_print(f'{cta_key} 执行失败，请修复问题')
                send_wechat(f'{cta_key} 执行失败，请修复问题')
                return
            elif trade_info['signal'] == 0:
                # last_price = fetch_binance_ticker_data(exchange,
                #                                        symbol)  # 最新价格
                # data = {
                #     'signal': signal,
                #     'signal_time': datetime.now(),
                #     'open_price': last_price,
                #     'close_price': last_price,
                #     'position_amount': 0
                # }
                # log_print(f'交易信息{data}')
                # cta_usdt_update_trade_info(cta_key, data)
                log_print(f'{cta_key}上次信号为平仓，本次也为平仓，无需操作')
            # 需要平仓
            elif trade_info['signal'] != 0:
                open_price = trade_info['open_price']  # 策略上次开仓价
                init_value = trade_info['init_value']
                net_value = trade_info['net_value']  # 策略当前净值
                trade_ratio = trade_info['trade_ratio']  # 策略杠杆
                position_amount = trade_info['position_amount']  # 策略当前持仓
                min_qty, price_precision = get_exchange_info(
                    exchange)  # 下单量精度，价格精度
                last_price = fetch_binance_ticker_data(exchange,
                                                       symbol)  # 最新价格
                net_value = (
                    (Decimal(last_price) / open_price - 1) *
                    trade_info['signal'] * trade_ratio + 1
                ) * net_value  # 计算最新的net_value，当前价格/开仓价格-1是涨跌幅，根据上一个signal类型及杠杆确定实际盈亏百分比，加1之后乘以之前记录的net_value，得到最新的net_value
                target_amount = 0  # 目标下单量
                order_amount = target_amount - position_amount  # 所需下单量 = 目标下单量 - 当前持仓量
                target_amount = float(f'{target_amount:.{min_qty[symbol]}f}')
                order_amount = float(f'{order_amount:.{min_qty[symbol]}f}')
                log_print(f'标的{symbol}所需下单量={order_amount}')
                # 下单并更新数据库
                if cta_usdt_open_limit_order(exchange, symbol, order_amount,
                                             min_qty, price_precision,
                                             last_price):
                    log_print(f'{cta_key}下单成功')
                    send_wechat(f'{cta_key}下单成功，signal = {signal}')
                    data = {
                        'signal': signal,
                        'signal_time': datetime.now(),
                        'close_price': last_price,
                        'net_value': net_value,
                        'profit': net_value - init_value,
                        'position_amount': target_amount,
                        'is_tpsl': 0,
                    }
                    log_print(f'交易信息{data}')
                    cta_usdt_update_trade_info(cta_key, data)
                else:
                    log_print(f'{cta_key}下单失败，signal={signal}')
                    send_wechat(f'{cta_key}下单失败，signal={signal}')
                    return

        log_print(f'{cta_key} 执行成功\n')
        if pos_infer:
            log_print(f'{cta_key}信号定期校准结束')
        del symbol_data, df


def cta_usdt_replenish_bnb(*args):
    global base_bnb_dict
    with scheduler.app.app_context():
        binance_list = args[0]
        params_list = cta_usdt_get_all_running_strategy()
        cta_strategy_list = list(set([params[0] for params in params_list]))
        for cta_strategy in cta_strategy_list:
            exchange = get_exchange(binance_list, cta_strategy)
            account_info = exchange.fapiPrivateV2_get_account()
            BNB_df = pd.DataFrame(account_info['assets'])
            amount_bnb = float(
                BNB_df[BNB_df['asset'] == 'BNB']['walletBalance'].iloc[0])
            if cta_strategy not in base_bnb_dict:
                base_bnb_dict[cta_strategy] = float(
                    f'{amount_bnb:.3f}') if amount_bnb > 0.1 else 0
            replenish_bnb(exchange, account_info, base_bnb_dict[cta_strategy])


def alpha_takeprofit_and_stoploss(*args):
    with scheduler.app.app_context():
        exchange = args[0]
        strategy = args[1]
        log_print(f'正在进行策略{strategy}的止盈止损监测')
        res = strategy_get_row(strategy)
        if res['status'] != 0:
            log_print(f'{strategy}止盈止损执行出错，请排查')
            send_wechat(f'{strategy}止盈止损执行出错，请排查')
            return
        takeprofit_percentage = Decimal(res['data']['takeprofit_percentage'])
        stoploss_percentage = Decimal(res['data']['stoploss_percentage'])
        log_print(
            f'{strategy}止盈比例为{takeprofit_percentage:.2f},止损比例为{stoploss_percentage:.2f}'
        )

        account_info = exchange.fapiPrivateV2_get_account()['positions']
        position = [
            p for p in account_info if Decimal(p['positionInitialMargin']) > 0
        ]

        # 获取当前策略的移动止盈信息
        try:
            df = pd.read_csv(f'{alpha_path}/{strategy}.csv')
        except:
            df = pd.DataFrame(columns=['symbol', 'max_profit_ratio'])

        symbol_list = []
        profit_list = []
        for pos in position:
            symbol = pos['symbol']
            margin = Decimal(pos['initialMargin'])
            profit = Decimal(pos['unrealizedProfit'])
            pos_amount = Decimal(pos['positionAmt'])
            position_usd = Decimal(pos['notional'])
            leverage = Decimal(pos['leverage'])
            profit_ratio = Decimal(
                f'{(profit / abs(position_usd - profit)):.4f}')

            symbol_list.append(symbol)
            profit_list.append([symbol, profit_ratio])

            # 止损条件
            condition_sl = profit < 0 and abs(
                profit_ratio
            ) >= stoploss_percentage  # 如果当前盈利为负数，且大于触发百分比，币种进黑名单

            try:
                max_profit_ratio = Decimal(
                    df[df['symbol'] == symbol]['max_profit_ratio'].iloc[0])
            except:
                max_profit_ratio = None

            # 止盈条件
            if max_profit_ratio is None:
                condition_tp = False
            else:
                condition_tp = profit > 0 and max_profit_ratio > takeprofit_percentage and max_profit_ratio - profit_ratio >= takeprofit_drawdown_percentage

            if float(pos_amount) > 0:
                direction = "做多"
                # log_print(
                #     f"{strategy}持仓: {pos['symbol']}, {direction}, 量: {round(position_usd, 2)}U, 盈亏: {round(profit_ratio, 4) * 100}%"
                # )
                if condition_sl:
                    release_time = int(
                        time.time()) + blacklist_hours * 3600  # 拉黑释放时间
                    t1 = close_order(exchange, symbol)['status']
                    t2 = long_backlist_create(strategy, {
                        'symbol': symbol,
                        'release_time': release_time
                    })['status']
                    if t1 == 0 and t2 == 0:
                        log_print(
                            f'{strategy} {direction}{symbol}已止损并加入黑名单，亏损{round(profit_ratio, 4) * 100}%'
                        )
                        send_wechat(
                            f'{strategy} {direction}{symbol}已止损并加入黑名单，亏损{round(profit_ratio, 4) * 100}%'
                        )
                    else:
                        log_print(
                            f'{strategy} {direction}{symbol}止损并拉入黑名单失败，请排查')
                        send_wechat(
                            f'{strategy} {direction}{symbol}止损并拉入黑名单失败，请排查')
                if condition_tp:
                    release_time = int(
                        time.time()) + blacklist_hours * 3600  # 拉黑释放时间
                    t1 = close_order(exchange, symbol)['status']
                    t2 = long_backlist_create(strategy, {
                        'symbol': symbol,
                        'release_time': release_time
                    })['status']
                    if t1 == 0 and t2 == 0:
                        log_print(
                            f'{strategy} {direction}{symbol}已止盈并加入黑名单，盈利{round(profit_ratio, 4) * 100}%'
                        )
                        send_wechat(
                            f'{strategy} {direction}{symbol}已止盈并加入黑名单，盈利{round(profit_ratio, 4) * 100}%'
                        )
                    else:
                        log_print(
                            f'{strategy} {direction}{symbol}止盈并拉入黑名单失败，请排查')
                        send_wechat(
                            f'{strategy} {direction}{symbol}止盈并拉入黑名单失败，请排查')

            if float(pos_amount) < 0:
                direction = "做空"
                # log_print(
                #     f"{strategy}持仓: {pos['symbol']}, {direction}, 量: {round(position_usd, 2)}U, 盈亏: {round(profit_ratio, 4) * 100}%"
                # )
                if condition_sl:
                    release_time = int(
                        time.time()) + blacklist_hours * 3600  # 拉黑释放时间
                    t1 = close_order(exchange, symbol)['status']
                    t2 = short_backlist_create(strategy, {
                        'symbol': symbol,
                        'release_time': release_time
                    })['status']
                    if t1 == 0 and t2 == 0:
                        log_print(
                            f'{strategy} {direction}{symbol}已止损并加入黑名单，亏损{round(profit_ratio, 4) * 100}%'
                        )
                        send_wechat(
                            f'{strategy} {direction}{symbol}已止损并加入黑名单，亏损{round(profit_ratio, 4) * 100}%'
                        )
                    else:
                        log_print(
                            f'{strategy} {direction}{symbol}止损并拉入黑名单失败，请排查')
                        send_wechat(
                            f'{strategy} {direction}{symbol}止损并拉入黑名单失败，请排查')
                if condition_tp:
                    release_time = int(
                        time.time()) + blacklist_hours * 3600  # 拉黑释放时间
                    t1 = close_order(exchange, symbol)['status']
                    t2 = short_backlist_create(strategy, {
                        'symbol': symbol,
                        'release_time': release_time
                    })['status']
                    if t1 == 0 and t2 == 0:
                        log_print(
                            f'{strategy} {direction}{symbol}已止盈并加入黑名单，盈利{round(profit_ratio, 4) * 100}%'
                        )
                        send_wechat(
                            f'{strategy} {direction}{symbol}已止盈并加入黑名单，盈利{round(profit_ratio, 4) * 100}%'
                        )
                    else:
                        log_print(
                            f'{strategy} {direction}{symbol}止盈并拉入黑名单失败，请排查')
                        send_wechat(
                            f'{strategy} {direction}{symbol}止盈并拉入黑名单失败，请排查')

        df = df.append(
            pd.DataFrame(profit_list, columns=['symbol', 'max_profit_ratio']))
        df = df[df['max_profit_ratio'] > 0]
        df.sort_values('max_profit_ratio', ascending=False, inplace=True)
        df.drop_duplicates(subset='symbol', keep='first', inplace=True)
        df = df[df['symbol'].isin(symbol_list)]
        df.to_csv(f'{alpha_path}/{strategy}.csv', index=False)
        log_print(f'策略{strategy}止盈止损监测完成')


def cta_usdt_takeprofit_and_stoploss(*args):
    with scheduler.app.app_context():
        binance_list = args[0]
        cta_keys = cta_usdt_get_all_need_tpsl_cta_keys()
        # 获取当前策略的移动止盈信息
        try:
            df = pd.read_csv(f'{fapi_path}/cta_usdt_tpsl.csv')
        except:
            df = pd.DataFrame(
                columns=['symbol', 'cta_key', 'max_profit_ratio'])

        profit_list = []
        for cta_key in cta_keys:
            log_print(f'正在进行策略{cta_key}的止盈止损监测')
            trade_info = cta_usdt_get_trade_info(cta_key)
            if trade_info is None:
                log_print(f'{cta_key}止盈止损执行出错，请排查')
                send_wechat(f'{cta_key}止盈止损执行出错，请排查')
                continue
            open_tpsl = trade_info['open_tpsl']
            if open_tpsl == 0:
                log_print(f'{cta_key}未开启止盈止损,无需止盈止损')
                continue
            signal = trade_info['signal']
            takeprofit_percentage = Decimal(
                trade_info['takeprofit_percentage'])
            cta_takeprofit_drawdown_percentage = Decimal(
                trade_info['takeprofit_drawdown_percentage'])
            stoploss_percentage = Decimal(trade_info['stoploss_percentage'])
            log_print(
                f'{cta_key}止盈比例为{takeprofit_percentage:.2f},止损比例为{stoploss_percentage:.2f}'
            )
            if signal == 0:
                log_print(f'{cta_key}未开仓,无需止盈止损')
                continue

            strategy_name = trade_info['strategy']
            exchange = get_exchange(binance_list, strategy_name)

            symbol = trade_info['symbol']
            pos_amount = Decimal(trade_info['position_amount'])
            open_price = trade_info['open_price']
            last_price = Decimal(fetch_binance_ticker_data(exchange, symbol))
            profit_ratio = Decimal(
                f'{signal * (last_price / open_price - 1):.4f}')

            profit_list.append([symbol, cta_key, profit_ratio])

            cta_stoploss_inside_bar = getattr(config,
                                              "cta_stoploss_inside_bar", True)
            # bar内止损检查
            condition_inside_bar = cta_stoploss_inside_bar or (
                datetime.now().timestamp() %
                int(pd.to_timedelta(trade_info['interval']).total_seconds()) <
                max(pd.to_timedelta(cta_tpsl_time).seconds, 30))

            # 止损条件
            condition_sl = condition_inside_bar and profit_ratio < 0 and abs(
                profit_ratio
            ) >= stoploss_percentage  # 如果当前盈利为负数，且大于触发百分比，币种进黑名单

            try:
                max_profit_ratio = Decimal(df[(df['symbol'] == symbol) & (
                    df['cta_key'] == cta_key)]['max_profit_ratio'].iloc[0])
            except:
                max_profit_ratio = None

            # 止盈条件
            if max_profit_ratio is None:
                condition_tp = False
            else:
                condition_tp = profit_ratio > 0 and max_profit_ratio > takeprofit_percentage and max_profit_ratio - profit_ratio >= cta_takeprofit_drawdown_percentage

            if float(pos_amount) > 0:
                direction = "做多"
                # log_print(
                #     f"{cta_key}持仓: {symbol}, {direction}, 量: {pos_amount * last_price:.2f}U, 盈亏: {round(profit_ratio, 4) * 100}%"
                # )
                if condition_sl:
                    t1 = cta_usdt_tpsl_close_order(exchange, trade_info,
                                                   cta_key)
                    if t1:
                        log_print(
                            f'{cta_key} {direction}{symbol}已止损，亏损{round(profit_ratio, 4) * 100}%'
                        )
                        send_wechat(
                            f'{cta_key} {direction}{symbol}已止损，亏损{round(profit_ratio, 4) * 100}%'
                        )
                    else:
                        log_print(f'{cta_key} {direction}{symbol}止损失败，请排查')
                        send_wechat(f'{cta_key} {direction}{symbol}止损失败，请排查')
                if condition_tp:
                    t1 = cta_usdt_tpsl_close_order(exchange, trade_info,
                                                   cta_key)
                    if t1:
                        log_print(
                            f'{cta_key} {direction}{symbol}已止盈，盈利{round(profit_ratio, 4) * 100}%'
                        )
                        send_wechat(
                            f'{cta_key} {direction}{symbol}已止盈，盈利{round(profit_ratio, 4) * 100}%'
                        )
                    else:
                        log_print(f'{cta_key} {direction}{symbol}止盈失败，请排查')
                        send_wechat(f'{cta_key} {direction}{symbol}止盈失败，请排查')

            if float(pos_amount) < 0:
                direction = "做空"
                # log_print(
                #     f"{cta_key}持仓: {symbol}, {direction}, 量: {pos_amount * last_price:.2f}U, 盈亏: {round(profit_ratio, 4) * 100}%"
                # )
                if condition_sl:
                    t1 = cta_usdt_tpsl_close_order(exchange, trade_info,
                                                   cta_key)
                    if t1:
                        log_print(
                            f'{cta_key} {direction}{symbol}已止损，亏损{round(profit_ratio, 4) * 100}%'
                        )
                        send_wechat(
                            f'{cta_key} {direction}{symbol}已止损，亏损{round(profit_ratio, 4) * 100}%'
                        )
                    else:
                        log_print(f'{cta_key} {direction}{symbol}止损失败，请排查')
                        send_wechat(f'{cta_key} {direction}{symbol}止损失败，请排查')
                if condition_tp:
                    t1 = cta_usdt_tpsl_close_order(exchange, trade_info,
                                                   cta_key)
                    if t1:
                        log_print(
                            f'{cta_key} {direction}{symbol}已止盈，盈利{round(profit_ratio, 4) * 100}%'
                        )
                        send_wechat(
                            f'{cta_key} {direction}{symbol}已止盈，盈利{round(profit_ratio, 4) * 100}%'
                        )
                    else:
                        log_print(f'{cta_key} {direction}{symbol}止盈失败，请排查')
                        send_wechat(f'{cta_key} {direction}{symbol}止盈失败，请排查')

            log_print(f'策略{cta_key}止盈止损监测完成')

        df = df.append(
            pd.DataFrame(profit_list,
                         columns=['symbol', 'cta_key', 'max_profit_ratio']))
        df = df[df['max_profit_ratio'] > 0]
        df.sort_values('max_profit_ratio', ascending=False, inplace=True)
        df.drop_duplicates(subset=['symbol', 'cta_key'],
                           keep='first',
                           inplace=True)
        df = df[df['cta_key'].isin(cta_keys)]
        df.to_csv(f'{fapi_path}/cta_usdt_tpsl.csv', index=False)
        log_print(f'U本位CTA策略止盈止损监测完成')


def scheduler_deribit_account_balance(*args):
    engine = create_engine(sql_uri)
    for duck in args:
        exchange = duck['exchange']
        strategy = duck['strategy']
        log_print(f'deribit {strategy} start')
        # 获取账户当前的净值
        equity_usd = 0
        balance_items = get_deribit_account_balance(exchange)['data']['items']

        row = {}
        for item in balance_items:
            symbol = item['symbol']
            equity = item['equity']
            equity_usd += item['equity_usd']
            row[symbol] = equity
            row[f'{symbol}_usd'] = item['equity_usd']

        row['equity_usd'] = equity_usd
        row['candle_begin_time'] = datetime.now().replace(second=0,
                                                          microsecond=0)

        sql = f'select * from deribit_{strategy}_value'
        try:
            df = pd.read_sql(sql, con=engine, index_col='index')
        except:
            df = pd.DataFrame(columns=[
                'candle_begin_time', 'equity_usd', 'BTC', 'BTC_usd', 'ETH',
                'ETH_usd', 'SOL', 'SOL_usd', 'USDC', 'USDC_usd'
            ])

        df = df.append(row, ignore_index=True)
        df.reset_index(inplace=True, drop=True)
        df = df[-1:]
        df.to_sql(name=f'deribit_{strategy}_value',
                  con=engine,
                  if_exists='append',
                  index=True)


def cta_usd_excute_init(*args):
    with scheduler.app.app_context():
        exchange = args[0]
        symbol = args[1]
        interval = args[2]
        cta = args[3]
        period = args[4]

        # 初始化获取10000条K线
        symbol_data = dapi_get_kline(exchange, symbol, interval, 10000)
        cta_key = '_'.join(args[1:])
        symbol_data.to_csv(f'{dapi_path}/{cta_key}.csv', index=False)

        if interval.find('m') >= 0:  # 添加循环间隔是分钟的子类的定时任务
            scheduler.add_job(id=cta_key,
                              func=cta_usd_excute_period,
                              args=args,
                              trigger='cron',
                              minute='*/' + interval.split('m')[0],
                              misfire_grace_time=300,
                              max_instances=1)
        elif interval.find('h') >= 0:  # 添加循环间隔是小时的子类的定时任务
            scheduler.add_job(id=cta_key,
                              func=cta_usd_excute_period,
                              args=args,
                              trigger='cron',
                              hour='*/' + interval.split('h')[0],
                              misfire_grace_time=300,
                              max_instances=1)
        else:  # 注意暂时未判断按天的策略
            log_print(cta_key, '时间间隔格式错误，请修改')
        cta_usd_update_trade_info(cta_key, data={'is_running': 1})
        log_print(f'{cta_key}策略启动成功')
        send_wechat(f'{cta_key}策略启动成功')
        time.sleep(1)


def cta_usd_excute_init_all(params_list):
    for params in params_list:
        exchange = params[0]
        symbol = params[1]
        interval = params[2]
        cta = params[3]
        period = params[4]
        cta_usd_excute_init(exchange, symbol, interval, cta, period)


def cta_usd_signal_check_all(*args):
    with scheduler.app.app_context():
        params_list = cta_usd_get_all_running_strategy()
        binance_list = args[0]
        for params in params_list:
            strategy = params[0]
            symbol = params[1]
            interval = params[2]
            cta = params[3]
            period = params[4]

            cta_key = '_'.join((symbol, interval, cta, period))

            if params[6] == 1:  # is_tpsl
                log_print(f'账户{strategy}标的{cta_key}已止盈止损，跳过信号检查')
                continue
            if not os.path.exists(f'{dapi_path}/{cta_key}.csv'):
                continue

            exchange = get_exchange(binance_list, strategy)

            cta_usd_excute_period(exchange,
                                  symbol,
                                  interval,
                                  cta,
                                  period,
                                  pos_infer=config.pos_infer)

        # 仓位校准部分
        # 获取开启CTA和半套的strategy, 对每个strategy逐个处理
        params_list = cta_usd_get_all_running_strategy()
        params_list_rebalance = cta_usd_get_all_rebalance_strategy()
        params_list.extend(params_list_rebalance)
        cta_usd_strategy_list = list(set([params[0]
                                          for params in params_list]))

        for cta_usd_strategy in cta_usd_strategy_list:
            exchange = get_exchange(binance_list, cta_usd_strategy)
            cta_usd_check_position(exchange, params_list, cta_usd_strategy)


def cta_usd_check_position(exchange, params_list, cta_usd_strategy):
    # 整理策略持仓
    columns = {
        0: 'strategy',
        1: 'symbol',
        2: 'interval',
        3: 'cta',
        4: 'period',
        5: '策略持仓量'
    }
    all_strategy_info = pd.DataFrame(data=params_list, dtype=float)
    all_strategy_info.rename(columns=columns, inplace=True)
    all_strategy_info = all_strategy_info[['strategy', 'symbol', '策略持仓量']]
    strategy_info = all_strategy_info[all_strategy_info['strategy'] ==
                                      cta_usd_strategy]
    strategy_info['策略持仓量'].fillna(0, inplace=True)
    symbol_list = list(set(strategy_info['symbol'].to_list()))
    strategy_info_by_symbol = pd.DataFrame(index=symbol_list,
                                           columns=['策略持仓量'])
    strategy_info_by_symbol['策略持仓量'] = strategy_info.groupby(
        'symbol')['策略持仓量'].sum()

    # 整理当前持仓
    position_risk = robust(exchange.dapiPrivate_get_positionrisk,
                           func_name='dapiPrivate_get_positionrisk')
    # 将原始数据转化为dataframe
    position_risk = pd.DataFrame(position_risk, dtype='float')
    # 整理数据
    position_risk.rename(columns={'positionAmt': '当前持仓量'}, inplace=True)
    position_risk = position_risk[position_risk['当前持仓量'] != 0]  # 只保留有仓位的币种
    position_risk.set_index('symbol', inplace=True)  # 将symbol设置为index
    # 创建symbol_info
    symbol_info = pd.DataFrame(index=symbol_list, columns=['当前持仓量'])
    symbol_info['当前持仓量'] = position_risk['当前持仓量']
    symbol_info['当前持仓量'].fillna(value=0, inplace=True)

    # 整理待校准结果
    symbol_info['策略持仓量'] = strategy_info_by_symbol['策略持仓量']
    symbol_info['下单量'] = symbol_info['策略持仓量'] - symbol_info['当前持仓量']
    symbol_info = symbol_info[symbol_info['下单量'] != 0]

    for symbol, row in symbol_info.dropna(subset=['下单量']).iterrows():

        # 计算下单量：按照最小下单量向下取整
        order_amount = row['下单量']
        price_precision = get_dapi_exchange_info(exchange)  # 下单量精度，价格精度
        last_price = fetch_binance_dapi_ticker_data(exchange, symbol)  # 最新价格
        order_amount = float(f'{order_amount:0f}')
        if order_amount == 0:
            continue
        log_print(f'标的{symbol}所需下单量={order_amount}')
        # 下单
        if cta_usd_open_limit_order(exchange, symbol, order_amount,
                                    price_precision, last_price):
            log_print(f'{symbol}仓位校准下单成功')
            send_wechat(f'{symbol}仓位校准下单成功')
        else:
            log_print(f'{symbol}仓位校准下单失败')
            send_wechat(f'{symbol}仓位校准下单失败')


def cta_usd_excute_period(*args, **kwargs):
    with scheduler.app.app_context():
        exchange = args[0]
        symbol = args[1]
        interval = args[2]
        cta = args[3]
        period = args[4]
        pos_infer = kwargs.get('pos_infer', False)

        cta_key = '_'.join(args[1:])

        run_time = datetime.now()
        run_time = run_time.replace(second=0, microsecond=0)
        if interval.find('h') >= 0:
            interval_num = int(interval.split('h')[0])
            hour = run_time.hour // interval_num * interval_num
            run_time = run_time.replace(hour=hour, minute=0)
        elif interval.find('m') >= 0:
            interval_num = int(interval.split('m')[0])
            minute = run_time.minute // interval_num * interval_num
            run_time = run_time.replace(minute=minute)

        symbol_data = pd.read_csv(f'{dapi_path}/{cta_key}.csv',
                                  parse_dates=['candle_begin_time'])
        # 增量获取50条K线
        new_kline = dapi_get_kline(exchange, symbol, interval, 50)

        symbol_data = pd.concat([symbol_data, new_kline])
        symbol_data.sort_values(by=['candle_begin_time'], inplace=True)
        symbol_data.drop_duplicates(subset=['candle_begin_time'],
                                    keep='last',
                                    inplace=True)

        # 删除runtime那行的数据，如果有的话
        symbol_data = symbol_data[symbol_data['candle_begin_time'] < run_time]
        symbol_data.reset_index(drop=True, inplace=True)
        symbol_data.iloc[-10000:].to_csv(f'{dapi_path}/{cta_key}.csv',
                                         index=False)

        df, *_ = getattr(factors, cta)(symbol_data.copy(), int(period))

        # 是否开启信号定期校准, 校准数据库与实盘信号差异
        if pos_infer:
            df['signal'].fillna(method='ffill', inplace=True)
            log_print(f'{cta_key}信号定期校准开始')

        signal = df.iloc[-1]['signal']
        log_print(f'{cta_key}本次下单信号为{signal}')

        if signal is None or np.isnan(signal):
            pass
        elif signal == 1 or signal == -1:
            # 获取应该开仓的金额及杠杆率及策略当前持仓量
            trade_info = cta_usd_get_trade_info(cta_key)
            if trade_info is None:
                log_print(f'{cta_key} 获取trade_info执行失败，请修复问题')
                send_wechat(f'{cta_key} 获取trade_info执行失败，请修复问题')
                return
            # 上次交易信号为0的情况，比较简单，直接获取净值计算并下单就可以
            elif signal == trade_info['signal']:
                log_print(f'{cta_key}上次信号与本次信号相同，无需操作')
            elif trade_info['signal'] == 0:
                net_value = trade_info['net_value']  # 策略当前净值
                trade_ratio = trade_info['trade_ratio']  # 策略杠杆
                position_amount = trade_info['position_amount']  # 策略当前持仓
                price_precision = get_dapi_exchange_info(
                    exchange)  # 下单量精度，价格精度
                last_price = fetch_binance_dapi_ticker_data(exchange,
                                                            symbol)  # 最新价格
                target_amount = net_value * trade_ratio * Decimal(
                    signal)  # 目标下单量
                order_amount = target_amount - position_amount  # 所需下单量 = 目标下单量 - 当前持仓量
                target_amount = float(f'{target_amount:.0f}')
                order_amount = float(f'{order_amount:0f}')
                log_print(f'标的{symbol}所需下单张数={order_amount}')
                # 下单并更新数据库
                if cta_usd_open_limit_order(exchange, symbol, order_amount,
                                            price_precision, last_price):
                    log_print(f'{cta_key}下单成功')
                    send_wechat(f'{cta_key}下单成功，signal = {signal}')
                    data = {
                        'signal': signal,
                        'signal_time': datetime.now(),
                        'open_price': last_price,
                        'position_amount': target_amount,
                        'is_tpsl': 0,
                    }
                    log_print(f'交易信息{data}')
                    cta_usd_update_trade_info(cta_key, data)
                else:
                    log_print(f'{cta_key}下单失败，signal={signal}')
                    send_wechat(f'{cta_key}下单失败，signal={signal}')
                    return
            elif trade_info['signal'] != 0:
                open_price = trade_info['open_price']  # 策略上次开仓价
                init_value = trade_info['init_value']
                net_value = trade_info['net_value']  # 策略当前净值
                trade_ratio = trade_info['trade_ratio']  # 策略杠杆
                position_amount = trade_info['position_amount']  # 策略当前持仓
                price_precision = get_dapi_exchange_info(
                    exchange)  # 下单量精度，价格精度
                last_price = fetch_binance_dapi_ticker_data(exchange,
                                                            symbol)  # 最新价格
                net_value = (
                    (Decimal(last_price) / open_price - 1) *
                    trade_info['signal'] * trade_ratio + 1
                ) * net_value  # 计算最新的net_value，当前价格/开仓价格-1是涨跌幅，根据上一个signal类型及杠杆确定实际盈亏百分比，加1之后乘以之前记录的net_value，得到最新的net_value
                target_amount = net_value * trade_ratio * Decimal(
                    signal)  # 目标下单量
                order_amount = target_amount - position_amount  # 所需下单量 = 目标下单量 - 当前持仓量
                target_amount = float(f'{target_amount:.0f}')
                order_amount = float(f'{order_amount:.0f}')
                log_print(f'标的{symbol}所需下单张数={order_amount}')
                # 下单并更新数据库
                if cta_usd_open_limit_order(exchange, symbol, order_amount,
                                            price_precision, last_price):
                    log_print(f'{cta_key}下单成功')
                    send_wechat(f'{cta_key}下单成功，signal = {signal}')
                    data = {
                        'signal': signal,
                        'signal_time': datetime.now(),
                        'open_price': last_price,
                        'close_price': last_price,
                        'profit': net_value - init_value,
                        'net_value': net_value,
                        'position_amount': target_amount,
                        'is_tpsl': 0,
                    }
                    log_print(f'交易信息{data}')
                    cta_usd_update_trade_info(cta_key, data)
                else:
                    log_print(f'{cta_key}下单失败，signal={signal}')
                    send_wechat(f'{cta_key}下单失败，signal={signal}')
                    return
        elif signal == 0:
            # 获取应该开仓的金额及杠杆率及策略当前持仓量
            trade_info = cta_usd_get_trade_info(cta_key)
            if trade_info is None:
                log_print(f'{cta_key} 执行失败，请修复问题')
                send_wechat(f'{cta_key} 执行失败，请修复问题')
                return
            elif trade_info['signal'] == 0:
                # last_price = fetch_binance_dapi_ticker_data(exchange,
                #                                             symbol)  # 最新价格
                # data = {
                #     'signal': signal,
                #     'signal_time': datetime.now(),
                #     'open_price': last_price,
                #     'close_price': last_price,
                #     'position_amount': 0
                # }
                # log_print(f'交易信息{data}')
                # cta_usd_update_trade_info(cta_key, data)
                log_print(f'{cta_key}上次信号为平仓，本次也为平仓，无需操作')
            # 需要平仓
            elif trade_info['signal'] != 0:
                open_price = trade_info['open_price']  # 策略上次开仓价
                init_value = trade_info['init_value']
                net_value = trade_info['net_value']  # 策略当前净值
                trade_ratio = trade_info['trade_ratio']  # 策略杠杆
                position_amount = trade_info['position_amount']  # 策略当前持仓
                price_precision = get_dapi_exchange_info(
                    exchange)  # 下单量精度，价格精度
                last_price = fetch_binance_dapi_ticker_data(exchange,
                                                            symbol)  # 最新价格
                net_value = (
                    (Decimal(last_price) / open_price - 1) *
                    trade_info['signal'] * trade_ratio + 1
                ) * net_value  # 计算最新的net_value，当前价格/开仓价格-1是涨跌幅，根据上一个signal类型及杠杆确定实际盈亏百分比，加1之后乘以之前记录的net_value，得到最新的net_value
                target_amount = 0  # 目标下单量
                order_amount = target_amount - position_amount  # 所需下单量 = 目标下单量 - 当前持仓量
                target_amount = float(f'{target_amount:.0f}')
                order_amount = float(f'{order_amount:.0f}')
                log_print(f'标的{symbol}所需下单量={order_amount}')
                # 下单并更新数据库
                if cta_usd_open_limit_order(exchange, symbol, order_amount,
                                            price_precision, last_price):
                    log_print(f'{cta_key}下单成功')
                    send_wechat(f'{cta_key}下单成功，signal = {signal}')
                    data = {
                        'signal': signal,
                        'signal_time': datetime.now(),
                        'close_price': last_price,
                        'net_value': net_value,
                        'profit': net_value - init_value,
                        'position_amount': target_amount,
                        'is_tpsl': 0,
                    }
                    log_print(f'交易信息{data}')
                    cta_usd_update_trade_info(cta_key, data)
                else:
                    log_print(f'{cta_key}下单失败，signal={signal}')
                    send_wechat(f'{cta_key}下单失败，signal={signal}')
                    return

        log_print(f'{cta_key} 执行成功\n')
        if pos_infer:
            log_print(f'{cta_key}信号定期校准结束')
        del symbol_data, df


def cta_usd_takeprofit_and_stoploss(*args):
    with scheduler.app.app_context():
        binance_list = args[0]
        cta_keys = cta_usd_get_all_need_tpsl_cta_keys()
        # 获取当前策略的移动止盈信息
        try:
            df = pd.read_csv(f'{dapi_path}/cta_usd_tpsl.csv')
        except:
            df = pd.DataFrame(
                columns=['symbol', 'cta_key', 'max_profit_ratio'])

        profit_list = []
        for cta_key in cta_keys:
            log_print(f'正在进行策略{cta_key}的止盈止损监测')
            trade_info = cta_usd_get_trade_info(cta_key)
            if trade_info is None:
                log_print(f'{cta_key}止盈止损执行出错，请排查')
                send_wechat(f'{cta_key}止盈止损执行出错，请排查')
                continue
            open_tpsl = trade_info['open_tpsl']
            if open_tpsl == 0:
                log_print(f'{cta_key}未开启止盈止损,无需止盈止损')
                continue
            signal = trade_info['signal']
            takeprofit_percentage = Decimal(
                trade_info['takeprofit_percentage'])
            cta_takeprofit_drawdown_percentage = Decimal(
                trade_info['takeprofit_drawdown_percentage'])
            stoploss_percentage = Decimal(trade_info['stoploss_percentage'])
            log_print(
                f'{cta_key}止盈比例为{takeprofit_percentage:.2f},止损比例为{stoploss_percentage:.2f}'
            )
            if signal == 0:
                log_print(f'{cta_key}未开仓,无需止盈止损')
                continue

            strategy_name = trade_info['strategy']
            exchange = get_exchange(binance_list, strategy_name)

            symbol = trade_info['symbol']
            pos_amount = Decimal(trade_info['position_amount'])
            open_price = trade_info['open_price']
            last_price = Decimal(
                fetch_binance_dapi_ticker_data(exchange, symbol))
            profit_ratio = Decimal(
                f'{signal * (last_price / open_price - 1):.4f}')

            profit_list.append([symbol, cta_key, profit_ratio])

            cta_stoploss_inside_bar = getattr(config,
                                              "cta_stoploss_inside_bar", True)
            # bar内止损检查
            condition_inside_bar = cta_stoploss_inside_bar or (
                datetime.now().timestamp() %
                int(pd.to_timedelta(trade_info['interval']).total_seconds()) <
                max(pd.to_timedelta(cta_tpsl_time).seconds, 30))

            # 止损条件
            condition_sl = condition_inside_bar and profit_ratio < 0 and abs(
                profit_ratio
            ) >= stoploss_percentage  # 如果当前盈利为负数，且大于触发百分比，币种进黑名单

            try:
                max_profit_ratio = Decimal(df[(df['symbol'] == symbol) & (
                    df['cta_key'] == cta_key)]['max_profit_ratio'].iloc[0])
            except:
                max_profit_ratio = None

            # 止盈条件
            if max_profit_ratio is None:
                condition_tp = False
            else:
                condition_tp = profit_ratio > 0 and max_profit_ratio > takeprofit_percentage and max_profit_ratio - profit_ratio >= cta_takeprofit_drawdown_percentage

            if float(pos_amount) > 0:
                direction = "做多"
                # log_print(
                #     f"{cta_key}持仓: {symbol}, {direction}, 量: {pos_amount:.2f}张, 盈亏: {round(profit_ratio, 4) * 100}%"
                # )
                if condition_sl:
                    t1 = cta_usd_tpsl_close_order(exchange, trade_info,
                                                  cta_key)
                    if t1:
                        log_print(
                            f'{cta_key} {direction}{symbol}已止损，亏损{round(profit_ratio, 4) * 100}%'
                        )
                        send_wechat(
                            f'{cta_key} {direction}{symbol}已止损，亏损{round(profit_ratio, 4) * 100}%'
                        )
                    else:
                        log_print(f'{cta_key} {direction}{symbol}止损失败，请排查')
                        send_wechat(f'{cta_key} {direction}{symbol}止损失败，请排查')
                if condition_tp:
                    t1 = cta_usd_tpsl_close_order(exchange, trade_info,
                                                  cta_key)
                    if t1:
                        log_print(
                            f'{cta_key} {direction}{symbol}已止盈，盈利{round(profit_ratio, 4) * 100}%'
                        )
                        send_wechat(
                            f'{cta_key} {direction}{symbol}已止盈，盈利{round(profit_ratio, 4) * 100}%'
                        )
                    else:
                        log_print(f'{cta_key} {direction}{symbol}止盈失败，请排查')
                        send_wechat(f'{cta_key} {direction}{symbol}止盈失败，请排查')

            if float(pos_amount) < 0:
                direction = "做空"
                # log_print(
                #     f"{cta_key}持仓: {symbol}, {direction}, 量: {pos_amount:.2f}张, 盈亏: {round(profit_ratio, 4) * 100}%"
                # )
                if condition_sl:
                    t1 = cta_usd_tpsl_close_order(exchange, trade_info,
                                                  cta_key)
                    if t1:
                        log_print(
                            f'{cta_key} {direction}{symbol}已止损，亏损{round(profit_ratio, 4) * 100}%'
                        )
                        send_wechat(
                            f'{cta_key} {direction}{symbol}已止损，亏损{round(profit_ratio, 4) * 100}%'
                        )
                    else:
                        log_print(f'{cta_key} {direction}{symbol}止损失败，请排查')
                        send_wechat(f'{cta_key} {direction}{symbol}止损失败，请排查')
                if condition_tp:
                    t1 = cta_usd_tpsl_close_order(exchange, trade_info,
                                                  cta_key)
                    if t1:
                        log_print(
                            f'{cta_key} {direction}{symbol}已止盈，盈利{round(profit_ratio, 4) * 100}%'
                        )
                        send_wechat(
                            f'{cta_key} {direction}{symbol}已止盈，盈利{round(profit_ratio, 4) * 100}%'
                        )
                    else:
                        log_print(f'{cta_key} {direction}{symbol}止盈失败，请排查')
                        send_wechat(f'{cta_key} {direction}{symbol}止盈失败，请排查')

            log_print(f'策略{cta_key}止盈止损监测完成')

        df = df.append(
            pd.DataFrame(profit_list,
                         columns=['symbol', 'cta_key', 'max_profit_ratio']))
        df = df[df['max_profit_ratio'] > 0]
        df.sort_values('max_profit_ratio', ascending=False, inplace=True)
        df.drop_duplicates(subset=['symbol', 'cta_key'],
                           keep='first',
                           inplace=True)
        df = df[df['cta_key'].isin(cta_keys)]
        df.to_csv(f'{dapi_path}/cta_usd_tpsl.csv', index=False)
        log_print(f'币本位CTA策略止盈止损监测完成')


def cta_usd_adl_handle(*args):
    for binance in args:
        exchange = binance['exchange']
        strategy = binance['strategy']
        account_info = exchange.dapiPrivate_get_account()
        positions = account_info['positions']
        positions = [p for p in positions if float(p['positionAmt']) != 0]
        if len(positions) == 0:
            continue
        price_precision = get_dapi_exchange_info(exchange)
        adl_list = exchange.dapiPrivate_get_adlquantile()
        for adl in adl_list:
            adl_level = int(adl['adlQuantile']['BOTH'])
            if adl_level < 4:
                continue
            # adl等级为4的进行处理
            symbol = adl['symbol']
            for p in positions:
                if p['symbol'] == symbol:
                    quantity = int(p['positionAmt'])
                    qty = abs(quantity) / 5  # 一次处理20%的ADL仓位
                    qty = round(qty)  # 下单数量取整
                    qty = max(1, qty)  # 至少处理1张

                    last_price = fetch_binance_dapi_ticker_data(
                        exchange, symbol)

                    # 持仓张数大于0，先sell后buy
                    if quantity > 0:
                        cta_usd_open_limit_order(exchange, symbol, -qty,
                                                 price_precision, last_price)
                        cta_usd_open_limit_order(exchange, symbol, qty,
                                                 price_precision, last_price)
                    # 持仓张数小于0，先buy后sell
                    else:
                        cta_usd_open_limit_order(exchange, symbol, qty,
                                                 price_precision, last_price)
                        cta_usd_open_limit_order(exchange, symbol, -qty,
                                                 price_precision, last_price)

                    log_print(f'{strategy} {symbol} ADL处理成功，处理{qty}张')
                    send_wechat(f'{strategy} {symbol} ADL处理成功，处理{qty}张')


def cta_usd_rebalance(*args):
    with scheduler.app.app_context():
        for binance in args:
            exchange = binance['exchange']
            strategy = binance['strategy']
            account = make_binance_account_adapter(
                exchange, binance.get('account_type', ACCOUNT_TYPE_STANDARD))
            cta_keys = cta_usd_rebalance_get_strategy_rebalance_cta_keys(
                strategy, running_only=True)
            if len(cta_keys) == 0:
                continue
            account_info = account.get_cm_account()
            assets = account_info['assets']
            if len(assets) == 0:
                continue

            assets = [s for s in assets if float(s['walletBalance']) > 0]
            positions = account_info['positions']
            # positions = [p for p in positions if float(p['positionAmt']) != 0]
            position_map = {}
            for p in positions:
                position_map[p['symbol']] = float(p['positionAmt'])

            price_precision = get_dapi_exchange_info(exchange)
            last_price = fetch_binance_dapi_ticker_data(exchange)

            data = get_dapi_public_exchange_info(exchange)
            _symbol_list = list(
                filter(
                    lambda s: s['contractStatus'] == 'TRADING' and s[
                        'contractType'] == 'PERPETUAL', data['symbols']))
            base_symbol = [
                x['baseAsset'] for x in _symbol_list
                if x['quoteAsset'] == "USD"
            ]

            for s in assets:
                if s['asset'] not in base_symbol:
                    continue

                symbol = f'{s["asset"]}USD_PERP'
                cta_key = cta_usd_rebalance_get_cta_key(strategy, symbol)
                if cta_key is None:
                    continue
                trade_info = cta_usd_rebalance_get_trade_info(cta_key)
                if trade_info is None:
                    log_print(f'{cta_key}半套执行出错，请排查')
                    send_wechat(f'{cta_key}半套执行出错，请排查')
                    continue

                margin_balance = float(s['marginBalance'])
                margin_balance_usd = float(
                    s['marginBalance']) * last_price[symbol]

                # 未初始化的情况下
                if trade_info['init_value'] == 0:
                    qty = margin_balance_usd / 10 if s['asset'] not in [
                        'BTC'
                    ] else margin_balance_usd / 100
                    qty *= float(trade_info['trade_ratio'])
                    qty = round(qty)  # 下单数量取整
                    need_order_amount = qty
                    if need_order_amount == 0:
                        log_print(f'{cta_key}初始化半套执行完成')
                        continue

                    if cta_usd_open_limit_order(exchange,
                                                symbol,
                                                -need_order_amount,
                                                price_precision,
                                                last_price[symbol],
                                                order_func=account.place_cm_order):
                        data = {
                            'init_value': margin_balance_usd,
                            'net_value': margin_balance_usd,
                            'position_amount': -qty,
                        }
                        cta_usd_rebalance_update_trade_info(cta_key, data)
                        log_print(f'{cta_key}初始化半套执行完成')
                    else:
                        log_print(f'{cta_key}初始化半套执行失败，请排查')
                        send_wechat(f'{cta_key}初始化半套执行失败，请排查')
                else:
                    # 净值新高才执行半套
                    if margin_balance_usd <= trade_info['net_value']:
                        log_print(f'{cta_key}半套执行完成')
                        continue
                    qty = margin_balance_usd / 10 if s['asset'] not in [
                        'BTC'
                    ] else margin_balance_usd / 100
                    # 净空不执行半套
                    if position_map.get(symbol, 0) / qty < -1:
                        log_print(f'{cta_key}半套执行完成')
                        continue
                    qty *= float(trade_info['trade_ratio'])
                    qty = round(qty)  # 下单数量取整
                    need_order_amount = qty - abs(
                        trade_info['position_amount'])
                    if need_order_amount == 0:
                        log_print(f'{cta_key}半套执行完成')
                        continue

                    if cta_usd_open_limit_order(exchange,
                                                symbol,
                                                -need_order_amount,
                                                price_precision,
                                                last_price[symbol],
                                                order_func=account.place_cm_order):
                        data = {
                            'net_value': margin_balance_usd,
                            'position_amount': -qty,
                        }
                        cta_usd_rebalance_update_trade_info(cta_key, data)
                        log_print(f'{cta_key}半套执行完成')
                    else:
                        log_print(f'{cta_key}半套执行失败，请排查')
                        send_wechat(f'{cta_key}半套执行失败，请排查')
