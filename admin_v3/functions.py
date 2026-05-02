from datetime import datetime, timedelta
import ccxt
from decimal import Decimal
from multiprocessing import Pool
from sqlalchemy import create_engine
from config import debug, amis_edit_origin, local_origin, proxy, sql_uri, wechat_hook_key, auto_add_re
from factors import *
import factors
from model import CtaUsdt, CtaUsd, CtaUsdRebalance, Strategy, LongBlackList, ShortBlackList
from exts import db
from binance_account import ACCOUNT_TYPE_STANDARD, make_binance_account_adapter
import time
import json
import pandas as pd
import numpy as np
import math
from warnings import simplefilter
import sys
import requests
import itertools

# 用于避免重复获取K线的变量
temp_df = None
temp_symbol = None
temp_interval = None
temp_cta = None
temp_period = None
temp_start_date = None

simplefilter(action='ignore', category=FutureWarning)
eps = 1e-8


# 重写log_print方法，加入时间信息
def log_print(*objects, sep=' ', end='\n', file=sys.stdout, flush=False):
    print('[%s]' % str(datetime.now()),
          *objects,
          sep=' ',
          end='\n',
          file=sys.stdout,
          flush=False)  # 这样每次调用log_print()的时候，会先输出当前时间，然后再输出内容


def robust(func, params={}, func_name='', retry_times=5, sleep_seconds=5):
    for _ in range(retry_times):
        try:
            return func(params=params)
        except Exception as e:
            import ccxt
            import json
            if isinstance(e, ccxt.ExchangeError):
                msg = str(e).replace('binance', '').strip()
                error_code = json.loads(msg)['code']
                # {'code': -2022, 'msg': 'ReduceOnly Order is rejected.'}
                if error_code in (-2022,):
                    raise RuntimeError(
                        'call ' + func_name + ' error!!! params: ', params,
                        'reason:', str(e))
            if _ == (retry_times - 1):
                raise RuntimeError('call ' + func_name + ' error!!! params: ',
                                   params, 'reason:', str(e))

            time.sleep(sleep_seconds)


def ccxt_public_call(exchange, method_names, params=None):
    for name in method_names:
        if hasattr(exchange, name):
            func = getattr(exchange, name)
            if params is None:
                return func()
            try:
                return func(params=params)
            except TypeError:
                return func(params)
    raise AttributeError(f'ccxt method not found: {method_names}')


def get_fapi_public_exchange_info(exchange):
    return ccxt_public_call(exchange,
                            ('fapiPublic_get_exchangeinfo',
                             'fapiPublicGetExchangeInfo'))


def get_dapi_public_exchange_info(exchange):
    return ccxt_public_call(exchange,
                            ('dapiPublic_get_exchangeinfo',
                             'dapiPublicGetExchangeInfo'))


def get_fapi_public_premium_index(exchange):
    return ccxt_public_call(exchange,
                            ('fapiPublic_get_premiumindex',
                             'fapiPublicGetPremiumIndex'))


def get_fapi_public_continuous_klines(exchange, params):
    return ccxt_public_call(exchange,
                            ('fapiPublic_get_continuousklines',
                             'fapiPublicGetContinuousKlines'), params)


def get_dapi_public_klines(exchange, params):
    return ccxt_public_call(exchange,
                            ('dapiPublic_get_klines', 'dapiPublicGetKlines'),
                            params)


def get_fapi_public_ticker_24hr(exchange, params=None):
    return ccxt_public_call(exchange,
                            ('fapiPublic_get_ticker_24hr',
                             'fapiPublicGetTicker24hr'), params)


def get_dapi_public_ticker_24hr(exchange, params=None):
    return ccxt_public_call(exchange,
                            ('dapiPublic_get_ticker_24hr',
                             'dapiPublicGetTicker24hr'), params)


# =====企业微信机器人推送消息
def send_wechat(message):
    if wechat_hook_key.strip() == '':
        print('未配置wechat_webhook_key，不发送信息')
        return
    try:
        data = {
            "msgtype": "text",
            "text": {
                "content": message + '\n' + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }
        r = requests.post(f'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={wechat_hook_key.strip()}',
                          data=json.dumps(data), timeout=10)
        print(f'调用企业微信接口返回： {r.text}')
        print('成功发送企业微信')
    except Exception as e:
        print(f"发送企业微信失败:{e}")
        print(traceback.format_exc())


def decorate_res(res):
    if debug:
        res.headers['Access-Control-Allow-Origin'] = amis_edit_origin
    else:
        res.headers['Access-Control-Allow-Origin'] = local_origin
    res.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    res.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    res.headers['Access-Control-Allow-Credentials'] = True
    return res


def add_account(data):
    try:
        strategy = data['strategy']
        account = data['account']
        apikey = data['apikey']
        secret = data['secret']
        account_type = data.get('account_type', ACCOUNT_TYPE_STANDARD)

        # 查询是否重复
        res = Strategy.query.filter(Strategy.account == account).first()

        if res is not None:
            return {
                'status': 0,
                'msg': f'账号{account}已经存在!'
            }
        item = Strategy(
            strategy=strategy,
            account=account,
            apikey=apikey,
            secret=secret,
            account_type=account_type,
        )
        db.session.add(item)
        db.session.commit()
        return {'status': 0, 'msg': f'账号{account}创建成功!'}
    except Exception as e:
        return {
            'status': 500,
            'msg': f'创建错误{e}'
        }


def get_account_list(binance_list):
    options = []
    for i in binance_list:
        op = {'label': i['strategy'], 'value': i['strategy']}
        options.append(op)

    def get_strategy_name(enum):
        return enum['value']

    options.sort(key=get_strategy_name)

    return {
        'status': 0,
        'msg': '',
        'data': {
            'options': options,
        }
    }


def get_exchange(binance_list, strategy):
    for i in binance_list:
        if strategy == i['strategy']:
            return i['exchange']


def get_exchange_account_type(binance_list, strategy):
    for i in binance_list:
        if strategy == i['strategy']:
            return i.get('account_type', ACCOUNT_TYPE_STANDARD)
    return ACCOUNT_TYPE_STANDARD


def get_strategy_account_type(strategy):
    st = Strategy.query.filter(Strategy.strategy == strategy).first()
    return getattr(st, 'account_type', ACCOUNT_TYPE_STANDARD) if st else ACCOUNT_TYPE_STANDARD


def get_main_exchange(binance_list):
    for i in binance_list:
        if i['is_main'] == 1:
            return i['exchange']


def get_default_exchange(binance_list):
    if len(binance_list) > 0:
        return binance_list[0]['exchange']
    else:
        return None


def get_strategy(binance_list, strategy):
    for i in binance_list:
        if strategy == i['strategy']:
            return i


def get_email(binance_list, strategy):
    for i in binance_list:
        if strategy == i['strategy']:
            return i['account']


def get_binance_list(st):
    binance_list = []
    for i in st:
        exchange = ccxt.binance({
            'apiKey': i.apikey,
            'secret': i.secret,
            'timeout': 30000,
            'rateLimit': 10,
            'enableRateLimit': False,
            'options': {
                'adjustForTimeDifference':
                    True,  # ←---- resolves the timestamp
                'recvWindow': 10000,
            },
        })
        exchange.proxies = proxy
        binance_list.append({
            'id': i.id,
            'strategy': i.strategy,
            'account': i.account,
            'trade_ratio': i.trade_ratio,
            'takeprofit_percentage': i.takeprofit_percentage,
            'stoploss_percentage': i.stoploss_percentage,
            'exchange': exchange,
            'is_main': i.is_main,
            'account_type': getattr(i, 'account_type', ACCOUNT_TYPE_STANDARD)
        })
    return binance_list


def get_deribit_list(duck):
    deribit_list = []
    for i in duck:
        exchange = ccxt.deribit({
            'apiKey': i.apikey,
            'secret': i.secret,
            'timeout': 30000,
            'rateLimit': 10,
            'enableRateLimit': False,
            'options': {
                'adjustForTimeDifference':
                    True,  # ←---- resolves the timestamp
                'recvWindow': 10000,
            },
        })
        exchange.proxies = proxy
        deribit_list.append({
            'id': i.id,
            'strategy': i.strategy,
            'account': i.account,
            'trade_ratio': i.trade_ratio,
            'takeprofit_percentage': i.takeprofit_percentage,
            'stoploss_percentage': i.stoploss_percentage,
            'exchange': exchange
        })
    return deribit_list


def replenish_bnb(exchange, balance, base_bnb=0, amount_t=10):
    def truncate(f, n):
        return math.floor(f * 10 ** n) / 10 ** n

    def get_spot_balance(exchange, asset):
        account = robust(exchange.private_get_account,
                         func_name='private_get_account')
        balance = account['balances']
        balance = pd.DataFrame(balance)
        # 如果子账号没有使用过现货账户，此处会返回空值
        if balance.empty:
            return 0.0

        amount = float(balance[balance['asset'] == asset]['free'])
        return amount

    coin = ['USDC', 'USDT']
    BNB_df = pd.DataFrame(balance['assets'])
    amount_bnb = float(
        BNB_df[BNB_df['asset'] == 'BNB']['walletBalance'].iloc[0])
    if amount_t == 0:
        return
    min_bnb = 0.001  # 该参数在BNB达到 10000 USDT之前有效
    spot_bnb = 0.03  # 现货bnb大于此数量,只转入此数量进入合约

    log_print(f"当前合约账户剩余{amount_bnb} BNB")
    spot_bnb_amount = get_spot_balance(exchange, 'BNB')
    if amount_bnb < base_bnb + min_bnb:
        log_print(f"当前现货账户持有{spot_bnb_amount} BNB")

        if spot_bnb_amount >= spot_bnb:
            post_account_management_transfer(exchange, 'BNB', 1,
                                             spot_bnb)  # type_1:spot2f
            # transfer_spot_to_future(exchange, 'BNB', spot_bnb)
            log_print(f"成功将现货{spot_bnb} BNB并转入U本位合约账户")

        elif min_bnb <= spot_bnb_amount <= spot_bnb:
            log_print(spot_bnb_amount)
            post_account_management_transfer(
                exchange, 'BNB', 1, float(truncate(spot_bnb_amount, 4)))
            # transfer_spot_to_future(exchange, 'BNB', float(truncate(spot_bnb_amount, 4)))
            log_print(
                f"成功将剩余现货{float(truncate(spot_bnb_amount, 4))} BNB并转入U本位合约账户")

        elif spot_bnb_amount < min_bnb:
            log_print("从现货市场买入10 USDT等值BNB并转入合约账户")
            for i in coin:
                spot_usdt_amount = get_spot_balance(exchange, i)
                amount_usd = float(
                    BNB_df[BNB_df['asset'] == i]['walletBalance'].iloc[0])
                log_print(f"当前合约账户持有{amount_usd}{i}")
                if amount_usd > 10.1:
                    if spot_usdt_amount < amount_t:
                        post_account_management_transfer(
                            exchange, i, 2,
                            amount_t - spot_usdt_amount)  # type_2:f2spot
                        # transfer_future_to_spot(exchange, i, amount_t - spot_usdt_amount)
                    buy_spot_coin(exchange, 'BNB', i, amount_t)
                    # spot_buy_quote(exchange, f'BNB{i}', amount_t)
                    time.sleep(2)
                    retry = 0
                    # 如果获取到现货账户BNB持仓扔小于最小BNB量，说明币安账户未更新，在行情剧烈波动的情况下存在这种情况
                    # 睡眠20秒后重新获取BNB现货账户余额，重试15次（5分钟）后仍未更新则放弃
                    while spot_bnb_amount < min_bnb and retry < 3:
                        spot_bnb_amount = get_spot_balance(exchange, 'BNB')
                        if spot_bnb_amount > min_bnb:
                            break
                        else:
                            retry += 1
                            time.sleep(3)

                    post_account_management_transfer(exchange, 'BNB', 1,
                                                     spot_bnb_amount)
                    # transfer_spot_to_future(exchange, 'BNB', spot_bnb_amount)
                    log_print(f"成功买入{spot_bnb_amount} BNB并转入U本位合约账户")
                    break
            else:
                log_print("BNB燃烧补充失败, 请检查现货或保证金余额")


def set_multiassetsmargin(exchange, target_status=True):
    try:
        exchange.fapiPrivate_post_multiassetsmargin(
            {'multiAssetsMargin': target_status})
        return {'status': 0, 'msg': f'联合保证金模式成功设置为:{target_status}'}
    except Exception as e:
        error = str(e)
        if '-4171' in error:
            return {'status': 0, 'msg': f'联合保证金模式已经为:{target_status},无法重复设置'}
        elif '-4169' in error:
            return {
                'status': -1,
                'msg': f'联合保证金模式无法设置为:{target_status},对应保证金资产不足'
            }
        else:
            return {'status': -1, 'msg': f'其他错误,2秒后重试,错误原因:{error}'}


def change_leverage(exchange, type, target_leverage):
    try:
        target_leverage = int(target_leverage)
        if type == 'fapi':
            position_risk = exchange.fapiPrivateV2_get_positionrisk()
        elif type == 'dapi':
            position_risk = eval(f'exchange.{type}Private_get_positionrisk()')
        leverage_info = dict([(row['symbol'], int(row['leverage']))
                              for row in position_risk])
        for symbol, leverage in leverage_info.items():
            if leverage != target_leverage:
                # 设置杠杆
                params = {'symbol': symbol, 'leverage': target_leverage}
                eval(f'exchange.{type}Private_post_leverage({params})')
        return {'status': 0, 'msg': f'杠杆成功调整为{target_leverage}'}
    except Exception as e:
        log_print(e)
        return {'status': -1, 'msg': f'调整账户杠杆失败 {e}'}


def change_positionside_dual(exchange, type):
    try:
        res = eval(f'exchange.{type}Private_get_positionside_dual()')
        log_print(res)
        if res['dualSidePosition']:
            params = {'dualSidePosition': False}
            res = eval(
                f'exchange.{type}Private_post_positionside_dual({params})')
            return {'status': 0, 'msg': '修改单向持仓模式成功'}
        else:
            return {'status': 0, 'msg': '本来已经是单向持仓模式'}
    except Exception as e:
        log_print(e)
        return {'status': -1, 'msg': f'修改单向持仓模式失败 {e}'}


def get_account_positions_list(exchange, account_type=ACCOUNT_TYPE_STANDARD):
    if exchange is None:
        return {'status': 0, 'msg': '', 'data': {'items': []}}
    account = make_binance_account_adapter(exchange, account_type)
    if account.is_unified:
        account_info = account.get_account_summary()
        positions = [
            p for p in account.get_um_position_risk()
            if Decimal(str(p.get('positionAmt') or '0')) != 0
        ]
        totalWalletBalance = Decimal(
            str(account_info.get('accountEquity')
                or account_info.get('totalWalletBalance') or '0'))
    else:
        account_info = account.get_account_summary()['raw']
        positions = [
            p for p in account_info['positions']
            if Decimal(str(p.get('positionInitialMargin') or '0')) > 0
        ]
        totalWalletBalance = Decimal(
            str(account_info['totalWalletBalance']))  # 钱包保证金余额

    items = []

    for pos in positions:
        symbol = pos['symbol']
        profit = Decimal(str(pos.get('unRealizedProfit')
                             or pos.get('unrealizedProfit') or '0'))
        position_amount = Decimal(str(pos['positionAmt']))
        entry_price = Decimal(str(pos.get('entryPrice') or '0'))
        position_usd = Decimal(str(pos.get('notional')
                                   or pos.get('notionalValue') or '0'))
        leverage_ratio = position_usd / totalWalletBalance if totalWalletBalance > 0 else 0

        # profit_ratio = ((margin + profit) / margin - 1) / leverage
        denominator = abs(position_usd - profit)
        profit_ratio = profit / denominator if denominator > 0 else 0
        side = 'SELL' if position_amount < 0 else 'BUY'

        item = {
            'symbol': symbol,
            'side': side,
            'entry_price': str(round(entry_price, 4)),
            'position_amount': str(round(position_amount, 3)),
            'position_usd': str(round(position_usd, 2)),
            'profit': str(round(profit, 2)),
            'profit_ratio': str(round(profit_ratio * 100, 2)) + '%',
            'leverage_ratio': str(abs(round(leverage_ratio * 100, 2))) + '%'
        }

        items.append(item)

    def get_side(enum):
        return enum['side'], -abs(float(enum['position_usd']))

    items.sort(key=get_side)

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def get_dapi_account_positions_list(exchange,
                                    account_type=ACCOUNT_TYPE_STANDARD):
    if exchange is None:
        return {'status': 0, 'msg': '', 'data': {'items': []}}
    last_price = fetch_binance_dapi_ticker_data(exchange)
    account = make_binance_account_adapter(exchange, account_type)
    account_info = account.get_cm_account()
    assets = account_info['assets']
    positions = account_info['positions']
    items = []
    for p in positions:
        if float(p['positionAmt']) == 0:
            continue
        item = {
            'symbol': p['symbol'],
            'leverage': float(p['leverage']),
            'entry_price': float(p['entryPrice']),
            'last_price': last_price[p['symbol']],
            'position_amount': float(p['positionAmt']),
        }
        items.append(item)

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def get_deribit_account_positions_list(exchange):
    if exchange is None:
        return {'status': 0, 'msg': '', 'data': {'items': []}}

    currencies = exchange.public_get_get_currencies()['result']
    sybmol_list = [i['currency'] for i in currencies]

    items = []
    df_list = []
    for symbol in sybmol_list:
        # 获取账户持仓
        params = {'currency': symbol}
        positions = exchange.private_get_get_positions(params)['result']
        temp_df = pd.DataFrame(positions, dtype=float)
        df_list.append(temp_df)

    df = pd.concat(df_list)
    df.fillna('nan', inplace=True)
    df.reset_index(drop=True, inplace=True)
    items = df.to_dict('records')

    def get_instrument_name(enum):
        return enum['instrument_name']

    items.sort(key=get_instrument_name)

    columns_item = []
    for column in df.columns:
        columns_item.append({'label': column, 'name': column})
    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'columns': columns_item,
            'total': len(items)
        }
    }


def get_account_balance(exchange, account_type=ACCOUNT_TYPE_STANDARD):
    if exchange is None:
        return {'status': 0, 'msg': '', 'data': {'items': []}}
    account = make_binance_account_adapter(exchange, account_type)
    if account.is_unified:
        account_info = account.get_account_summary()
        positions = [
            p for p in account.get_um_position_risk()
            if Decimal(str(p.get('positionAmt') or '0')) != 0
        ]
        totalWalletBalance = Decimal(
            str(account_info.get('accountEquity')
                or account_info.get('totalWalletBalance') or '0'))
        totalUnrealizedProfit = sum(
            Decimal(str(p.get('unRealizedProfit')
                        or p.get('unrealizedProfit') or '0'))
            for p in positions)
        totalMarginBalance = Decimal(
            str(account_info.get('accountEquity')
                or account_info.get('totalMarginBalance') or '0'))
    else:
        account_info = account.get_account_summary()['raw']
        positions = [
            p for p in account_info['positions']
            if Decimal(str(p.get('positionInitialMargin') or '0')) > 0
        ]
        totalWalletBalance = Decimal(
            str(account_info['totalWalletBalance']))  # 钱包保证金余额
        totalUnrealizedProfit = Decimal(
            str(account_info['totalUnrealizedProfit']))
        totalMarginBalance = Decimal(str(account_info['totalMarginBalance']))
    profit_ratio = totalUnrealizedProfit / totalWalletBalance if totalWalletBalance > 0 else 0

    buy_position = 0
    sell_position = 0

    for pos in positions:
        position_amount = Decimal(str(pos['positionAmt']))
        position_usd = Decimal(str(pos.get('notional')
                                   or pos.get('notionalValue') or '0'))
        if position_amount > 0:
            buy_position += position_usd
        else:
            sell_position += position_usd

    leverage_ratio = (buy_position + abs(sell_position)
                      ) / totalWalletBalance if totalWalletBalance > 0 else 0

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': [{
                'wallet_balance': str(round(totalWalletBalance, 2)),
                'net_value': str(round(totalMarginBalance, 2)),
                'unrealized_profit': str(round(totalUnrealizedProfit, 2)),
                'profit_ratio': str(round(profit_ratio * 100, 2)) + '%',
                'buy_position': str(round(buy_position, 2)),
                'sell_position': str(round(sell_position, 2)),
                'leverage_ratio': str(round(leverage_ratio, 2))
            }],
            'total':
                1
        }
    }


def get_account_margin(exchange, account_type=ACCOUNT_TYPE_STANDARD):
    if exchange is None:
        return {'status': 0, 'msg': '', 'data': {'items': []}}
    account = make_binance_account_adapter(exchange, account_type)
    assets = account.get_balance_assets()
    assets = [
        p for p in assets
        if Decimal(str(p.get('updateTime') or '0')) > 0
        or Decimal(str(p.get('marginBalance') or '0')) != 0
        or Decimal(str(p.get('walletBalance') or '0')) != 0
        or Decimal(str(p.get('totalWalletBalance') or '0')) != 0
        or Decimal(str(p.get('umWalletBalance') or '0')) != 0
    ]

    items = []
    for asset_dict in assets:
        asset = asset_dict['asset']
        walletBalance = Decimal(str(asset_dict.get('walletBalance') or '0'))
        if walletBalance == 0:
            walletBalance = Decimal(
                str(asset_dict.get('totalWalletBalance')
                    or asset_dict.get('umWalletBalance') or '0'))
        unrealizedProfit = Decimal(
            str(asset_dict.get('unrealizedProfit')
                or asset_dict.get('umUnrealizedPNL') or '0'))
        marginBalance = Decimal(str(asset_dict.get('marginBalance') or '0'))
        if marginBalance == 0:
            marginBalance = walletBalance + unrealizedProfit
        maxWithdrawAmount = Decimal(
            str(asset_dict.get('maxWithdrawAmount')
                or asset_dict.get('totalAvailableBalance') or '0'))
        items.append({
            'asset': asset,
            'walletBalance': walletBalance,
            'unrealizedProfit': unrealizedProfit,
            'marginBalance': marginBalance,
            'maxWithdrawAmount': maxWithdrawAmount
        })

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def get_spot_account_balance(exchange):
    spot_wallet_Balance = 0
    spot_account_info = exchange.private_get_account()
    spot_positions = {}
    for p in spot_account_info['balances']:
        token_num = float(p['free']) + float(p['locked'])
        if token_num > 0 and p['asset'] != 'USDT':
            spot_positions[p['asset']] = token_num
            symbol = p['asset'] + 'USDT'
            symbol_price = get_symbol_spot_price(exchange, symbol)
            net_value = float(spot_positions[p['asset']]) * float(
                symbol_price['price'])
            spot_wallet_Balance += net_value

        elif p['asset'] == 'USDT' and token_num != 0:
            spot_wallet_Balance += token_num
    return spot_wallet_Balance


def get_fapi_account_balance(exchange, account_type=ACCOUNT_TYPE_STANDARD):
    fapi_wallet_Balance = 0
    if account_type == 'unified':
        account = make_binance_account_adapter(exchange, account_type)
        for p in account.get_balance_assets():
            asset_value = float(p.get('umWalletBalance') or 0) + float(
                p.get('umUnrealizedPNL') or 0)
            if asset_value != 0.0 and p['asset'] != 'USDT':
                symbol = p['asset'] + 'USDT'
                symbol_price = get_symbol_spot_price(exchange, symbol)
                fapi_wallet_Balance += asset_value * float(
                    symbol_price['price'])
            elif asset_value != 0 and p['asset'] == 'USDT':
                fapi_wallet_Balance += asset_value
        return fapi_wallet_Balance

    fapi_account_info = exchange.fapiPrivateV2_get_account()
    fapi_positions = {}
    for p in fapi_account_info['assets']:
        fapi_positions[p['asset']] = float(p['walletBalance']) + float(
            p['unrealizedProfit'])
        if fapi_positions[p['asset']] != 0.0 and p['asset'] != 'USDT':
            symbol = p['asset'] + 'USDT'
            symbol_price = get_symbol_spot_price(exchange, symbol)
            net_value = float(fapi_positions[p['asset']]) * float(
                symbol_price['price'])
            fapi_wallet_Balance += net_value

        elif fapi_positions[p['asset']] != 0 and p['asset'] == 'USDT':
            net_value = float(fapi_positions[p['asset']])
            fapi_wallet_Balance += net_value
    return fapi_wallet_Balance


def get_dapi_total_account_balance(exchange, account_type=ACCOUNT_TYPE_STANDARD):
    dapi_wallet_Balance = 0
    account = make_binance_account_adapter(exchange, account_type)
    dapi_account_info = account.get_cm_account()
    dapi_positions = {}
    for p in dapi_account_info['assets']:
        dapi_positions[p['asset']] = float(p['walletBalance']) + float(
            p['unrealizedProfit'])
        if dapi_positions[p['asset']] != 0.0 and p['asset'] != 'USDT':
            symbol = p['asset'] + 'USDT'
            symbol_price = get_symbol_spot_price(exchange, symbol)
            net_value = float(dapi_positions[p['asset']]) * float(
                symbol_price['price'])
            dapi_wallet_Balance += net_value
    return dapi_wallet_Balance


def get_saving_account_balance(exchange):
    saving_wallet_Balance = 0
    # saving_account_info = exchange.sapi_get_lending_union_account()
    saving_positions = {}
    # saving_wallet_Balance = float(saving_account_info['totalAmountInUSDT'])
    # for p in saving_account_info['positionAmountVos']:
    #     saving_positions[p['asset']] = float(p['amount'])
    return saving_wallet_Balance


def get_fund_account_balance(exchange):
    fund_wallet_Balance = 0
    fund_account_info = exchange.sapi_post_asset_get_funding_asset()
    fund_positions = {}
    if fund_account_info != []:
        for p in fund_account_info:
            fund_positions[p['asset']] = float(p['free']) + float(p['locked'])
            if fund_positions[p['asset']] != 0.0 and p['asset'] != 'USDT':
                symbol = p['asset'] + 'USDT'
                symbol_price = get_symbol_spot_price(exchange, symbol)
                net_value = float(fund_positions[p['asset']]) * float(
                    symbol_price['price'])
                fund_wallet_Balance += net_value

            elif fund_positions[p['asset']] != 0 and p['asset'] == 'USDT':
                net_value = float(fund_positions[p['asset']])
                fund_wallet_Balance += net_value
    else:
        fund_wallet_Balance = 0
    return fund_wallet_Balance


def get_symbol_spot_price(exchange, symbol):
    params = {'symbol': symbol}
    for time in range(5):
        try:
            symbol_price = exchange.public_get_ticker_price(params=params)
            return symbol_price
        except Exception as e:
            if isinstance(e, ccxt.BadSymbol):
                msg = str(e).replace('binance', '').strip()
                error_code = json.loads(msg)['code']
                if error_code in (-1121,):
                    symbol_price = {'symbol': symbol, 'price': 0}
                    return symbol_price


def get_account_management_balance(binance_list):
    total_wallet_balance = 0
    total_fapi_wallet_balance = 0
    total_dapi_wallet_balance = 0
    total_spot_wallet_balance = 0
    total_fund_wallet_balance = 0
    total_saving_wallet_balance = 0

    sub_items = []
    items = []
    for binance in binance_list:
        exchange = binance['exchange']
        if exchange is None:
            return {'status': 0, 'msg': '', 'data': {'items': []}}

        account_type = binance.get('account_type', ACCOUNT_TYPE_STANDARD)
        fapi_wallet_balance = get_fapi_account_balance(exchange, account_type)
        dapi_wallet_balance = get_dapi_total_account_balance(exchange,
                                                             account_type)
        if account_type == 'unified':
            spot_wallet_balance = 0
            saving_wallet_balance = 0
            fund_wallet_balance = 0
            summary = make_binance_account_adapter(
                exchange, account_type).get_account_summary()
            account_total = float(summary.get('accountEquity', 0))
        else:
            spot_wallet_balance = get_spot_account_balance(exchange)
            saving_wallet_balance = get_saving_account_balance(exchange)
            fund_wallet_balance = get_fund_account_balance(exchange)
            account_total = fapi_wallet_balance + dapi_wallet_balance + spot_wallet_balance + fund_wallet_balance + saving_wallet_balance

        sub_items.append({
            'strategy_name': binance['strategy'],
            'account_total': str(round(account_total, 2)),
            'USD_M_account': str(round(fapi_wallet_balance, 2)),
            'Coin_M_account': str(round(dapi_wallet_balance, 2)),
            'spot_account': str(round(spot_wallet_balance, 2)),
            'fund_account': str(round(fund_wallet_balance, 2)),
            'saving_account': str(round(saving_wallet_balance, 2))
        })
        total_wallet_balance += account_total
        total_fapi_wallet_balance += fapi_wallet_balance
        total_dapi_wallet_balance += dapi_wallet_balance
        total_spot_wallet_balance += spot_wallet_balance
        total_fund_wallet_balance += fund_wallet_balance
        total_saving_wallet_balance += saving_wallet_balance

    items.append({
        'strategy_name': '账户汇总',
        'account_total': str(round(total_wallet_balance, 2)),
        'USD_M_account': str(round(total_fapi_wallet_balance, 2)),
        'Coin_M_account': str(round(total_dapi_wallet_balance, 2)),
        'spot_account': str(round(total_spot_wallet_balance, 2)),
        'fund_account': str(round(total_fund_wallet_balance, 2)),
        'saving_account': str(round(total_saving_wallet_balance, 2))
    })

    items.extend(sub_items)
    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def get_dapi_account_status(exchange, account_type=ACCOUNT_TYPE_STANDARD):
    if exchange is None:
        return {'status': 0, 'msg': '', 'data': {'items': []}}
    last_price = fetch_binance_dapi_ticker_data(exchange)
    account = make_binance_account_adapter(exchange, account_type)
    account_info = account.get_cm_account()
    assets = account_info['assets']
    positions = account_info['positions']
    items = []
    no_asset_items = []

    # cta
    cta_usdt_items = CtaUsd.query.filter(CtaUsd.is_del == 0).order_by(
        CtaUsd.symbol).all()
    if len(cta_usdt_items) == 0:
        return get_dapi_account_balance(exchange, account_type)
    cta_items = []
    for c in cta_usdt_items:
        cta_items.append(c.to_dict())
    df = pd.DataFrame(cta_items)
    cta_symbols = list(set(df["symbol"].to_list()))
    for cta_symbol in cta_symbols:
        df.loc[df['symbol'] == cta_symbol,
        'ticker_price'] = last_price.get(cta_symbol, None)
    df['un_profit'] = (
                              df['ticker_price'] - df['open_price'].astype(float)
                      ) / df['open_price'].astype(float) * df['position_amount'].astype(float)
    df['un_profit'].fillna(0, inplace=True)

    df_cta = df.groupby("symbol").agg({
        'net_value': 'sum',
        'position_amount': 'sum',
        'un_profit': 'sum',
    }).to_dict()

    # cta re
    cta_usdt_items = CtaUsdRebalance.query.filter(
        CtaUsdRebalance.is_del == 0).all()
    cta_items = []
    for c in cta_usdt_items:
        cta_items.append(c.to_dict())
    df_re = pd.DataFrame(cta_items)
    df_re.set_index("symbol", inplace=True)
    df_re = df_re.to_dict()

    position_map = {}
    for p in positions:
        if float(p['positionAmt']) == 0:
            continue
        position_map[p['symbol']] = float(p['positionAmt'])

    for s in assets:
        symbol = f'{s["asset"]}USD_PERP'
        position_by_symbol = position_map.get(symbol, 0)
        margin_balance_usd = float(s['marginBalance']) * last_price.get(
            symbol, 0)
        cta_realtime_position = float(
            df_cta.get('position_amount', {}).get(symbol, 0))
        cta_all_position = float(df_cta.get('net_value', {}).get(
            symbol, 0)) + float(df_cta.get('un_profit', {}).get(symbol, 0))

        cta_all_position_weight = cta_all_position * (
            10 if s["asset"] != 'BTC' else 100) / (margin_balance_usd + 1e-9)
        cta_all_position_difference_based_contract = round(
            cta_all_position - margin_balance_usd /
            (10 if s["asset"] != 'BTC' else 100), 2)
        cta_re_position = float(
            df_re.get('position_amount', {}).get(symbol, 0))
        cta_re_position_ratio = abs(cta_re_position) * (
            10 if s["asset"] != 'BTC' else 100) / (margin_balance_usd + 1e-9)

        item = {
            'asset':
                s['asset'],
            'margin_balance':
                round(float(s['marginBalance']), 5),
            'margin_balance_usd':
                margin_balance_usd,
            # 'wallet_balance':
            # float(s['walletBalance']),
            'position':
                position_by_symbol,
            'cta_position':
                cta_realtime_position,
            'cta_all_position_weight':
                cta_all_position_weight,
            'cta_diff_based_contract':
                cta_all_position_difference_based_contract,
            'cta_re_position':
                cta_re_position,
            'cta_re_position_ratio':
                round(float(cta_re_position_ratio), 4),
            'unrealized_profit':
                round(float(s['unrealizedProfit']), 5),
            'profit_ratio':
                round(float(s['unrealizedProfit']) / float(s['walletBalance']), 4)
                if float(s['walletBalance']) != 0 else 0
        }
        if float(s['marginBalance']) != 0:
            items.append(item)
        else:
            no_asset_items.append({
                'asset': s['asset'],
                'margin_balance': 0,
                'margin_balance_usd': 0,
                'position': 0,
                'cta_position': 0,
                'cta_all_position_weight': 0,
                'cta_diff_based_contract': 0,
                'cta_re_position': 0,
                'cta_re_position_ratio': 0,
                'unrealized_profit': 0,
                'profit_ratio': 0
            })

    items.sort(key=lambda x: x['asset'])
    items.extend(sorted(no_asset_items, key=lambda x: x['asset']))

    del df, df_cta, df_re, cta_usdt_items

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def get_dapi_account_balance(exchange, account_type=ACCOUNT_TYPE_STANDARD):
    if exchange is None:
        return {'status': 0, 'msg': '', 'data': {'items': []}}
    last_price = fetch_binance_dapi_ticker_data(exchange)
    account = make_binance_account_adapter(exchange, account_type)
    account_info = account.get_cm_account()
    assets = account_info['assets']
    positions = account_info['positions']
    items = []

    data = get_dapi_public_exchange_info(exchange)
    _symbol_list = list(
        filter(
            lambda s: s['contractStatus'] == 'TRADING' and s['contractType'] ==
                      'PERPETUAL', data['symbols']))
    base_symbol = [
        x['baseAsset'] for x in _symbol_list if x['quoteAsset'] == "USD"
    ]
    for s in assets:
        if s['asset'] not in base_symbol:
            continue
        # if float(s['marginBalance']) == 0:
        #     continue
        symbol = f'{s["asset"]}USD_PERP'
        item = {
            'asset':
                s['asset'],
            'margin_balance':
                float(s['marginBalance']),
            'margin_balance_usd':
                float(s['marginBalance']) * last_price[symbol],
            'wallet_balance':
                float(s['walletBalance']),
            'unrealized_profit':
                float(s['unrealizedProfit']),
            'profit_ratio':
                round(float(s['unrealizedProfit']) / float(s['walletBalance']), 4)
                if float(s['walletBalance']) != 0 else 0
        }
        items.append(item)

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def get_deribit_account_balance(exchange):
    if exchange is None:
        return {'status': 0, 'msg': '', 'data': {'items': []}}

    currencies = exchange.public_get_get_currencies()['result']
    sybmol_list = [i['currency'] for i in currencies]

    items = []
    for symbol in sybmol_list:
        # 获取最新价格
        params = {'index_name': f'{symbol.lower()}_usd'}
        index_price = float(
            exchange.public_get_get_index_price(params)['result']
            ['index_price'])

        # 获取账户保证金相关信息
        params = {'currency': symbol}
        summary = exchange.private_get_get_account_summary(params)['result']
        equity = float(summary['equity'])
        total_pl = float(summary['total_pl'])
        delta_total = float(summary['delta_total'])
        margin_balance = float(summary['margin_balance'])
        initial_margin = float(summary['initial_margin'])
        options_pl = float(summary['options_pl'])
        futures_pl = float(summary['futures_pl'])
        balance = float(summary['balance'])
        available_funds = float(summary['available_funds'])
        equity_usd = equity * index_price

        items.append({
            'symbol': symbol,
            'index_price': index_price,
            'equity': equity,
            'total_pl': total_pl,
            'delta_total': delta_total,
            'margin_balance': margin_balance,
            'initial_margin': initial_margin,
            'options_pl': options_pl,
            'futures_pl': futures_pl,
            'balance': balance,
            'available_funds': available_funds,
            'equity_usd': equity_usd,
        })

    def get_symbol(enum):
        return enum['symbol']

    items.sort(key=get_symbol)

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def post_account_management_uni_transfer(exchange, fromEmail, fromWallet,
                                         toEmail, toWallet, asset, amount):
    if exchange is None:
        return {'status': 0, 'msg': '交易所为空，请排查'}
    if float(amount) <= 0:
        return {'status': 500, 'msg': '划转数量非法'}
    if fromEmail == None and toEmail == None:
        return {'status': 0, 'msg': '账户邮箱存在问题，请排查是否正确'}
    if fromWallet != 'SPOT' and toWallet != 'SPOT':
        return {'status': -1, 'msg': '不支持此类型划转'}

    params = {
        'fromEmail': fromEmail,
        'fromAccountType': fromWallet,
        'toEmail': toEmail,
        'toAccountType': toWallet,
        'asset': asset,
        'amount': Decimal(amount)
    }
    log_print(
        f'fromEmail: {fromEmail}, fromAccountType: {fromWallet}, toEmail: {toEmail}, toAccountType: {toWallet}, asset: {asset}, amount: {amount}'
    )
    try:
        res = exchange.sapiPostSubAccountUniversalTransfer(params=params)
        log_print(f'划转结果为 {res}')
    except Exception as e:
        log_print(f'{e}')
        return {'status': -1, 'msg': f'{e}'}
    return {'status': 0, 'msg': '划转成功'}


def post_account_management_transfer(exchange, asset, type, amount):
    if exchange is None:
        return {'status': 0, 'msg': '交易所为空，请排查'}
    if float(amount) <= 0:
        return {'status': 500, 'msg': '划转数量非法'}

    params = {'asset': asset, 'type': int(type), 'amount': Decimal(amount)}
    log_print(f'asset: {asset}, amount: {amount}')
    try:
        res = exchange.sapi_post_futures_transfer(params)
        log_print(f'划转结果为 {res}')
    except Exception as e:
        log_print(f'{e}')
        return {'status': -1, 'msg': f'{e}'}
    return {'status': 0, 'msg': '划转成功'}


def get_account_management_uni_transfer_history(exchange):
    if exchange is None:
        return {'status': 0, 'msg': '', 'data': {'items': []}}
    transfer_info = exchange.sapiGetSubAccountUniversalTransfer()

    items = []
    for record in transfer_info['result']:
        _createTimeStamp = time.localtime(
            int(record['createTimeStamp']) / 1000)
        createTimeStamp = time.strftime("%Y-%m-%d %H:%M:%S", _createTimeStamp)

        item = {
            'fromEmail': record['fromEmail'],
            'fromAccountType': record['fromAccountType'],
            'toEmail': record['toEmail'],
            'toAccountType': record['toAccountType'],
            'asset': record['asset'],
            'amount': record['amount'],
            'createTimeStamp': createTimeStamp
        }
        items.append(item)

    def get_time(enum):
        return enum['createTimeStamp']

    items.sort(key=get_time, reverse=True)
    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def get_fapi_fundingrate(exchange):
    data = get_fapi_public_premium_index(exchange)
    items = []

    for s in data:
        symbol = s['symbol']
        mark_price = Decimal(s['markPrice'])
        funding_rate = float(s['lastFundingRate'])
        next_funding_time = int(s['nextFundingTime']) / 1000

        item = {
            'symbol': symbol,
            'mark_price': round(mark_price, 4),
            'funding_rate': round(funding_rate, 6),
            'next_funding_time': next_funding_time
        }

        items.append(item)

    def get_rate(enum):
        return enum['funding_rate']

    items.sort(key=get_rate, reverse=True)

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def strategy_get_row(strategy):
    try:
        st = Strategy.query.filter(Strategy.strategy == strategy).first()
        return {
            'status': 0,
            'msg': '',
            'data': {
                'id': st.id,
                'strategy': st.strategy,
                'account': st.account,
                'account_type': getattr(st, 'account_type',
                                        ACCOUNT_TYPE_STANDARD),
                'trade_ratio': st.trade_ratio,
                'takeprofit_percentage': st.takeprofit_percentage,
                'stoploss_percentage': st.stoploss_percentage,
            }
        }
    except Exception as e:
        log_print(e)
        send_wechat(f'获取策略信息失败:{str(e)}')
        return {'status': 500, 'msg': '获取策略信息失败', 'data': {}}


def strategy_update_params(data):
    st = Strategy.query.filter(Strategy.strategy == data['strategy']).first()
    st.strategy = data['strategy']
    st.account = data['account']
    st.account_type = data.get('account_type', ACCOUNT_TYPE_STANDARD)
    st.trade_ratio = data['trade_ratio']
    st.takeprofit_percentage = data['takeprofit_percentage']
    st.stoploss_percentage = data['stoploss_percentage']
    db.session.commit()


def get_taker_by_ratio(exchange):
    exchange_info = get_fapi_public_exchange_info(exchange)
    _symbol_list = [
        x['symbol'] for x in exchange_info['symbols']
        if x['status'] == 'TRADING'
    ]
    symbol_list = [
        symbol for symbol in _symbol_list if symbol.endswith('USDT')
    ]

    _temp_list = []
    for symbol in symbol_list:
        if symbol in ['COCOSUSDT', 'BTCSTUSDT', 'DREPUSDT', 'SUNUSDT']:
            continue
        if symbol.endswith(('DOWNUSDT', 'UPUSDT', 'BULLUSDT', 'BEARUSDT')):
            continue
        _temp_list.append(symbol)
    symbol_list = _temp_list

    # arg_list = [(exchange, symbol, '1h', 24) for symbol in symbol_list]

    # with Pool(processes=2) as pl:
    #     # 利用starmap启用多进程信息
    #     items = pl.starmap(get_kline_for_taker_by_ratio, arg_list)

    items = []
    for symbol in symbol_list:
        item = get_kline_for_taker_by_ratio(exchange, symbol, '1h', 24)
        items.append(item)

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def get_bbw_for_all(exchange, interval='1d'):
    if interval == '':
        return {'status': 0, 'msg': '', 'data': {'items': []}}
    exchange_info = get_fapi_public_exchange_info(exchange)
    _symbol_list = list(
        filter(
            lambda s: s['status'] == 'TRADING' and s['contractType'] ==
                      'PERPETUAL', exchange_info['symbols']))
    symbol_list = [
        x['symbol'] for x in _symbol_list if x['quoteAsset'] == "USDT"
    ]
    # base_symbol = [
    #     x['baseAsset'] for x in _symbol_list if x['quoteAsset'] == "USDT"
    # ]
    # symbol_list.extend([
    #     x['symbol'] for x in _symbol_list
    #     if x['quoteAsset'] == "BUSD" and x['baseAsset'] not in base_symbol
    # ])

    _temp_list = []
    for symbol in symbol_list:
        if symbol in [
            'USDCUSDT', 'COCOSUSDT', 'BTCSTUSDT', 'DREPUSDT', 'SUNUSDT'
        ]:
            continue
        if symbol.endswith(('DOWNUSDT', 'UPUSDT', 'BULLUSDT', 'BEARUSDT')):
            continue
        _temp_list.append(symbol)
    symbol_list = _temp_list

    # arg_list = [(exchange, symbol, interval, 1000) for symbol in symbol_list]

    # with Pool(processes=2) as pl:
    #     # 利用starmap启用多进程信息
    #     items = pl.starmap(get_kline_for_bbw_all, arg_list)
    items = []
    for symbol in symbol_list:
        item = get_kline_for_bbw_all(exchange, symbol, interval, 1000)
        items.append(item)

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def get_kline_for_taker_by_ratio(exchange, symbol, interval, backhour):
    # params = {'symbol': symbol, 'interval': interval, 'limit': backhour}
    # # ===call KLine API
    # kline = exchange.fapiPublic_get_klines(params)
    params = {
        'pair': symbol,
        'contractType': 'PERPETUAL',
        'interval': interval,
        'limit': backhour
    }
    # ===call KLine API
    kline = get_fapi_public_continuous_klines(exchange, params)

    # 将数据转换为DataFrame
    columns = [
        'candle_begin_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trade_num',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ]
    df = pd.DataFrame(kline, columns=columns, dtype='float')

    # 兼容时区
    utc_offset = int(time.localtime().tm_gmtoff / 60 / 60)
    # 整理数据
    df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'],
                                             unit='ms') + pd.Timedelta(
        hours=utc_offset)  # 时间转化为东八区
    df['symbol'] = symbol  # 添加symbol列
    columns = [
        'symbol',
        'candle_begin_time',
        'open',
        'high',
        'low',
        'close',
        'volume',
        'quote_volume',
        'trade_num',
        'taker_buy_base_asset_volume',
        'taker_buy_quote_asset_volume',
    ]
    df = df[columns]

    df.sort_values(by=['candle_begin_time'], inplace=True)
    df.drop_duplicates(subset=['candle_begin_time'], keep='last', inplace=True)
    df.reset_index(drop=True, inplace=True)

    volume = df['quote_volume'].sum()
    buy_volume = df['taker_buy_quote_asset_volume'].sum()
    taker_by_ratio = buy_volume / (volume + 1e-8)
    close = df.iloc[-1]['close']

    item = {
        'symbol': symbol,
        'close': close,
        'taker_by_ratio': round(taker_by_ratio, 4)
    }

    return item


def get_kline_for_bbw_all(exchange, symbol, interval, backhour):
    # params = {'symbol': symbol, 'interval': interval, 'limit': backhour}
    # # ===call KLine API
    # kline = exchange.fapiPublic_get_klines(params)
    params = {
        'pair': symbol,
        'contractType': 'PERPETUAL',
        'interval': interval,
        'limit': backhour
    }
    # ===call KLine API
    kline = get_fapi_public_continuous_klines(exchange, params)
    # 将数据转换为DataFrame
    columns = [
        'candle_begin_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trade_num',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ]
    df = pd.DataFrame(kline, columns=columns, dtype='float')

    # 兼容时区
    utc_offset = int(time.localtime().tm_gmtoff / 60 / 60)
    # 整理数据
    df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'],
                                             unit='ms') + pd.Timedelta(
        hours=utc_offset)  # 时间转化为东八区
    df['symbol'] = symbol  # 添加symbol列
    columns = [
        'symbol',
        'candle_begin_time',
        'open',
        'high',
        'low',
        'close',
        'volume',
        'quote_volume',
        'trade_num',
        'taker_buy_base_asset_volume',
        'taker_buy_quote_asset_volume',
    ]
    df = df[columns]

    df.sort_values(by=['candle_begin_time'], inplace=True)
    df.drop_duplicates(subset=['candle_begin_time'], keep='last', inplace=True)
    df.reset_index(drop=True, inplace=True)

    df['median'] = df['close'].rolling(20, min_periods=1).mean()
    df['std'] = df['close'].rolling(20, min_periods=1).std(ddof=0)
    df['upper'] = df['median'] + df['std'] * 2
    df['lower'] = df['median'] - df['std'] * 2
    df['bbw'] = (df['upper'] - df['lower']) / df['median']
    df['bbw_pct_change_1d'] = df['bbw'].pct_change(1)
    df['bbw_pct_change_1w'] = df['bbw'].pct_change(7)

    if len(df) <= 20:
        item = {
            'symbol': symbol,
        }
        return item
    df = df.iloc[20:]

    # volume = df['quote_volume'].sum()
    # buy_volume = df['taker_buy_quote_asset_volume'].sum()
    # taker_by_ratio = buy_volume / (volume + 1e-8)
    close = df.iloc[-1]['close']
    bbw = round(df.iloc[-1]['bbw'], 8)
    df['bbw_max'] = df['bbw'].max()
    df['bbw_min'] = df['bbw'].min()
    df['bbw_median'] = df['bbw'].mean()

    df['bbw_std'] = df['bbw'].rolling(20, min_periods=1).std(ddof=0)
    df['bbw_zscore'] = (df['bbw'] - df['bbw_median']) / df['bbw_std']

    bbw_std = round(df.iloc[-1]['bbw_std'], 8)
    bbw_zscore = round(df.iloc[-1]['bbw_zscore'], 8)
    bbw_max = round(df.iloc[-1]['bbw_max'], 8)
    bbw_min = round(df.iloc[-1]['bbw_min'], 8)
    bbw_median = round(df.iloc[-1]['bbw_median'], 8)
    bbw_percentage = (bbw - bbw_min) / (bbw_max - bbw_min + eps)
    bbw_median_percentage = (bbw - bbw_median) / (bbw_median + eps)
    bbw_pct_change_1d = df.iloc[-1]['bbw_pct_change_1d']
    bbw_pct_change_1w = df.iloc[-1]['bbw_pct_change_1w']

    bbw_up_days_list = [
        len(list(v)) for k, v in itertools.groupby(
            np.where(df['bbw_pct_change_1d'] > 0, 1, np.nan))
    ]
    bbw_down_days_list = [
        len(list(v)) for k, v in itertools.groupby(
            np.where(df['bbw_pct_change_1d'] < 0, 1, np.nan))
    ]
    max_bbw_up_days = max(bbw_up_days_list)
    recent_bbw_up_days = bbw_up_days_list[-1]
    max_bbw_down_days = max(bbw_down_days_list)
    recent_bbw_down_days = bbw_down_days_list[-1]

    item = {
        'symbol': symbol,
        'close': close,
        'bbw_max': round(bbw_max, 4),
        'bbw_min': round(bbw_min, 4),
        'bbw_median': round(bbw_median, 4),
        'bbw_percentage': round(bbw_percentage, 4),
        'bbw_median_percentage': round(bbw_median_percentage, 4),
        'bbw_pct_change_1d': round(bbw_pct_change_1d, 4),
        'bbw_pct_change_1w': round(bbw_pct_change_1w, 4),
        'max_bbw_up_days': max_bbw_up_days,
        'max_bbw_down_days': max_bbw_down_days,
        'recent_bbw_up_days': recent_bbw_up_days,
        'recent_bbw_down_days': recent_bbw_down_days,
        'bbw': round(bbw, 4),
        'bbw_std': round(bbw_std, 4),
        'bbw_zscore': round(bbw_zscore, 4)
    }

    return item


def get_kline(exchange, symbol, interval, backhour, start_date=None):
    time_interval = interval
    symbol_data = []
    earliest = None
    use_date = False

    if backhour < 100:
        # params = {'symbol': symbol, 'interval': interval, 'limit': backhour}
        # # ===call KLine API
        # symbol_data = exchange.fapiPublic_get_klines(params)
        params = {
            'pair': symbol,
            'contractType': 'PERPETUAL',
            'interval': interval,
            'limit': backhour
        }
        # ===call KLine API
        symbol_data = get_fapi_public_continuous_klines(exchange, params)
    else:
        if time_interval.find('m') >= 0:
            data_timedelta = timedelta(
                minutes=int(time_interval.split('m')[0]))
            start = datetime.now() - backhour * data_timedelta
            if start_date:
                start = start_date
                use_date = True
        elif time_interval.find('h') >= 0:
            data_timedelta = timedelta(hours=int(time_interval.split('h')[0]))
            start = datetime.now() - backhour * data_timedelta
            if start_date:
                start = start_date
                use_date = True
        else:
            # params = {'symbol': symbol, 'interval': interval, 'limit': 1500}
            # # ===call KLine API
            # symbol_data = exchange.fapiPublic_get_klines(params)
            params = {
                'pair': symbol,
                'contractType': 'PERPETUAL',
                'interval': interval,
                'limit': 1500
            }
            # ===call KLine API
            symbol_data = get_fapi_public_continuous_klines(exchange, params)

    def _get_data(end, max_len=1000):
        nonlocal symbol_data, start, earliest, time_interval

        # temp_data = exchange.fapiPublic_get_klines({
        #     'symbol': symbol,
        #     'interval': time_interval,
        #     'endTime': end,
        #     'limit': max_len
        # })
        params = {
            'pair': symbol,
            'contractType': 'PERPETUAL',
            'interval': time_interval,
            'endTime': end,
            'limit': max_len
        }
        # ===call KLine API
        temp_data = get_fapi_public_continuous_klines(exchange, params)
        # temp_data = exchange.dapiPublic_get_klines(params={'symbol': symbol, 'interval': time_interval, 'endTime': end,'limit': max_len})
        # symbol=symbol, interval=time_interval, endTime=end,
        #                                    limit=max_len)
        if len(temp_data) == 0:  # 获取数据的异常处理
            time.sleep(1)
            return _get_data(end, max_len=max_len)
        symbol_data = temp_data + symbol_data
        temp_time = pd.to_datetime(temp_data[0][0],
                                   unit='ms') + pd.DateOffset(hours=8)
        log_print(symbol, time_interval, '当前获取到', temp_time)
        if (temp_time < start or temp_time == earliest):
            log_print(symbol, time_interval, '初始化数据完成')
        else:
            earliest = temp_time
            # time.sleep(0.2)  # 一秒拿5000根，权重不超过1500
            _get_data(temp_data[0][0], max_len=max_len)

    if len(symbol_data) == 0:
        _get_data(int(round(time.time() * 1000)), max_len=1000)

    # params = {'symbol': symbol, 'interval': interval, 'limit': backhour}

    # # ===call KLine API
    # kline = exchange.fapiPublic_get_klines(params)
    # 将数据转换为DataFrame
    columns = [
        'candle_begin_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trade_num',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ]
    df = pd.DataFrame(symbol_data, columns=columns, dtype='float')

    # 兼容时区
    utc_offset = int(time.localtime().tm_gmtoff / 60 / 60)
    # 整理数据
    df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'],
                                             unit='ms') + pd.Timedelta(
        hours=utc_offset)  # 时间转化为东八区
    df['symbol'] = symbol  # 添加symbol列
    columns = [
        'symbol',
        'candle_begin_time',
        'open',
        'high',
        'low',
        'close',
        'volume',
        'quote_volume',
        'trade_num',
        'taker_buy_base_asset_volume',
        'taker_buy_quote_asset_volume',
    ]
    df = df[columns]

    df.sort_values(by=['candle_begin_time'], inplace=True)
    df.drop_duplicates(subset=['candle_begin_time'], keep='last', inplace=True)
    if use_date:
        df = df[df['candle_begin_time'] >= start_date]
    else:
        df = df.iloc[-backhour - 1:]
    df.reset_index(drop=True, inplace=True)

    return df


def dapi_get_kline(exchange, symbol, interval, backhour, start_date=None):
    time_interval = interval
    symbol_data = []
    earliest = None
    use_date = False

    if backhour < 100:
        params = {'symbol': symbol, 'interval': interval, 'limit': backhour}
        # ===call KLine API
        symbol_data = get_dapi_public_klines(exchange, params)
    else:
        if time_interval.find('m') >= 0:
            data_timedelta = timedelta(
                minutes=int(time_interval.split('m')[0]))
            start = datetime.now() - backhour * data_timedelta
            if start_date:
                start = start_date
                use_date = True
        elif time_interval.find('h') >= 0:
            data_timedelta = timedelta(hours=int(time_interval.split('h')[0]))
            start = datetime.now() - backhour * data_timedelta
            if start_date:
                start = start_date
                use_date = True
        else:
            params = {'symbol': symbol, 'interval': interval, 'limit': 1500}
            # ===call KLine API
            symbol_data = get_dapi_public_klines(exchange, params)

    def _get_data(end, max_len=1000):
        nonlocal symbol_data, start, earliest, time_interval

        temp_data = get_dapi_public_klines(exchange, {
            'symbol': symbol,
            'interval': time_interval,
            'endTime': end,
            'limit': max_len
        })
        # temp_data = exchange.dapiPublic_get_klines(params={'symbol': symbol, 'interval': time_interval, 'endTime': end,'limit': max_len})
        # symbol=symbol, interval=time_interval, endTime=end,
        #                                    limit=max_len)
        if len(temp_data) == 0:  # 获取数据的异常处理
            time.sleep(1)
            return _get_data(end, max_len=max_len)
        symbol_data = temp_data + symbol_data
        temp_time = pd.to_datetime(temp_data[0][0],
                                   unit='ms') + pd.DateOffset(hours=8)
        log_print(symbol, time_interval, '当前获取到', temp_time)
        if (temp_time < start or temp_time == earliest):
            log_print(symbol, time_interval, '初始化数据完成')
        else:
            earliest = temp_time
            # time.sleep(0.2)  # 一秒拿5000根，权重不超过1500
            _get_data(temp_data[0][0], max_len=max_len)

    if len(symbol_data) == 0:
        _get_data(int(round(time.time() * 1000)), max_len=1000)

    # params = {'symbol': symbol, 'interval': interval, 'limit': backhour}

    # # ===call KLine API
    # kline = exchange.fapiPublic_get_klines(params)
    # 将数据转换为DataFrame
    columns = [
        'candle_begin_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trade_num',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ]
    df = pd.DataFrame(symbol_data, columns=columns, dtype='float')

    # 兼容时区
    utc_offset = int(time.localtime().tm_gmtoff / 60 / 60)
    # 整理数据
    df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'],
                                             unit='ms') + pd.Timedelta(
        hours=utc_offset)  # 时间转化为东八区
    df['symbol'] = symbol  # 添加symbol列
    columns = [
        'symbol',
        'candle_begin_time',
        'open',
        'high',
        'low',
        'close',
        'volume',
        'quote_volume',
        'trade_num',
        'taker_buy_base_asset_volume',
        'taker_buy_quote_asset_volume',
    ]
    df = df[columns]

    df.sort_values(by=['candle_begin_time'], inplace=True)
    df.drop_duplicates(subset=['candle_begin_time'], keep='last', inplace=True)
    if use_date:
        df = df[df['candle_begin_time'] >= start_date]
    else:
        df = df.iloc[-backhour - 1:]
    df.reset_index(drop=True, inplace=True)

    return df


def long_backlist_list(strategy):
    now = datetime.now()
    long_bl = LongBlackList.query.filter(
        LongBlackList.strategy == strategy, LongBlackList.is_del == 0,
        LongBlackList.release_time >= now).all()

    items = []
    for i in long_bl:
        item = {
            'id': i.id,
            'symbol': i.symbol,
            'release_time': datetime.timestamp(i.release_time)
        }
        items.append(item)

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def long_backlist_create(strategy, data):
    try:
        symbol = data['symbol']
        ts = int(data['release_time'])
        release_time = datetime.fromtimestamp(ts)

        item = LongBlackList(strategy=strategy,
                             symbol=symbol,
                             release_time=release_time)
        db.session.add(item)
        db.session.commit()
        return {'status': 0, 'msg': ''}
    except Exception as e:
        log_print(e)
        return {'status': 500, 'msg': str(e)}


def long_backlist_update(data):
    id = data['id']
    symbol = data['symbol']
    ts = int(data['release_time'])
    release_time = datetime.fromtimestamp(ts)
    item = LongBlackList.query.get(id)
    item.symbol = symbol
    item.release_time = release_time
    db.session.commit()


def long_backlist_delete(id):
    item = LongBlackList.query.get(id)
    item.is_del = 1
    db.session.commit()


def short_backlist_list(strategy):
    now = datetime.now()
    short_bl = ShortBlackList.query.filter(
        ShortBlackList.strategy == strategy, ShortBlackList.is_del == 0,
        ShortBlackList.release_time >= now).all()

    items = []
    for i in short_bl:
        item = {
            'id': i.id,
            'symbol': i.symbol,
            'release_time': datetime.timestamp(i.release_time)
        }
        items.append(item)

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def short_backlist_create(strategy, data):
    try:
        symbol = data['symbol']
        ts = int(data['release_time'])
        release_time = datetime.fromtimestamp(ts)

        item = ShortBlackList(strategy=strategy,
                              symbol=symbol,
                              release_time=release_time)
        db.session.add(item)
        db.session.commit()
        return {'status': 0, 'msg': ''}
    except Exception as e:
        log_print(e)
        return {'status': 500, 'msg': str(e)}


def short_backlist_update(data):
    id = data['id']
    symbol = data['symbol']
    ts = int(data['release_time'])
    release_time = datetime.fromtimestamp(ts)
    item = ShortBlackList.query.get(id)
    item.symbol = symbol
    item.release_time = release_time
    db.session.commit()


def short_backlist_delete(id):
    item = ShortBlackList.query.get(id)
    item.is_del = 1
    db.session.commit()


def close_order(exchange, symbol):
    if exchange is None or symbol is None:
        return {
            'status': 500,
            'msg': 'params error',
        }

    twap_amount = 1000  # 默认500刀以上触发拆单
    min_qty, price_precision = get_exchange_info(exchange)
    last_price = fetch_binance_ticker_data(exchange, symbol)

    account_info = exchange.fapiPrivateV2_get_account()
    positions = [
        p for p in account_info['positions']
        if Decimal(p['positionInitialMargin']) > 0
    ]

    for pos in positions:
        if pos['symbol'] != symbol:
            continue
        position_side = pos['positionSide']
        position_amount = float(pos['positionAmt'])
        side = 'BUY' if position_amount < 0 else 'SELL'
        notional = abs(float(pos['notional']))

    # 计算下单方向、价格
    if side == 'BUY':
        price = last_price * 1.03
    else:
        price = last_price * 0.97

    # 对下单价格这种最小下单精度
    price = float(f'{price:.{price_precision[symbol]}f}')

    log_print(f'{symbol} 需要平仓金额 {notional}')
    position_amount = abs(position_amount)

    twap_order_num = math.floor(notional / twap_amount)
    for i in range(0, twap_order_num):
        log_print(f'{symbol} twap下单，正在进行第 {i + 1} 次下单')
        quantity = twap_amount / last_price
        quantity = float(f'{quantity:.{min_qty[symbol]}f}')
        log_print(f'本次下单量 = {quantity}')

        # # 下单参数
        # params = {
        #     'symbol': symbol,
        #     'side': side,
        #     'type': 'LIMIT',
        #     'price': price,
        #     'quantity': quantity,
        #     'clientOrderId': str(time.time()),
        #     'timeInForce': 'GTC',
        #     'reduceOnly': True
        # }

        # 市价单下单参数
        params = {
            'symbol': symbol,
            'side': side,
            'type': 'MARKET',
            'quantity': quantity,
            'clientOrderId': str(time.time()),
            'reduceOnly': True
        }
        # 下单
        log_print('下单参数：', params)

        try:
            # open_order = exchange.fapiPrivate_post_order(params=params)
            open_order = robust(func=exchange.fapiPrivate_post_order,
                                params=params,
                                func_name='close_order')
            log_print('下单完成，下单信息：', open_order, '\n')
        except Exception as e:
            log_print('下单出错')
            log_print(e)
            return {'status': 500, 'msg': str(e)}

        position_amount -= quantity
        position_amount = float(f'{position_amount:.{min_qty[symbol]}f}')
        log_print(f'剩余下单量 = {position_amount}')
        time.sleep(2)

    position_amount = float(f'{position_amount:.{min_qty[symbol]}f}')
    log_print(f'残单处理，残单量 = {position_amount}')

    if position_amount == 0:
        return {
            'status': 0,
            'msg': '平仓成功',
        }

    # # 下单参数
    # params = {
    #     'symbol': symbol,
    #     'side': side,
    #     'type': 'LIMIT',
    #     'price': price,
    #     'quantity': position_amount,
    #     'clientOrderId': str(time.time()),
    #     'timeInForce': 'GTC',
    #     'reduceOnly': True
    # }

    # 市价单下单参数
    params = {
        'symbol': symbol,
        'side': side,
        'type': 'MARKET',
        'quantity': position_amount,
        'clientOrderId': str(time.time()),
        'reduceOnly': True
    }
    # 下单
    log_print('下单参数：', params)

    try:
        # open_order = exchange.fapiPrivate_post_order(params=params)
        open_order = robust(func=exchange.fapiPrivate_post_order,
                            params=params,
                            func_name='close_order')
        log_print('下单完成，下单信息：', open_order, '\n')
        log_print('残单下单成功')
    except Exception as e:
        log_print('下单出错')
        log_print(e)
        return {'status': 500, 'msg': str(e)}

    return {
        'status': 0,
        'msg': '平仓成功',
    }


def dapi_close_order(exchange, symbol):
    if exchange is None or symbol is None:
        return {
            'status': 500,
            'msg': 'params error',
        }

    twap_amount = 50  # 最多一次下多少张
    last_price = fetch_binance_dapi_ticker_data(exchange, symbol)
    price_precision = get_dapi_exchange_info(exchange)

    account_info = exchange.dapiPrivate_get_account()
    assets = account_info['assets']
    positions = account_info['positions']

    for pos in positions:
        if pos['symbol'] != symbol:
            continue
        position_side = pos['positionSide']
        position_amount = float(pos['positionAmt'])
        side = 'BUY' if position_amount < 0 else 'SELL'

    # 计算下单方向、价格
    if side == 'BUY':
        price = last_price * 1.03
    else:
        price = last_price * 0.97

    # 对下单价格这种最小下单精度
    price = float(f'{price:.{price_precision[symbol]}f}')

    log_print(f'{symbol} 需要平仓张数 {position_amount}')
    position_amount = abs(position_amount)

    twap_order_num = math.floor(position_amount / twap_amount)
    for i in range(0, twap_order_num):
        log_print(f'{symbol} twap下单，正在进行第 {i + 1} 次下单')
        quantity = twap_amount
        log_print(f'本次下单量 = {quantity}')

        # # 下单参数
        # params = {
        #     'symbol': symbol,
        #     'side': side,
        #     'type': 'LIMIT',
        #     'price': price,
        #     'quantity': quantity,
        #     'clientOrderId': str(time.time()),
        #     'timeInForce': 'GTC',
        #     'reduceOnly': True
        # }

        # 市价单下单参数
        params = {
            'symbol': symbol,
            'side': side,
            'type': 'MARKET',
            'quantity': quantity,
            'clientOrderId': str(time.time()),
            'reduceOnly': True
        }
        # 下单
        log_print('下单参数：', params)

        try:
            # open_order = exchange.dapiPrivate_post_order(params=params)
            open_order = robust(func=exchange.dapiPrivate_post_order,
                                params=params,
                                func_name='dapi_close_order')
            log_print('下单完成，下单信息：', open_order, '\n')
        except Exception as e:
            log_print('下单出错')
            log_print(e)
            return {'status': 500, 'msg': str(e)}

        position_amount -= quantity
        log_print(f'剩余下单量 = {position_amount}')
        time.sleep(2)

    log_print(f'残单处理，残单量 = {position_amount}')

    if position_amount == 0:
        return {
            'status': 0,
            'msg': '平仓成功',
        }

    # # 下单参数
    # params = {
    #     'symbol': symbol,
    #     'side': side,
    #     'type': 'LIMIT',
    #     'price': price,
    #     'quantity': position_amount,
    #     'clientOrderId': str(time.time()),
    #     'timeInForce': 'GTC',
    #     'reduceOnly': True
    # }

    # 市价单下单参数
    params = {
        'symbol': symbol,
        'side': side,
        'type': 'MARKET',
        'quantity': position_amount,
        'clientOrderId': str(time.time()),
        'reduceOnly': True
    }
    # 下单
    log_print('下单参数：', params)

    try:
        # open_order = exchange.dapiPrivate_post_order(params=params)
        open_order = robust(func=exchange.dapiPrivate_post_order,
                            params=params,
                            func_name='dapi_close_order')
        log_print('下单完成，下单信息：', open_order, '\n')
        log_print('残单下单成功')
    except Exception as e:
        log_print('下单出错')
        log_print(e)
        return {'status': 500, 'msg': str(e)}

    return {
        'status': 0,
        'msg': '平仓成功',
    }


def deribit_close_position(exchange, instrument_name):
    if exchange is None or instrument_name is None:
        return {
            'status': 500,
            'msg': 'params error',
        }

    try:
        # 获取该期权合约的持仓信息
        params = {'instrument_name': instrument_name}
        position = exchange.private_get_get_position(params)['result']
        direction = position['direction']

        # 获取该期权合约的Ask、Bid
        params = {'instrument_name': instrument_name}
        tickers = exchange.public_get_ticker(params)['result']
        best_bid_price = float(tickers['best_bid_price'])
        best_ask_price = float(tickers['best_ask_price'])
        mark_price = float(tickers['mark_price'])
        log_print(
            f'bid:{best_bid_price} ask:{best_ask_price} mark_price:{mark_price}'
        )

        # 下单
        params = {'instrument_name': instrument_name, 'type': 'limit'}
        if direction == 'sell':
            params['price'] = best_ask_price
        elif direction == 'buy':
            params['price'] = best_bid_price

        res = exchange.private_get_close_position(params)
        log_print(res)
        return {
            'status': 0,
            'msg': '下单成功',
        }
    except Exception as e:
        log_print(f'下单失败: {e}')
        return {
            'status': -1,
            'msg': str(e),
        }


def get_subaccount_management_list(exchange):
    if exchange is None:
        return {'status': 0, 'msg': '', 'data': {'items': []}}
    subaccount_list = exchange.sapiGetSubAccountList()
    items = []
    for p in subaccount_list['subAccounts']:
        _createTime = time.localtime(int(p['createTime']) / 1000)
        createTime = time.strftime("%Y-%m-%d %H:%M:%S", _createTime)

        item = {
            'email': p['email'],
            'isFreeze': p['isFreeze'],
            'isManagedSubAccount': p['isManagedSubAccount'],
            'isAssetManagementSubAccount': p['isAssetManagementSubAccount'],
            'createTime': createTime
        }
        items.append(item)
    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def get_all_account_positions_list(binance_list):
    df_list = []
    totalWalletBalance = Decimal(0)
    for binance in binance_list:
        exchange = binance['exchange']
        account = make_binance_account_adapter(
            exchange, binance.get('account_type', ACCOUNT_TYPE_STANDARD))
        if account.is_unified:
            account_info = account.get_account_summary()
            positions = [
                p for p in account.get_um_position_risk()
                if Decimal(str(p.get('positionAmt') or '0')) != 0
            ]
            totalWalletBalance += Decimal(
                str(account_info.get('accountEquity')
                    or account_info.get('totalWalletBalance') or '0'))
        else:
            account_info = account.get_account_summary()['raw']
            positions = [
                p for p in account_info['positions']
                if Decimal(str(p.get('positionInitialMargin') or '0')) > 0
            ]
            totalWalletBalance += Decimal(
                str(account_info['totalWalletBalance']))  # 钱包保证金余额

        temp_df = pd.DataFrame(positions)
        df_list.append(temp_df)

        items = []
    if len(df_list) == 0:
        return {'status': 0, 'msg': '', 'data': {'items': [], 'total': 0}}
    df = pd.concat(df_list, axis=0)

    items = []
    if len(df) == 0:
        return {'status': 0, 'msg': '', 'data': {'items': items, 'total': 0}}

    if 'unrealizedProfit' not in df and 'unRealizedProfit' in df:
        df['unrealizedProfit'] = df['unRealizedProfit']
    if 'notional' not in df and 'notionalValue' in df:
        df['notional'] = df['notionalValue']
    if 'initialMargin' not in df:
        df['initialMargin'] = 0
    if 'leverage' not in df:
        df['leverage'] = 0

    df = df[['symbol', 'initialMargin', 'unrealizedProfit', 'positionAmt',
             'leverage', 'notional']]
    for col in [
            'initialMargin', 'unrealizedProfit', 'positionAmt', 'notional',
            'leverage'
    ]:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    symbol_info = df.groupby('symbol').agg({
        'initialMargin': 'sum',
        'unrealizedProfit': 'sum',
        'positionAmt': 'sum',
        'notional': 'sum',
        'leverage': 'mean'
    })
    symbol_info = symbol_info.reset_index()
    # symbol_info['profit_ratio'] = (
    #     (symbol_info['initialMargin'] + symbol_info['unrealizedProfit']) /
    #     symbol_info['initialMargin'] - 1) / symbol_info['leverage']
    symbol_info['profit_ratio'] = 0.0
    denominator = abs(symbol_info['notional'] - symbol_info['unrealizedProfit'])
    symbol_info.loc[denominator > 0, 'profit_ratio'] = (
        symbol_info.loc[denominator > 0, 'unrealizedProfit'] /
        denominator[denominator > 0])
    symbol_info['leverage_ratio'] = symbol_info['notional'] / float(
        totalWalletBalance) if totalWalletBalance > 0 else 0
    for i in range(0, len(symbol_info)):
        side = 'BUY' if symbol_info.iloc[i]['positionAmt'] > 0 else 'SELL'
        item = {
            'symbol':
                symbol_info.iloc[i]['symbol'],
            'side':
                side,
            'position_amount':
                str(round(symbol_info.iloc[i]['positionAmt'], 3)),
            'position_usd':
                str(round(symbol_info.iloc[i]['notional'], 2)),
            'profit':
                str(round(symbol_info.iloc[i]['unrealizedProfit'], 2)),
            'profit_ratio':
                str(round(symbol_info.iloc[i]['profit_ratio'] * 100, 2)) + '%',
            'leverage_ratio':
                str(abs(round(symbol_info.iloc[i]['leverage_ratio'] * 100, 2))) +
                '%'
        }

        items.append(item)

    def get_side(enum):
        return enum['side'], -abs(float(enum['position_usd']))

    items.sort(key=get_side)

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def get_all_account_balance(binance_list):
    totalWalletBalance = Decimal(0)
    totalUnrealizedProfit = Decimal(0)
    totalMarginBalance = Decimal(0)
    buy_position = Decimal(0)
    sell_position = Decimal(0)

    sub_items = []
    items = []

    for binance in binance_list:
        exchange = binance['exchange']

        account = make_binance_account_adapter(
            exchange, binance.get('account_type', ACCOUNT_TYPE_STANDARD))
        if account.is_unified:
            account_info = account.get_account_summary()
            positions = [
                p for p in account.get_um_position_risk()
                if Decimal(str(p.get('positionAmt') or '0')) != 0
            ]
            subTotalWalletBalance = Decimal(
                str(account_info.get('accountEquity')
                    or account_info.get('totalWalletBalance') or '0'))
            subTotalUnrealizedProfit = sum(
                Decimal(
                    str(p.get('unRealizedProfit')
                        or p.get('unrealizedProfit') or '0'))
                for p in positions)
            subTotalMarginBalance = Decimal(
                str(account_info.get('accountEquity')
                    or account_info.get('totalMarginBalance') or '0'))
        else:
            account_info = account.get_account_summary()['raw']
            positions = [
                p for p in account_info['positions']
                if Decimal(str(p.get('positionInitialMargin') or '0')) > 0
            ]
            subTotalWalletBalance = Decimal(
                str(account_info['totalWalletBalance']))  # 钱包保证金余额
            subTotalUnrealizedProfit = Decimal(
                str(account_info['totalUnrealizedProfit']))
            subTotalMarginBalance = Decimal(
                str(account_info['totalMarginBalance']))
        subProfit_ratio = subTotalUnrealizedProfit / subTotalWalletBalance if subTotalWalletBalance > 0 else 0

        sub_buy_position = 0
        sub_sell_position = 0

        for pos in positions:
            position_amount = Decimal(str(pos['positionAmt']))
            position_usd = Decimal(str(pos.get('notional')
                                       or pos.get('notionalValue') or '0'))
            if position_amount > 0:
                sub_buy_position += position_usd
                buy_position += position_usd
            else:
                sub_sell_position += position_usd
                sell_position += position_usd

        sub_leverage_ratio = (
                                     sub_buy_position + abs(sub_sell_position)
                             ) / subTotalWalletBalance if subTotalWalletBalance > 0 else 0
        sub_items.append({
            'strategy_name':
                binance['strategy'],
            'wallet_balance':
                str(round(subTotalWalletBalance, 2)),
            'net_value':
                str(round(subTotalMarginBalance, 2)),
            'unrealized_profit':
                str(round(subTotalUnrealizedProfit, 2)),
            'profit_ratio':
                str(round(subProfit_ratio * 100, 2)) + '%',
            'buy_position':
                str(round(sub_buy_position, 2)),
            'sell_position':
                str(round(sub_sell_position, 2)),
            'leverage_ratio':
                str(round(sub_leverage_ratio, 2))
        })

        totalWalletBalance += subTotalWalletBalance
        totalUnrealizedProfit += subTotalUnrealizedProfit
        totalMarginBalance += subTotalMarginBalance

    leverage_ratio = (buy_position + abs(sell_position)
                      ) / totalWalletBalance if totalWalletBalance > 0 else 0
    profit_ratio = totalUnrealizedProfit / totalWalletBalance if totalWalletBalance > 0 else 0

    items.append({
        'strategy_name': '账户汇总',
        'wallet_balance': str(round(totalWalletBalance, 2)),
        'net_value': str(round(totalMarginBalance, 2)),
        'unrealized_profit': str(round(totalUnrealizedProfit, 2)),
        'profit_ratio': str(round(profit_ratio * 100, 2)) + '%',
        'buy_position': str(round(buy_position, 2)),
        'sell_position': str(round(sell_position, 2)),
        'leverage_ratio': str(round(leverage_ratio, 2))
    })

    items.extend(sub_items)

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def get_symbol_list(exchange):
    exchange_info = get_fapi_public_exchange_info(exchange)
    _symbol_list = [
        x['symbol'] for x in exchange_info['symbols']
        if x['status'] == 'TRADING'
    ]
    symbol_list = [
        symbol for symbol in _symbol_list if symbol.endswith('USDT')
    ]

    _temp_list = []
    for symbol in symbol_list:
        if symbol in ['COCOSUSDT', 'BTCSTUSDT', 'DREPUSDT', 'SUNUSDT']:
            continue
        if symbol.endswith(('DOWNUSDT', 'UPUSDT', 'BULLUSDT', 'BEARUSDT')):
            continue
        _temp_list.append(symbol)
    symbol_list = _temp_list

    options = []
    for i in symbol_list:
        op = {'label': i, 'value': i}
        options.append(op)
    return {
        'status': 0,
        'msg': '',
        'data': {
            'options': options,
        }
    }


def get_same_account_asset_list(exchange, type):
    if exchange is None:
        return {'status': 0, 'msg': '', 'data': {'items': []}}
    if type == '1':
        exchange_info = exchange.fapiPrivateV2_get_account()
        spot_info = exchange.private_get_account()
        available_list = [
            x['asset'] for x in spot_info['balances']
            if float(x['free']) > float(0)
        ]
        to_symbol_list = [
            x['asset'] for x in exchange_info['assets']
            if x['asset'] in available_list
        ]
    elif type == '2':
        exchange_info = exchange.fapiPrivateV2_get_account()
        to_symbol_list = [
            x['asset'] for x in exchange_info['assets']
            if float(x['maxWithdrawAmount']) > float(0)
        ]
    elif type == '3':
        exchange_info = exchange.dapiPrivate_get_account()
        spot_info = exchange.private_get_account()
        available_list = [
            x['asset'] for x in spot_info['balances']
            if float(x['free']) > float(0)
        ]
        to_symbol_list = [
            x['asset'] for x in exchange_info['assets']
            if x['asset'] in available_list
        ]
    elif type == '4':
        exchange_info = exchange.dapiPrivate_get_account()
        to_symbol_list = [
            x['asset'] for x in exchange_info['assets']
            if float(x['maxWithdrawAmount']) > float(0)
        ]
    else:
        return {'status': 0, 'msg': '', 'data': {'items': []}}

    options = []
    for i in to_symbol_list:
        op = {'label': i, 'value': i}
        options.append(op)
    return {
        'status': 0,
        'msg': '',
        'data': {
            'options': options,
        }
    }


def get_asset_list(exchange, fromWallet, toWallet):
    if exchange is None:
        return {'status': 0, 'msg': '', 'data': {'items': []}}

    if fromWallet == 'USDT_FUTURE' and toWallet == 'USDT_FUTURE':
        exchange_info = exchange.fapiPrivateV2_get_account()
        to_symbol_list = [
            x['asset'] for x in exchange_info['assets']
            if float(x['maxWithdrawAmount']) > float(0)
        ]
    elif fromWallet == 'USDT_FUTURE' and toWallet == 'COIN_FUTURE':
        exchange_info = exchange.fapiPrivateV2_get_account()
        from_symbol_list = [
            x['asset'] for x in exchange_info['assets']
            if float(x['maxWithdrawAmount']) > float(0)
        ]
        exchange_info = exchange.dapiPrivate_get_account()
        temp_symbol_list = [x['asset'] for x in exchange_info['assets']]
        to_symbol_list = [
            symbol for symbol in from_symbol_list if symbol in temp_symbol_list
        ]
    elif fromWallet == 'USDT_FUTURE' and toWallet == 'SPOT':
        exchange_info = exchange.fapiPrivateV2_get_account()
        to_symbol_list = [
            x['asset'] for x in exchange_info['assets']
            if float(x['maxWithdrawAmount']) > float(0)
        ]
    elif fromWallet == 'COIN_FUTURE' and toWallet == 'USDT_FUTURE':
        exchange_info = exchange.dapiPrivate_get_account()
        from_symbol_list = [
            x['asset'] for x in exchange_info['assets']
            if float(x['maxWithdrawAmount']) > float(0)
        ]
        exchange_info = exchange.fapiPrivateV2_get_account()
        temp_symbol_list = [x['asset'] for x in exchange_info['assets']]
        to_symbol_list = [
            symbol for symbol in from_symbol_list if symbol in temp_symbol_list
        ]
    elif fromWallet == 'COIN_FUTURE' and toWallet == 'COIN_FUTURE':
        exchange_info = exchange.dapiPrivate_get_account()
        to_symbol_list = [
            x['asset'] for x in exchange_info['assets']
            if float(x['maxWithdrawAmount']) > float(0)
        ]
    elif fromWallet == 'COIN_FUTURE' and toWallet == 'SPOT':
        exchange_info = exchange.dapiPrivate_get_account()
        to_symbol_list = [
            x['asset'] for x in exchange_info['assets']
            if float(x['maxWithdrawAmount']) > float(0)
        ]
    elif fromWallet == 'SPOT' and toWallet == 'USDT_FUTURE':
        exchange_info = exchange.fapiPrivateV2_get_account()
        spot_info = exchange.private_get_account()
        available_list = [
            x['asset'] for x in spot_info['balances']
            if float(x['free']) > float(0)
        ]
        to_symbol_list = [
            x['asset'] for x in exchange_info['assets']
            if x['asset'] in available_list
        ]
    elif fromWallet == 'SPOT' and toWallet == 'COIN_FUTURE':
        exchange_info = exchange.dapiPrivate_get_account()
        spot_info = exchange.private_get_account()
        available_list = [
            x['asset'] for x in spot_info['balances']
            if float(x['free']) > float(0)
        ]
        to_symbol_list = [
            x['asset'] for x in exchange_info['assets']
            if x['asset'] in available_list
        ]
    elif fromWallet == 'SPOT' and toWallet == 'SPOT':
        exchange_info = exchange.private_get_account()
        black_list = ['LDSOL', 'LDBNB', 'LDUSDT', 'LDBUSD', 'LDETH']
        temp_list = [
            x['asset'] for x in exchange_info['balances']
            if float(x['free']) > float(0)
        ]
        to_symbol_list = [
            symbol for symbol in temp_list if not symbol.endswith('UP')
                                              and not symbol.endswith('DOWN') and not symbol.endswith('BEAR')
                                              and not symbol.endswith('BULL') and symbol not in black_list
        ]
    else:
        return {'status': 0, 'msg': '', 'data': {'items': []}}

    options = []
    for i in to_symbol_list:
        op = {'label': i, 'value': i}
        options.append(op)
    return {
        'status': 0,
        'msg': '',
        'data': {
            'options': options,
        }
    }


def get_max_free_asset(exchange, fromWallet, asset):
    if exchange is None:
        return {'status': 0, 'msg': '', 'data': {'items': []}}
    max_free_asset = 0
    if fromWallet == 'USDT_FUTURE':
        exchange_info = exchange.fapiPrivateV2_get_account()
        for x in exchange_info['assets']:
            if x['asset'] == asset:
                max_free_asset = x['maxWithdrawAmount']
            else:
                continue

    elif fromWallet == 'COIN_FUTURE':
        exchange_info = exchange.dapiPrivate_get_account()
        for x in exchange_info['assets']:
            if x['asset'] == asset:
                max_free_asset = x['maxWithdrawAmount']
            else:
                continue

    elif fromWallet == 'SPOT':
        exchange_info = exchange.private_get_account()
        for x in exchange_info['balances']:
            if x['asset'] == asset:
                max_free_asset = x['free']
            else:
                continue
    else:
        return {'status': 0, 'msg': '', 'data': {'items': []}}

    return {
        'status': 0,
        'msg': '',
        'data': {
            'max_free_asset_amount': max_free_asset
        }
    }


def get_same_account_max_free_asset(exchange, type, asset):
    if exchange is None:
        return {'status': 0, 'msg': ''}
    max_free_asset = 0
    if type == '1':
        exchange_info = exchange.private_get_account()
        for x in exchange_info['balances']:
            if x['asset'] == asset:
                max_free_asset = x['free']
            else:
                continue
    elif type == '2':
        exchange_info = exchange.fapiPrivateV2_get_account()
        for x in exchange_info['assets']:
            if x['asset'] == asset:
                max_free_asset = x['maxWithdrawAmount']
            else:
                continue
    elif type == '3':
        exchange_info = exchange.private_get_account()
        for x in exchange_info['balances']:
            if x['asset'] == asset:
                max_free_asset = x['free']
            else:
                continue
    elif type == '4':
        exchange_info = exchange.dapiPrivate_get_account()
        for x in exchange_info['assets']:
            if x['asset'] == asset:
                max_free_asset = x['maxWithdrawAmount']
            else:
                continue
    else:
        return {'status': 0, 'msg': ''}

    return {
        'status': 0,
        'msg': '',
        'data': {
            'max_free_asset_amount': max_free_asset
        }
    }


def get_exchange_info(exchange, use_notional=False):
    exchange_info = get_fapi_public_exchange_info(exchange)
    _symbol_list = [
        x['symbol'] for x in exchange_info['symbols']
        if x['status'] == 'TRADING'
    ]
    symbol_list = [
        symbol for symbol in _symbol_list if symbol.endswith('USDT')
    ]

    _temp_list = []
    for symbol in symbol_list:
        if symbol in ['COCOSUSDT', 'BTCSTUSDT', 'DREPUSDT', 'SUNUSDT']:
            continue
        if symbol.endswith(('DOWNUSDT', 'UPUSDT', 'BULLUSDT', 'BEARUSDT')):
            continue
        _temp_list.append(symbol)
    symbol_list = _temp_list
    min_qty = {}
    price_precision = {}
    min_notional = {}

    for x in exchange_info['symbols']:
        _symbol = x['symbol']

        for _filter in x['filters']:
            if _filter['filterType'] == 'PRICE_FILTER':
                price_precision[_symbol] = int(
                    math.log(float(_filter['tickSize']), 0.1))
            elif _filter['filterType'] == 'MARKET_LOT_SIZE':
                min_qty[_symbol] = int(math.log(float(_filter['minQty']), 0.1))
            elif _filter['filterType'] == 'MIN_NOTIONAL':
                min_notional[_symbol] = float(_filter['notional'])

    if use_notional:
        return min_notional
    return min_qty, price_precision


def get_dapi_exchange_info(exchange):
    exchange_info = get_dapi_public_exchange_info(exchange)
    price_precision = {}

    for x in exchange_info['symbols']:
        _symbol = x['symbol']

        for _filter in x['filters']:
            if _filter['filterType'] == 'PRICE_FILTER':
                price_precision[_symbol] = int(
                    math.log(float(_filter['tickSize']), 0.1))

    return price_precision


def get_dapi_perp_symbol_list(exchange):
    exchange_info = get_dapi_public_exchange_info(exchange)
    _symbol_list = [
        x['symbol'] for x in exchange_info['symbols']
        if x['contractStatus'] == 'TRADING'
    ]
    symbol_list = [
        symbol for symbol in _symbol_list if symbol.endswith('PERP')
    ]
    return symbol_list


# 获取币安的ticker数据
def ticker_last_price_map(tickers):
    tickers = pd.DataFrame(tickers)
    tickers['lastPrice'] = pd.to_numeric(tickers['lastPrice'])
    tickers.set_index('symbol', inplace=True)
    return tickers.to_dict(orient='dict')['lastPrice']


def fetch_binance_ticker_data(exchange, symbol=None):
    if symbol is None:
        tickers = get_fapi_public_ticker_24hr(exchange)
        return ticker_last_price_map(tickers)
    else:
        tickers = get_fapi_public_ticker_24hr(exchange, {'symbol': symbol})
        return float(tickers['lastPrice'])


# 获取币安的ticker数据
def fetch_binance_dapi_ticker_data(exchange, symbol=None):
    if symbol is None:
        tickers = get_dapi_public_ticker_24hr(exchange)
        return ticker_last_price_map(tickers)
    else:
        tickers = get_dapi_public_ticker_24hr(exchange, {'symbol': symbol})
        if isinstance(tickers, list):
            tickers = tickers[0]
        return float(tickers['lastPrice'])


# 获取当日成交订单
def get_account_today_orders(exchange, account_type=ACCOUNT_TYPE_STANDARD):
    if exchange is None:
        return {'status': 0, 'msg': '', 'data': {'items': []}}
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_time_unix = int(start.timestamp() * 1000)
    params = {'startTime': start_time_unix}

    account = make_binance_account_adapter(exchange, account_type)
    try:
        orders = account.get_user_trades('um', params)
    except ccxt.BaseError as e:
        log_print(f'获取U本位当日成交失败: {e}')
        return {'status': 0, 'msg': '获取当日成交失败', 'data': {'items': []}}
    if len(orders) == 0:
        return {'status': 0, 'msg': '', 'data': {'items': []}}

    df = pd.DataFrame(orders)

    df = df[[
        'symbol', 'realizedPnl', 'side', 'price', 'qty', 'quoteQty',
        'commission', 'commissionAsset', 'time'
    ]]

    df['time'] = pd.to_numeric(df['time'])
    items = df.to_dict(orient='records')

    def get_time(enum):
        return enum['time']

    items.sort(key=get_time, reverse=True)

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


# 获取当日成交订单
def get_dapi_account_today_orders(exchange, symbol):
    if exchange is None or symbol == '':
        return {'status': 0, 'msg': '', 'data': {'items': []}}
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_time_unix = int(start.timestamp() * 1000)
    params = {'startTime': start_time_unix, 'symbol': symbol}

    orders = exchange.dapiPrivateGetUserTrades(params)
    if len(orders) == 0:
        return {'status': 0, 'msg': '', 'data': {'items': []}}

    df = pd.DataFrame(orders)

    df = df[[
        'symbol', 'realizedPnl', 'side', 'price', 'qty', 'baseQty',
        'commission', 'commissionAsset', 'time'
    ]]

    df['time'] = pd.to_numeric(df['time'])
    items = df.to_dict(orient='records')

    def get_time(enum):
        return enum['time']

    items.sort(key=get_time, reverse=True)

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


# 获取冲提币, c2c划转信息
def get_deposit_withdraw_info(binance):
    if binance['exchange'] is None:
        return 0, 0

    exchange = binance['exchange']
    now = datetime.now()
    start = now.replace(second=0, microsecond=0)
    start -= timedelta(minutes=10)
    start_time_unix = int(start.timestamp() * 1000)

    usd_in = 0
    usd_out = 0

    last_price = fetch_binance_ticker_data(exchange)
    last_price['BUSDUSDT'] = 1
    last_price['USDTUSDT'] = 1
    last_price['USDCUSDT'] = 1

    # 检查是否有用户间转账
    params = {"startTime": start_time_unix}
    try:
        payment = exchange.sapiGetPayTransactions(params)
        if payment['data'] != []:
            for transaction in payment['data']:
                symbol = f'{transaction["currency"]}USDT'
                if float(transaction['amount']) >= 0:
                    usd_in += float(last_price[symbol]) * float(
                        transaction['amount'])
                else:
                    # 转出amount为负
                    usd_out += -1 * float(last_price[symbol]) * float(
                        transaction['amount'])
    except Exception as e:
        log_print("检查用户间转账" + str(e))

    # 检查链上充值
    try:
        chain_to_spot = exchange.sapiGetCapitalDepositHisrec(params)
        if chain_to_spot != []:
            for record in chain_to_spot:
                symbol = f'{record["coin"]}USDT'
                usd_in += float(last_price[symbol]) * float(record['amount'])
    except Exception as e:
        log_print("检查链上充值" + str(e))

    # 检查向链上提币
    try:
        spot_to_chain = exchange.sapiGetCapitalWithdrawHistory(params)
        if spot_to_chain != []:
            for record in spot_to_chain:
                symbol = f'{record["coin"]}USDT'
                usd_out += float(last_price[symbol]) * (
                        float(record['amount']) + float(record['transactionFee']))
    except Exception as e:
        log_print("检查提币到链上" + str(e))

    if binance['is_main'] == 1:
        # 检查母账户转出
        try:
            params = {
                "startTime": start_time_unix,
                "fromEmail": binance['account']
            }
            main_to_sub = exchange.sapiGetSubAccountUniversalTransfer(params)
            if main_to_sub['result'] != []:
                for record in main_to_sub['result']:
                    symbol = f'{record["coin"]}USDT'
                    usd_out += float(last_price[symbol]) * float(
                        record['amount'])
        except Exception as e:
            log_print("检查母账户转出" + str(e))
        # 检查母账户转入
        try:
            params = {
                "startTime": start_time_unix,
                "toEmail": binance['account']
            }
            sub_to_main = exchange.sapiGetSubAccountUniversalTransfer(params)
            if sub_to_main['result'] != []:
                for record in sub_to_main['result']:
                    symbol = f'{record["asset"]}USDT'
                    usd_in += float(last_price[symbol]) * float(
                        record['amount'])
        except Exception as e:
            log_print("检查母账户转入" + str(e))
    else:
        # 检查子账户转入
        try:
            params = {'type': 1, "startTime": start_time_unix}
            sub_in = exchange.sapiGetSubAccountTransferSubUserHistory(params)
            for i in sub_in:
                symbol = f'{i["asset"]}USDT'
                usd_in += float(last_price[symbol]) * float(i['qty'])
        except Exception as e:
            log_print("检查子账户转入" + str(e))
        # 检查子账户转出
        try:
            params = {'type': 2, "startTime": start_time_unix}
            sub_out = exchange.sapiGetSubAccountTransferSubUserHistory(params)
            for i in sub_out:
                symbol = f'{i["asset"]}USDT'
                usd_out += float(last_price[symbol]) * float(i['qty'])
        except Exception as e:
            log_print("检查子账户转出" + str(e))

    log_print(usd_in, usd_out)
    return usd_in, usd_out


# 获取该账户过去10分钟的转入转出信息
def get_transfer_info(exchange):
    if exchange is None:
        return 0, 0

    now = datetime.now()
    start = now.replace(second=0, microsecond=0)
    start -= timedelta(minutes=10)
    start_time_unix = int(start.timestamp() * 1000)

    usd_in = 0
    usd_out = 0

    last_price = fetch_binance_ticker_data(exchange)
    last_price['USDTUSDT'] = 1
    last_price['BUSDUSDT'] = 1
    last_price['USDCUSDT'] = 1
    last_price['BTCUSDT'] = last_price['BTCUSDT'] * 0.95
    last_price['ETHUSDT'] = last_price['ETHUSDT'] * 0.95
    last_price['BNBUSDT'] = last_price['BNBUSDT'] * 0.95
    last_price['XRPUSDT'] = last_price['XRPUSDT'] * 0.9
    last_price['ADAUSDT'] = last_price['ADAUSDT'] * 0.9
    last_price['DOTUSDT'] = last_price['DOTUSDT'] * 0.9
    last_price['SOLUSDT'] = last_price['SOLUSDT'] * 0.9

    # 现货转入U本位合约
    try:
        params = {'type': 'MAIN_UMFUTURE', 'startTime': start_time_unix}
        spot_to_u = exchange.sapiGetAssetTransfer(params)
        if spot_to_u['total'] != '0':
            for i in spot_to_u['rows']:
                symbol = i['asset'] + 'USDT'
                usd_in += last_price[symbol] * float(i['amount'])
    except Exception as e:
        log_print('现货转入U本位合约' + str(e))

    # U本位合约转入现货
    try:
        params = {'type': 'UMFUTURE_MAIN', 'startTime': start_time_unix}
        u_to_spot = exchange.sapiGetAssetTransfer(params)
        if u_to_spot['total'] != '0':
            for i in u_to_spot['rows']:
                symbol = i['asset'] + 'USDT'
                usd_out += last_price[symbol] * float(i['amount'])
    except Exception as e:
        log_print('U本位合约转出至现货' + str(e))

    # 其他账户向子账户转入
    try:
        params = {'type': 1, 'startTime': start_time_unix}
        sub_in = exchange.sapiGetSubAccountTransferSubUserHistory(params)
        for i in sub_in:
            if i['toAccountType'] == 'FUTURE':
                symbol = i['asset'] + 'USDT'
                usd_in += last_price[symbol] * float(i['qty'])
    except Exception as e:
        log_print('转入子账户U本位合约' + str(e))

    # 子账户向其他账户转出
    try:
        params = {'type': 2, 'startTime': start_time_unix}
        sub_out = exchange.sapiGetSubAccountTransferSubUserHistory(params)
        for i in sub_out:
            if i['fromAccountType'] == 'FUTURE':
                symbol = i['asset'] + 'USDT'
                usd_out += last_price[symbol] * float(i['qty'])
    except Exception as e:
        log_print('子账户U本位合约转出' + str(e))

    return usd_in, usd_out


# 获取该账户过去10分钟的转入转出信息
def get_dapi_transfer_info(exchange):
    if exchange is None:
        return 0, 0

    now = datetime.now()
    start = now.replace(second=0, microsecond=0)
    start -= timedelta(minutes=10)
    start_time_unix = int(start.timestamp() * 1000)

    usd_in = 0
    usd_out = 0

    last_price = fetch_binance_dapi_ticker_data(exchange)

    # 现货转入币本位合约
    try:
        params = {'type': 'MAIN_CMFUTURE', 'startTime': start_time_unix}
        spot_to_c = exchange.sapiGetAssetTransfer(params)
        if spot_to_c['total'] != '0':
            for i in spot_to_c['rows']:
                symbol = i['asset'] + 'USD_PERP'
                usd_in += last_price[symbol] * float(i['amount'])
    except Exception as e:
        log_print('现货转入币本位合约' + str(e))

    # 币本位合约转入现货
    try:
        params = {'type': 'CMFUTURE_MAIN', 'startTime': start_time_unix}
        c_to_spot = exchange.sapiGetAssetTransfer(params)
        if c_to_spot['total'] != '0':
            for i in c_to_spot['rows']:
                symbol = i['asset'] + 'USD_PERP'
                usd_out += last_price[symbol] * float(i['amount'])
    except Exception as e:
        log_print('币本位合约转出至现货' + str(e))

    return usd_in, usd_out


def get_bbw_echarts(exchange, symbol, interval):
    if exchange is None or symbol == '' or interval == '':
        return {'status': 0, 'msg': '', 'data': {}}

    df = get_kline(exchange, symbol, interval, 1000)
    df['ctime'] = df['candle_begin_time'].apply(str)
    df['median'] = df['close'].rolling(20, min_periods=1).mean()
    df['std'] = df['close'].rolling(20, min_periods=1).std(ddof=0)
    df['upper'] = df['median'] + df['std'] * 2
    df['lower'] = df['median'] - df['std'] * 2
    df['bbw'] = (df['upper'] - df['lower']) / df['median']

    x_series = df['ctime'].tolist()[20:]
    bbw_series = df['bbw'].tolist()[20:]
    bbw_series = [round(bbw, 4) for bbw in bbw_series]

    bbw_data = {
        'title': {
            'text': '历史波动率'
        },
        'tooltip': {
            'trigger': 'axis'
        },
        'legend': {},
        'toolbox': {
            'show': True,
            'feature': {
                'dataZoom': {
                    'yAxisIndex': 'none'
                },
                'dataView': {
                    'readOnly': False
                },
                'magicType': {
                    'type': ['line', 'bar']
                },
                'restore': {},
                'saveAsImage': {}
            }
        },
        'xAxis': {
            'type': 'category',
            'boundaryGap': False,
            'data': x_series
        },
        'yAxis': [{
            'type': 'value',
            'name': 'bbw'
        }],
        'dataZoom': [{
            'type': 'inside',
            'start': 80,
            'end': 100
        }, {
            'show': True,
            'type': 'slider',
            'top': '90%',
            'start': 80,
            'end': 100
        }],
        'series': [{
            'name': 'bbw',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 0,
            'data': bbw_series,
            'markPoint': {
                'symbol':
                    "pin",
                'symbolSize':
                    70,
                'data': [{
                    'type': 'max',
                    'name': 'Max'
                }, {
                    'type': 'min',
                    'name': 'Min'
                }, {
                    'type': 'average',
                    'name': 'mean'
                }]
            }
        }]
    }
    return {'status': 0, 'msg': '', 'data': bbw_data}


# 获取账户总计的资金曲线
def get_account_management_balance_echarts(exchange):
    engine = create_engine(sql_uri)
    sql = f'select * from total_binance_account_value'
    try:
        df = pd.read_sql(sql, con=engine, index_col='index')
    except:
        return {'status': 0, 'msg': '', 'data': {}}

    df['ctime'] = df['candle_begin_time'].apply(
        lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))
    df['equity_curve'] = df['accumulate_value']
    df['profit_ratio'] = df['accumulate_value'] - 1
    df['profit_ratio_percent'] = df['profit_ratio'] * 100

    # ===计算最大回撤，最大回撤的含义：《如何通过3行代码计算最大回撤》https://mp.weixin.qq.com/s/Dwt4lkKR_PEnWRprLlvPVw
    # 计算当日之前的资金曲线的最高点
    df['max2here'] = df['equity_curve'].expanding().max()
    # 计算到历史最高值到当日的跌幅，drowdwon
    df['dd2here'] = df['equity_curve'] / df['max2here'] - 1
    df['dd2here_percent'] = df['dd2here'] * 100

    df = df.round(2)

    x_series = list(df['ctime'])
    equity_series = list(df['profit_ratio_percent'])
    drawdown_series = list(df['dd2here_percent'])

    equity_data = {
        'title': {
            'text': '账户净值曲线'
        },
        'tooltip': {
            'trigger': 'axis'
        },
        'legend': {},
        'toolbox': {
            'show': True,
            'feature': {
                'dataZoom': {
                    'yAxisIndex': 'none'
                },
                'dataView': {
                    'readOnly': False
                },
                'magicType': {
                    'type': ['line', 'bar']
                },
                'restore': {},
                'saveAsImage': {}
            }
        },
        'visualMap': [
            {
                'show': False,
                'type': 'continuous',
                'seriesIndex': 0,
                'min': -80,
                'max': 300,
                'inRange': {
                    'color': ['#ff0000', '#ffff00', '#00ff00', '#3399ff'],
                },
            },
        ],
        'xAxis': {
            'type': 'category',
            'boundaryGap': False,
            'data': x_series
        },
        'yAxis': [
            {
                'type': 'value',
                'name': 'equity',
                'axisLabel': {
                    'formatter': '{value} %'
                }
            },
            {
                'name': 'drawdown',
                'nameLocation': 'start',
                # 'inverse': True,
                'max': 0,
                'axisLabel': {
                    'formatter': '{value} %'
                }
            }
        ],
        'dataZoom': [{
            'type': 'inside',
            'start': 0,
            'end': 100
        }, {
            'show': True,
            'type': 'slider',
            'top': '90%',
            'start': 0,
            'end': 100
        }],
        'series': [{
            'name': 'equity_curve',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 0,
            'data': equity_series,
            'markPoint': {
                'data': [{
                    'type': 'max',
                    'name': 'Max'
                }, {
                    'type': 'min',
                    'name': 'Min'
                }],
                'symbolSize':
                    60,
            }
        }, {
            'name': 'drawdown',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 1,
            'data': drawdown_series,
        }]
    }
    return {'status': 0, 'msg': '', 'data': equity_data}


# 获取账户的资金曲线
def get_account_balance_echarts(strategy):
    engine = create_engine(sql_uri)
    sql = f'select * from {strategy}_value'
    try:
        df = pd.read_sql(sql, con=engine, index_col='index')
    except:
        return {'status': 0, 'msg': '', 'data': {}}

    df['ctime'] = df['candle_begin_time'].apply(
        lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))
    df['equity_curve'] = df['accumulate_value']
    df['profit_ratio'] = df['accumulate_value'] - 1
    df['profit_ratio_percent'] = df['profit_ratio'] * 100

    # ===计算最大回撤，最大回撤的含义：《如何通过3行代码计算最大回撤》https://mp.weixin.qq.com/s/Dwt4lkKR_PEnWRprLlvPVw
    # 计算当日之前的资金曲线的最高点
    df['max2here'] = df['equity_curve'].expanding().max()
    # 计算到历史最高值到当日的跌幅，drowdwon
    df['dd2here'] = df['equity_curve'] / df['max2here'] - 1
    df['dd2here_percent'] = df['dd2here'] * 100

    df = df.round(2)

    x_series = list(df['ctime'])
    equity_series = list(df['profit_ratio_percent'])
    drawdown_series = list(df['dd2here_percent'])

    equity_data = {
        'title': {
            'text': '账户净值曲线'
        },
        'tooltip': {
            'trigger': 'axis'
        },
        'legend': {},
        'toolbox': {
            'show': True,
            'feature': {
                'dataZoom': {
                    'yAxisIndex': 'none'
                },
                'dataView': {
                    'readOnly': False
                },
                'magicType': {
                    'type': ['line', 'bar']
                },
                'restore': {},
                'saveAsImage': {}
            }
        },
        'visualMap': [
            {
                'show': False,
                'type': 'continuous',
                'seriesIndex': 0,
                'min': -80,
                'max': 300,
                'inRange': {
                    'color': ['#ff0000', '#ffff00', '#00ff00', '#3399ff'],
                },
            },
        ],
        'xAxis': {
            'type': 'category',
            'boundaryGap': False,
            'data': x_series
        },
        'yAxis': [
            {
                'type': 'value',
                'name': 'equity',
                'axisLabel': {
                    'formatter': '{value} %'
                }
            },
            {
                'name': 'drawdown',
                'nameLocation': 'start',
                # 'inverse': True,
                'max': 0,
                'axisLabel': {
                    'formatter': '{value} %'
                }
            }
        ],
        'dataZoom': [{
            'type': 'inside',
            'start': 0,
            'end': 100
        }, {
            'show': True,
            'type': 'slider',
            'top': '90%',
            'start': 0,
            'end': 100
        }],
        'series': [{
            'name': 'equity_curve',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 0,
            'data': equity_series,
            'markPoint': {
                'data': [{
                    'type': 'max',
                    'name': 'Max'
                }, {
                    'type': 'min',
                    'name': 'Min'
                }],
                'symbolSize':
                    60,
            }
        }, {
            'name': 'drawdown',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 1,
            'data': drawdown_series,
        }]
    }
    return {'status': 0, 'msg': '', 'data': equity_data}


# 获取账户的资金曲线
def get_dapi_account_balance_echarts(strategy):
    engine = create_engine(sql_uri)
    sql = f'select * from dapi_{strategy}_value'
    try:
        df = pd.read_sql(sql, con=engine, index_col='index')
    except:
        return {'status': 0, 'msg': '', 'data': {}}

    df['ctime'] = df['candle_begin_time'].apply(
        lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))
    df['equity_curve'] = df['accumulate_value']
    df['profit_ratio'] = df['accumulate_value'] - 1
    df['profit_ratio_percent'] = df['profit_ratio'] * 100

    # ===计算最大回撤，最大回撤的含义：《如何通过3行代码计算最大回撤》https://mp.weixin.qq.com/s/Dwt4lkKR_PEnWRprLlvPVw
    # 计算当日之前的资金曲线的最高点
    df['max2here'] = df['equity_curve'].expanding().max()
    # 计算到历史最高值到当日的跌幅，drowdwon
    df['dd2here'] = df['equity_curve'] / df['max2here'] - 1
    df['dd2here_percent'] = df['dd2here'] * 100

    df = df.round(2)

    x_series = list(df['ctime'])
    equity_series = list(df['profit_ratio_percent'])
    drawdown_series = list(df['dd2here_percent'])

    equity_data = {
        'title': {
            'text': '账户净值曲线'
        },
        'tooltip': {
            'trigger': 'axis'
        },
        'legend': {},
        'toolbox': {
            'show': True,
            'feature': {
                'dataZoom': {
                    'yAxisIndex': 'none'
                },
                'dataView': {
                    'readOnly': False
                },
                'magicType': {
                    'type': ['line', 'bar']
                },
                'restore': {},
                'saveAsImage': {}
            }
        },
        'visualMap': [
            {
                'show': False,
                'type': 'continuous',
                'seriesIndex': 0,
                'min': -80,
                'max': 300,
                'inRange': {
                    'color': ['#ff0000', '#ffff00', '#00ff00', '#3399ff'],
                },
            },
        ],
        'xAxis': {
            'type': 'category',
            'boundaryGap': False,
            'data': x_series
        },
        'yAxis': [
            {
                'type': 'value',
                'name': 'equity',
                'axisLabel': {
                    'formatter': '{value} %'
                }
            },
            {
                'name': 'drawdown',
                'nameLocation': 'start',
                # 'inverse': True,
                'max': 0,
                'axisLabel': {
                    'formatter': '{value} %'
                }
            }
        ],
        'dataZoom': [{
            'type': 'inside',
            'start': 0,
            'end': 100
        }, {
            'show': True,
            'type': 'slider',
            'top': '90%',
            'start': 0,
            'end': 100
        }],
        'series': [{
            'name': 'equity_curve',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 0,
            'data': equity_series,
            'markPoint': {
                'data': [{
                    'type': 'max',
                    'name': 'Max'
                }, {
                    'type': 'min',
                    'name': 'Min'
                }],
                'symbolSize':
                    60,
            }
        }, {
            'name': 'drawdown',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 1,
            'data': drawdown_series,
        }]
    }
    return {'status': 0, 'msg': '', 'data': equity_data}


# 获取deribit账户的资金曲线
def get_deribit_account_balance_echarts(strategy):
    engine = create_engine(sql_uri)
    sql = f'select * from deribit_{strategy}_value'
    try:
        df = pd.read_sql(sql, con=engine, index_col='index')
    except:
        return {'status': 0, 'msg': '', 'data': {}}

    df['ctime'] = df['candle_begin_time'].apply(
        lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))

    x_series = list(df['ctime'])
    equity_series = list(df['equity_usd'])
    btc_series = list(df['BTC_usd'])
    eth_series = list(df['ETH_usd'])
    sol_series = list(df['SOL_usd'])
    usdc_series = list(df['USDC_usd'])

    equity_data = {
        'title': {
            'text': '账户净值曲线'
        },
        'tooltip': {
            'trigger': 'axis'
        },
        'legend': {},
        'toolbox': {
            'show': True,
            'feature': {
                'dataZoom': {
                    'yAxisIndex': 'none'
                },
                'dataView': {
                    'readOnly': False
                },
                'magicType': {
                    'type': ['line', 'bar']
                },
                'restore': {},
                'saveAsImage': {}
            }
        },
        'visualMap': [],
        'xAxis': {
            'type': 'category',
            'boundaryGap': False,
            'data': x_series
        },
        'yAxis': [{
            'type': 'value',
            'name': 'equity',
            'axisLabel': {
                'formatter': '{value}'
            }
        }],
        'dataZoom': [{
            'type': 'inside',
            'start': 0,
            'end': 100
        }, {
            'show': True,
            'type': 'slider',
            'top': '90%',
            'start': 0,
            'end': 100
        }],
        'series': [{
            'name': 'equity_usd',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 0,
            'data': equity_series,
        }, {
            'name': 'BTC',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 0,
            'data': btc_series,
        }, {
            'name': 'ETH',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 0,
            'data': eth_series,
        }, {
            'name': 'SOL',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 0,
            'data': sol_series,
        }, {
            'name': 'USDC',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 0,
            'data': usdc_series,
        }]
    }
    return {'status': 0, 'msg': '', 'data': equity_data}


def get_deribit_index_echarts(exchange, symbol):
    if exchange is None or symbol == '':
        return {'status': 0, 'msg': '', 'data': {}}
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(days=365)
    df = get_kline(exchange, f'{symbol}USDT', '1d', 365, start)

    df['ctime'] = df['candle_begin_time'].apply(
        lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))

    x_series = list(df['ctime'])
    price_series = list(df['close'])

    equity_data = {
        'title': {
            'text': f'{symbol} 价格曲线'
        },
        'tooltip': {
            'trigger': 'axis'
        },
        'legend': {},
        'toolbox': {
            'show': True,
            'feature': {
                'dataZoom': {
                    'yAxisIndex': 'none'
                },
                'dataView': {
                    'readOnly': False
                },
                'magicType': {
                    'type': ['line', 'bar']
                },
                'restore': {},
                'saveAsImage': {}
            }
        },
        'visualMap': [],
        'xAxis': {
            'type': 'category',
            'boundaryGap': False,
            'data': x_series
        },
        'yAxis': [{
            'type': 'value',
            'name': 'price',
            'axisLabel': {
                'formatter': '{value}'
            }
        }],
        'dataZoom': [{
            'type': 'inside',
            'start': 0,
            'end': 100
        }, {
            'show': True,
            'type': 'slider',
            'top': '90%',
            'start': 0,
            'end': 100
        }],
        'series': [{
            'name': 'index_price',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 0,
            'data': price_series,
        }]
    }
    return {'status': 0, 'msg': '', 'data': equity_data}


def get_deribit_dvol_echarts(exchange, symbol):
    if exchange is None or symbol == '':
        return {'status': 0, 'msg': '', 'data': {}}
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    end = int(now.timestamp()) * 1000
    start = int((now - timedelta(days=365)).timestamp()) * 1000
    params = {
        'currency': symbol,
        'start_timestamp': start,
        'end_timestamp': end,
        'resolution': '1D'
    }
    res = exchange.public_get_get_volatility_index_data(params)['result']
    df = pd.DataFrame(
        res['data'],
        columns=['candle_begin_time', 'open', 'high', 'low', 'close'],
        dtype=float)
    # 兼容时区
    utc_offset = int(time.localtime().tm_gmtoff / 60 / 60)
    # 整理数据
    df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'],
                                             unit='ms') + pd.Timedelta(
        hours=utc_offset)  # 时间转化为东八区
    df['ctime'] = df['candle_begin_time'].apply(
        lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))

    x_series = list(df['ctime'])
    dvol_series = list(df['close'])

    equity_data = {
        'title': {
            'text': f'{symbol} dvol波动率曲线'
        },
        'tooltip': {
            'trigger': 'axis'
        },
        'legend': {},
        'toolbox': {
            'show': True,
            'feature': {
                'dataZoom': {
                    'yAxisIndex': 'none'
                },
                'dataView': {
                    'readOnly': False
                },
                'magicType': {
                    'type': ['line', 'bar']
                },
                'restore': {},
                'saveAsImage': {}
            }
        },
        'visualMap': [],
        'xAxis': {
            'type': 'category',
            'boundaryGap': False,
            'data': x_series
        },
        'yAxis': [{
            'type': 'value',
            'name': 'DVOL',
            'axisLabel': {
                'formatter': '{value}'
            }
        }],
        'dataZoom': [{
            'type': 'inside',
            'start': 0,
            'end': 100
        }, {
            'show': True,
            'type': 'slider',
            'top': '90%',
            'start': 0,
            'end': 100
        }],
        'series': [{
            'name': 'DVOL',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 0,
            'data': dvol_series,
        }]
    }
    return {'status': 0, 'msg': '', 'data': equity_data}


def get_deribit_history_volatility_echarts(exchange, symbol):
    if exchange is None or symbol == '':
        return {'status': 0, 'msg': '', 'data': {}}
    # params = {'currency': symbol}
    # res = exchange.public_get_get_historical_volatility(params)['result']
    # df = pd.DataFrame(res, columns=['candle_begin_time', 'close'], dtype=float)
    # # 兼容时区
    # utc_offset = int(time.localtime().tm_gmtoff / 60 / 60)
    # # 整理数据
    # df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'],
    #                                          unit='ms') + pd.Timedelta(
    #                                              hours=utc_offset)  # 时间转化为东八区
    df = get_kline(exchange, f'{symbol}USDT', '1d', 1000)
    df = calculate_historical_vols(df, 365)
    df = df[-366:]
    df.reset_index(inplace=True, drop=True)
    df['ctime'] = df['candle_begin_time'].apply(
        lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))

    x_series = list(df['ctime'])
    his_vol_series = list((df['vol_30_day'] * 100).round(2))

    equity_data = {
        'title': {
            'text': f'{symbol} 历史波动率曲线'
        },
        'tooltip': {
            'trigger': 'axis'
        },
        'legend': {},
        'toolbox': {
            'show': True,
            'feature': {
                'dataZoom': {
                    'yAxisIndex': 'none'
                },
                'dataView': {
                    'readOnly': False
                },
                'magicType': {
                    'type': ['line', 'bar']
                },
                'restore': {},
                'saveAsImage': {}
            }
        },
        'visualMap': [],
        'xAxis': {
            'type': 'category',
            'boundaryGap': False,
            'data': x_series
        },
        'yAxis': [{
            'type': 'value',
            'name': 'his_vol',
            'axisLabel': {
                'formatter': '{value}'
            }
        }],
        'dataZoom': [{
            'type': 'inside',
            'start': 0,
            'end': 100
        }, {
            'show': True,
            'type': 'slider',
            'top': '90%',
            'start': 0,
            'end': 100
        }],
        'series': [{
            'name': 'his_vol',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 0,
            'data': his_vol_series,
        }]
    }
    return {'status': 0, 'msg': '', 'data': equity_data}


def get_deribit_crypto_coin_echarts(strategy):
    engine = create_engine(sql_uri)
    sql = f'select * from deribit_{strategy}_value'
    try:
        df = pd.read_sql(sql, con=engine, index_col='index')
    except:
        return {'status': 0, 'msg': '', 'data': {}}

    df['ctime'] = df['candle_begin_time'].apply(
        lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))

    x_series = list(df['ctime'])
    btc_series = list(df['BTC'])
    eth_series = list(df['ETH'])
    sol_series = list(df['SOL'])
    usdc_series = list(df['USDC'])

    equity_data = {
        'title': {
            'text': '账户加密货币数目'
        },
        'tooltip': {
            'trigger': 'axis'
        },
        'legend': {},
        'toolbox': {
            'show': True,
            'feature': {
                'dataZoom': {
                    'yAxisIndex': 'none'
                },
                'dataView': {
                    'readOnly': False
                },
                'magicType': {
                    'type': ['line', 'bar']
                },
                'restore': {},
                'saveAsImage': {}
            }
        },
        'visualMap': [],
        'xAxis': {
            'type': 'category',
            'boundaryGap': False,
            'data': x_series
        },
        'yAxis': [{
            'type': 'value',
            'name': 'equity',
            'axisLabel': {
                'formatter': '{value}'
            }
        }],
        'dataZoom': [{
            'type': 'inside',
            'start': 0,
            'end': 100
        }, {
            'show': True,
            'type': 'slider',
            'top': '90%',
            'start': 0,
            'end': 100
        }],
        'series': [{
            'name': 'BTC',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 0,
            'data': btc_series,
        }, {
            'name': 'ETH',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 0,
            'data': eth_series,
        }, {
            'name': 'SOL',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 0,
            'data': sol_series,
        }, {
            'name': 'USDC',
            'type': 'line',
            'smooth': True,
            'symbol': 'none',
            'yAxisIndex': 0,
            'data': usdc_series,
        }]
    }
    return {'status': 0, 'msg': '', 'data': equity_data}


def get_echarts_kline(exchange,
                      symbol='BTCUSDT',
                      interval='1h',
                      cta='adapt_bolling',
                      period=55,
                      start_date=None):
    global temp_df, temp_symbol, temp_interval, temp_cta, temp_period, temp_start_date
    if exchange is None or symbol == '' or cta == '' or period == '':
        return {'status': 0, 'msg': '', 'data': {}}
    period = int(period)
    if start_date is not None:
        start_date = datetime.fromtimestamp(int(start_date))
    if temp_symbol == symbol and temp_interval == interval and temp_start_date == start_date and temp_df is not None:
        df = temp_df
    else:
        if symbol.endswith('USDT'):
            df = get_kline(exchange, symbol, interval, 10000, start_date)
        elif symbol.endswith('PERP'):
            df = dapi_get_kline(exchange, symbol, interval, 10000, start_date)
    # 临时变量赋值
    temp_df = df.copy()
    temp_symbol = symbol
    temp_interval = interval
    temp_cta = cta
    temp_period = period
    temp_start_date = start_date

    df['ctime'] = df['candle_begin_time'].apply(
        lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))
    ctime = list(df['ctime'])
    oclh = df[['open', 'close', 'low', 'high']].values.tolist()
    volume = df['volume'].to_list()
    volumes = []
    for i in range(0, len(volume)):
        if oclh[i][0] > oclh[i][1]:
            flag = 1
        else:
            flag = -1
        volumes.append([i, volume[i], flag])

    kline_data = {
        'title': {
            'text': symbol,
            'left': 0
        },
        'legend': {
            'data': [
                'kline', 'ma', 'ema', 'wma', 'ema_2x', 'ema_4x', 'ema_8x',
                'dema', 'upper', 'lower', 'upper2', 'lower2'
            ]
        },
        'grid': [{
            'left': '10%',
            'right': '8%',
            'height': '60%'
        }, {
            'left': '10%',
            'right': '8%',
            'top': '75%',
            'height': '10%'
        }],
        'xAxis': [{
            'type': 'category',
            'data': ctime,
            'boundaryGap': False,
            'axisLine': {
                'onZero': False
            },
            'splitLine': {
                'show': False
            },
            'min': 'dataMin',
            'max': 'dataMax'
        }, {
            'type': 'category',
            'gridIndex': 1,
            'data': ctime,
            'boundaryGap': False,
            'axisLine': {
                'onZero': False
            },
            'axisTick': {
                'show': False
            },
            'splitLine': {
                'show': False
            },
            'axisLabel': {
                'show': False
            },
            'min': 'dataMin',
            'max': 'dataMax'
        }],
        'yAxis': [{
            'scale': True,
            'splitArea': {
                'show': True
            },
        }, {
            'scale': True,
            'gridIndex': 1,
            'splitNumber': 2,
            'axisLabel': {
                'show': False
            },
            'axisLine': {
                'show': False
            },
            'axisTick': {
                'show': False
            },
            'splitLine': {
                'show': False
            }
        }],
        'tooltip': {
            'trigger': 'axis',
            'axisPointer': {
                'type': 'cross'
            }
        },
        'series': [
            {
                'name': 'kline',
                'type': 'candlestick',
                'data': oclh,
                'itemStyle': {
                    'color': '#00da3c',
                    'color0': '#ec0000',
                    'borderColor': '#008F28',
                    'borderColor0': '#8A0000'
                },
                'markPoint': {
                    'symbol':
                        "pin",
                    'symbolSize':
                        50,
                    'data': [{
                        'name': 'highest value',
                        'type': 'max',
                        'valueDim': 'highest',
                        'itemStyle': {
                            'color': "rgba(255, 255, 0, 1)",
                            'borderColor': 'null'
                        },
                        'label': {
                            'color': "rgba(255, 0, 0, 1)",
                            'fontStyle': "italic"
                        }
                    }, {
                        'name': 'lowest value',
                        'type': 'min',
                        'valueDim': 'lowest',
                        'itemStyle': {
                            'color': "rgba(255, 255, 0, 1)",
                            'borderColor': 'null'
                        },
                        'label': {
                            'color': "rgba(255, 0, 0, 1)",
                            'fontStyle': "italic"
                        }
                    }, {
                        'name': 'average value on close',
                        'type': 'average',
                        'valueDim': 'close',
                        'itemStyle': {
                            'color': "rgba(255, 255, 0, 1)",
                            'borderColor': 'null'
                        },
                        'label': {
                            'color': "rgba(255, 0, 0, 1)",
                            'fontStyle': "italic"
                        }
                    }]
                },
                'markLine': {
                    'lineStyle': {
                        'width': 2,
                        'color': "rgba(0, 255, 255, 1)"
                    },
                    'symbol': ['none', 'none'],
                    'data': [[{
                        'name': 'from lowest to highest',
                        'type': 'min',
                        'valueDim': 'lowest',
                        'symbol': 'circle',
                        'symbolSize': 10,
                        'label': {
                            'show': False
                        },
                        'emphasis': {
                            'label': {
                                'show': False
                            }
                        }
                    }, {
                        'type': 'max',
                        'valueDim': 'highest',
                        'symbol': 'circle',
                        'symbolSize': 10,
                        'label': {
                            'show': False
                        },
                        'emphasis': {
                            'label': {
                                'show': False
                            }
                        }
                    }], {
                        'name': 'min line on close',
                        'type': 'min',
                        'valueDim': 'close'
                    }, {
                        'name': 'max line on close',
                        'type': 'max',
                        'valueDim': 'close'
                    }]
                }
            },
            {
                'name': 'Volume',
                'type': 'bar',
                'xAxisIndex': 1,
                'yAxisIndex': 1,
                'data': volumes
            },
        ],
        'dataZoom': [{
            'type': 'inside',
            'xAxisIndex': [0, 1],
            'start': 99,
            'end': 100
        }, {
            'show': True,
            'type': 'slider',
            'xAxisIndex': [0, 1],
            'top': '90%',
            'start': 99,
            'end': 100
        }],
        'visualMap': {
            'show':
                False,
            'seriesIndex':
                1,
            'dimension':
                2,
            'pieces': [{
                'value': 1,
                'color': '#ec0000'
            }, {
                'value': -1,
                'color': '#00da3c'
            }]
        },
    }

    if cta == 'simple_two_mean_close':
        _, short_mean, long_mean, signal_data = simple_two_mean_close(df, period)
        kline_data['series'].extend([{
            'name': 'short_ma',
            'type': 'line',
            'data': short_mean,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'long_ma',
            'type': 'line',
            'data': long_mean,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'adapt_bolling':
        _, median, upper, lower, signal_data = adapt_bolling(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'adapt_bolling_reverse':
        _, median, upper, lower, signal_data = adapt_bolling_reverse(
            df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'adaptboll_with_mtm_v3':
        _, signal_data = adaptboll_with_mtm_v3(df, period)

    if cta == 'ema':
        _, ema_median, signal_data = ema(df, period)
        kline_data['series'].append({
            'name': 'ema',
            'type': 'line',
            'data': ema_median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        })

    if cta == 'ema_multi':
        _, ema_median, ema_2x, ema_4x, ema_8x, signal_data = ema_multi(
            df, period)
        kline_data['series'].extend([{
            'name': 'ema',
            'type': 'line',
            'data': ema_median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'ema_2x',
            'type': 'line',
            'data': ema_2x,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'ema_4x',
            'type': 'line',
            'data': ema_4x,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'ema_8x',
            'type': 'line',
            'data': ema_8x,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'signal_simple_turtle':
        _, ema_median, upper, lower, signal_data = signal_simple_turtle(
            df, period)
        kline_data['series'].extend([{
            'name': 'ema',
            'type': 'line',
            'data': ema_median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'signal_simple_turtle_dema':
        _, ema_median, upper, lower, signal_data = signal_simple_turtle_dema(
            df, period)
        kline_data['series'].extend([{
            'name': 'ema',
            'type': 'line',
            'data': ema_median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'signal_simple_turtle_wma':
        _, ema_median, upper, lower, signal_data = signal_simple_turtle_wma(
            df, period)
        kline_data['series'].extend([{
            'name': 'ema',
            'type': 'line',
            'data': ema_median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'signal_simple_turtle_reverse':
        _, ema_median, upper, lower, signal_data = signal_simple_turtle_reverse(
            df, period)
        kline_data['series'].extend([{
            'name': 'ema',
            'type': 'line',
            'data': ema_median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'signal_atrbolling_bias':
        _, median, upper, lower, signal_data = signal_atrbolling_bias(
            df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'signal_atrbolling_bias_wma':
        _, median, upper, lower, signal_data = signal_atrbolling_bias_wma(
            df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'signal_atrbolling_bias_reverse':
        _, median, upper, lower, signal_data = signal_atrbolling_bias_reverse(
            df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'signal_highlow_bolling':
        _, median, upper, lower, signal_data = signal_highlow_bolling(
            df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'signal_highlow_bolling_wma':
        _, median, upper, lower, signal_data = signal_highlow_bolling_wma(
            df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'signal_adapt_kc':
        _, median, upper, lower, upper2, lower2, signal_data = signal_adapt_kc(
            df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper2',
            'type': 'line',
            'data': upper2,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower2',
            'type': 'line',
            'data': lower2,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'signal_adapt_kc_with_rsi':
        _, median, upper, lower, signal_data = signal_adapt_kc_with_rsi(
            df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'signal_mike':
        _, signal_data = signal_mike(df, period)

    if cta == 'mike_stop_with_bias':
        _, signal_data = mike_stop_with_bias(df, period)

    if cta == 'signal_dc_tunnel':
        _, mean, max, min, signal_data = signal_dc_tunnel(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': mean,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': max,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': min,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'signal_dc_flash_with_stop_lose':
        _, signal_data = signal_dc_flash_with_stop_lose(df, period)

    if cta == 'signal_dual_thrust':
        _, signal_data = signal_dual_thrust(df, period)

    if cta == 'adaptboll_with_cci':
        _, signal_data = adaptboll_with_cci(df, period)

    if cta == 'adaptboll_with_mtm_cci_zdf':
        _, signal_data = adaptboll_with_mtm_cci_zdf(df, period)

    if cta == 'signal_mtmbbw_bolling':
        _, median, upper, lower, signal_data = signal_mtmbbw_bolling(
            df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'mtm_bolling':
        _, median, upper, lower, signal_data = mtm_bolling(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'mtm_dc_tunnel':
        _, mean, max, min, signal_data = mtm_dc_tunnel(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': mean,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': max,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': min,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'mtm_keltner_channel':
        _, median, upper, lower, signal_data = mtm_keltner_channel(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'adx_bolling':
        _, median, upper, lower, signal_data = adx_bolling(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'adx_dc_tunnel':
        _, mean, max, min, signal_data = adx_dc_tunnel(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': mean,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': max,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': min,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'adx_keltner_channel':
        _, median, upper, lower, signal_data = adx_keltner_channel(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'angle_bolling':
        _, median, upper, lower, signal_data = angle_bolling(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'angle_dc_tunnel':
        _, mean, max, min, signal_data = angle_dc_tunnel(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': mean,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': max,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': min,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'angle_keltner_channel':
        _, median, upper, lower, signal_data = angle_keltner_channel(
            df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'amv_bolling':
        _, median, upper, lower, signal_data = amv_bolling(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'amv_dc_tunnel':
        _, mean, max, min, signal_data = amv_dc_tunnel(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': mean,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': max,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': min,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'amv_keltner_channel':
        _, median, upper, lower, signal_data = amv_keltner_channel(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'ar_bolling':
        _, median, upper, lower, signal_data = ar_bolling(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'ar_dc_tunnel':
        _, mean, max, min, signal_data = ar_dc_tunnel(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': mean,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': max,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': min,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'ar_keltner_channel':
        _, median, upper, lower, signal_data = ar_keltner_channel(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'atr_bolling':
        _, median, upper, lower, signal_data = atr_bolling(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'atr_dc_tunnel':
        _, mean, max, min, signal_data = atr_dc_tunnel(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': mean,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': max,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': min,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'atr_keltner_channel':
        _, median, upper, lower, signal_data = atr_keltner_channel(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'bbw_bolling':
        _, median, upper, lower, signal_data = bbw_bolling(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'bbw_dc_tunnel':
        _, mean, max, min, signal_data = bbw_dc_tunnel(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': mean,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': max,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': min,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    if cta == 'bbw_keltner_channel':
        _, median, upper, lower, signal_data = bbw_keltner_channel(df, period)
        kline_data['series'].extend([{
            'name': 'ma',
            'type': 'line',
            'data': median,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'upper',
            'type': 'line',
            'data': upper,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }, {
            'name': 'lower',
            'type': 'line',
            'data': lower,
            'smooth': True,
            'symbol': 'none',
            'lineStyle': {
                'opacity': 0.5
            }
        }])

    kline_data['series'][0]['markPoint']['data'].extend(signal_data)
    return {'status': 0, 'msg': '', 'data': kline_data}


def open_order(exchange, data):
    if exchange is None or data['symbol'] == '':
        return {
            'status': 500,
            'msg': 'params error',
        }

    params = data

    try:
        # res = exchange.fapiPrivate_post_order(params=params)  # 亏损的币种先减仓拉入黑名单
        res = robust(func=exchange.fapiPrivate_post_order,
                     params=params,
                     func_name='open order')
        log_print('下单成功')
    except Exception as e:
        log_print('下单出错')
        log_print(e)
        return {'status': -1, 'msg': str(e)}

    return {'status': 0, 'msg': '下单成功'}


def dapi_open_order(exchange, data):
    if exchange is None or data['symbol'] == '':
        return {
            'status': 500,
            'msg': 'params error',
        }

    params = data

    try:
        res = robust(func=exchange.dapiPrivate_post_order,
                     params=params,
                     func_name='open order')
        log_print('下单成功')
    except Exception as e:
        log_print('下单出错')
        log_print(e)
        return {'status': -1, 'msg': str(e)}

    return {'status': 0, 'msg': '下单成功'}


def get_strategy_exchange_info(exchange, symbol):
    if exchange is None or symbol == '':
        return {
            'status': 500,
            'msg': 'params error',
        }

    min_qty, price_precision = get_exchange_info(exchange)
    last_price = fetch_binance_ticker_data(exchange, symbol)

    return {
        'status': 0,
        'msg': '',
        'data': {
            'min_qty': min_qty[symbol],
            'price_precision': price_precision[symbol],
            'now_price': last_price,
        }
    }


def get_dapi_strategy_exchange_info(exchange, symbol):
    if exchange is None or symbol == '':
        return {
            'status': 500,
            'msg': 'params error',
        }

    price_precision = get_dapi_exchange_info(exchange)
    last_price = fetch_binance_dapi_ticker_data(exchange, symbol)

    return {
        'status': 0,
        'msg': '',
        'data': {
            'price_precision': price_precision[symbol],
            'now_price': last_price,
        }
    }


def get_account_openorders(exchange, account_type=ACCOUNT_TYPE_STANDARD):
    if exchange is None:
        return {'status': 0, 'msg': '', 'data': {'items': []}}
    account = make_binance_account_adapter(exchange, account_type)
    try:
        openorders = account.get_open_orders('um')
    except ccxt.BaseError as e:
        log_print(f'获取U本位当前委托失败: {e}')
        return {'status': 0, 'msg': '获取当前委托失败', 'data': {'items': []}}
    items = []
    # 过滤掉BUSD合约
    for order in openorders:
        if order.get('symbol', '').endswith('BUSD'):
            continue
        items.append(order)
    columns = []
    for order in openorders:
        columns.extend(order.keys())

    columns = list(set(columns))
    columns.sort()
    columns_item = []
    for column in columns:
        columns_item.append({'label': column, 'name': column})
    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'columns': columns_item,
            'total': len(items)
        }
    }


def get_dapi_account_openorders(exchange):
    if exchange is None:
        return {'status': 0, 'msg': '', 'data': {'items': []}}
    openorders = exchange.dapiPrivateGetOpenorders()
    items = []
    # 过滤掉BUSD合约
    for order in openorders:
        items.append(order)
    columns = []
    for order in openorders:
        columns.extend(order.keys())

    columns = list(set(columns))
    columns.sort()
    columns_item = []
    for column in columns:
        columns_item.append({'label': column, 'name': column})
    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'columns': columns_item,
            'total': len(items)
        }
    }


def delete_order(exchange, symbol, orderId):
    if exchange is None or symbol == '' or orderId == '':
        return {
            'status': 500,
            'msg': 'params error',
        }

    params = {'symbol': symbol, 'orderId': int(orderId)}

    try:
        exchange.fapiPrivateDeleteOrder(params)
        log_print('撤单成功')
    except Exception as e:
        log_print('撤单失败')
        log_print(e)
        return {'status': -1, 'msg': str(e)}

    return {'status': 0, 'msg': '撤单成功'}


def dapi_delete_order(exchange, symbol, orderId):
    if exchange is None or symbol == '' or orderId == '':
        return {
            'status': 500,
            'msg': 'params error',
        }

    params = {'symbol': symbol, 'orderId': int(orderId)}

    try:
        exchange.dapiPrivateDeleteOrder(params)
        log_print('撤单成功')
    except Exception as e:
        log_print('撤单失败')
        log_print(e)
        return {'status': -1, 'msg': str(e)}

    return {'status': 0, 'msg': '撤单成功'}


def get_usd_asset_from_earn_account(exchange, need_value, asset):
    # 获取理财信息
    params = {'asset': asset}
    res = exchange.sapi_get_lending_daily_token_position(params)
    if len(res) == 0:
        log_print(f'理财账户的{asset}数量不足')
        return False
    product_id = res[0]['productId']
    usd_amount = float(res[0]['totalAmount'])
    if usd_amount < need_value:
        log_print(f'理财账户的{asset}数量不足')
        return False

    # 保险起见，多提5U出来
    log_print(f'保险起见，多划转5U')
    amount = need_value + 5
    params = {'productId': product_id, 'amount': amount, 'type': 'FAST'}
    try:
        res = exchange.sapi_post_lending_daily_redeem(params)
        if not res:
            log_print(f'从理财账户到现货账户划转 {asset} {amount} 成功')
            return True
    except Exception as e:
        log_print(f'从理财账户到现货账户划转 {asset} {amount} 失败')
        log_print(e)
        return False


def buy_spot_coin(exchange, asset, usd_symbol, usd_num):
    try:
        params = {
            'symbol': f'{asset}{usd_symbol}',
            'side': 'BUY',
            'type': 'MARKET',
            'quoteOrderQty': usd_num
        }
        res = exchange.private_post_order(params)
        log_print(res)
        executed_qty = Decimal(res['executedQty'])
        commission = 0
        for f in res['fills']:
            commission += Decimal(f['commission'])
        return True, executed_qty - commission
    except Exception as e:
        log_print(f'购买现货{asset}{usd_symbol}下单出错')
        log_print(e)
        return False, 0


def sell_spot_coin(exchange, asset, usd_symbol, usd_num):
    try:
        params = {
            'symbol': f'{asset}{usd_symbol}',
            'side': 'SELL',
            'type': 'MARKET',
            'quoteOrderQty': usd_num
        }
        res = exchange.private_post_order(params)
        log_print(res)
        executed_qty = Decimal(res['executedQty'])
        commission = 0
        for f in res['fills']:
            commission += Decimal(f['commission'])
        return True, executed_qty - commission
    except Exception as e:
        log_print(f'卖出现货{asset}{usd_symbol}下单出错')
        log_print(e)
        return False, 0


def spot_transfer_to_dapi_account(exchange, asset, qty):
    try:
        params = {'asset': asset, 'amount': qty, 'type': 3}
        log_print(f'划转{asset} 数量{qty} 至 币本位合约账户')
        res = exchange.sapi_post_futures_transfer(params)
        log_print(res)
        return True
    except Exception as e:
        log_print(f'划转{asset} 数量{qty} 至 币本位合约账户失败')
        log_print(e)
        return False


def dapi_transfer_to_spot_account(exchange, asset, qty):
    try:
        params = {'asset': asset, 'amount': qty, 'type': 4}
        log_print(f'划转{asset} 数量{qty} 至 现货账户')
        res = exchange.sapi_post_futures_transfer(params)
        log_print(res)
        return True
    except Exception as e:
        log_print(f'划转{asset} 数量{qty} 至 现货账户失败')
        log_print(e)
        return False


def spot_account_has_enough_coin(exchange, usd_symbol, coin_num):
    balances = exchange.private_get_account()['balances']
    balance = [x for x in balances if float(x['free']) > 0]
    for b in balance:
        if b['asset'] != usd_symbol:
            continue
        log_print(f'现货账户现有{usd_symbol} {b["free"]}')
        if float(b['free']) > coin_num:
            return True
    return False


def dapi_buy_coin_list_and_transfer(exchange, asset_lists, mode, num, balance):
    msg = {
        'status': 0,
        'msg': []
    }
    asset_lists = asset_lists.split(',')

    for asset in asset_lists:
        try:
            res = dapi_buy_coin_and_transfer(exchange, asset, mode, num, balance)
            if res['status'] == 0:
                msg['msg'].append(f'{asset}购买并转入币本位成功')
        except Exception as e:
            print(e)
            msg['msg'].append(f'{asset}购买并转入币本位失败')

    return msg


def dapi_buy_coin_and_transfer(exchange, asset, mode, num, balance):
    if exchange is None or asset == '' or mode == '' or num == '':
        return {
            'status': 500,
            'msg': 'params error',
        }

    if mode == 'normal':
        usd_num = float(num)
    elif mode == 'until':
        if balance == '':
            return {
                'status': 500,
                'msg': 'params error',
            }

        usd_num = float(num) - float(balance)

    usd_num = Decimal(f'{usd_num:.2f}')
    log_print(f'需获取价值{usd_num}的{asset}')

    if usd_num < 10:
        return {
            'status': 500,
            'msg': '数值错误，最小划转10U的币',
        }

    ticker = exchange.public_get_ticker_price({'symbol':
                                                   f'{asset}USDT'})['price']
    ticker = Decimal(ticker)
    log_print(f'{asset}现货当前价格为{ticker}')
    amount = Decimal(usd_num / ticker)

    # 判断现货账户是否直接有足够的币转入
    if spot_account_has_enough_coin(exchange, asset, amount):
        if spot_transfer_to_dapi_account(exchange, asset, amount):
            return {
                'status': 0,
                'msg': '划转币本位成功',
            }
        else:
            return {
                'status': -1,
                'msg': '划转币本位失败',
            }

    # 判断现货账户的USDT是否够买入
    if spot_account_has_enough_coin(exchange, 'USDT', usd_num):
        ok, qty = buy_spot_coin(exchange, asset, 'USDT', usd_num)
        if ok:
            if spot_transfer_to_dapi_account(exchange, asset, qty):
                return {
                    'status': 0,
                    'msg': '划转币本位成功',
                }
            else:
                return {
                    'status': -1,
                    'msg': '划转币本位失败',
                }
        else:
            return {
                'status': -1,
                'msg': f'购买现货{asset}失败',
            }

    # 说明都不够买入，通过理财账户划转USDT买入
    if get_usd_asset_from_earn_account(exchange, usd_num, 'USDT'):
        ok, qty = buy_spot_coin(exchange, asset, 'USDT', usd_num)
        if ok:
            if spot_transfer_to_dapi_account(exchange, asset, qty):
                return {
                    'status': 0,
                    'msg': '划转币本位成功',
                }
            else:
                return {
                    'status': -1,
                    'msg': '划转币本位失败',
                }
        else:
            return {
                'status': -1,
                'msg': f'购买现货{asset}失败',
            }

    return {
        'status': -1,
        'msg': f'兄弟，实在找不到哪里有钱了，自己看看账户吧',
    }


def dapi_transfer_and_sell_coin(exchange, asset, mode, num, balance):
    if exchange is None or asset == '' or mode == '' or num == '' or balance == '':
        return {
            'status': 500,
            'msg': 'params error',
        }

    if mode == 'normal':
        usd_num = float(num)
    elif mode == 'until':
        usd_num = float(balance) - float(num)

    usd_num = Decimal(f'{usd_num:.2f}')
    log_print(f'需卖出价值{usd_num}的{asset}')

    if usd_num < 10:
        return {
            'status': 500,
            'msg': '数值错误，最小卖出10U的币',
        }

    ticker = exchange.public_get_ticker_price({'symbol':
                                                   f'{asset}USDT'})['price']
    ticker = Decimal(ticker)
    log_print(f'{asset}现货当前价格为{ticker}')
    amount = Decimal((usd_num + 1) / ticker)  # 多划转1U的币出去，防止精度问题导致不够卖

    if dapi_transfer_to_spot_account(exchange, asset, amount):
        ok, qty = sell_spot_coin(exchange, asset, 'USDT', usd_num)
        if ok:
            return {
                'status': 0,
                'msg': '卖出现货成功',
            }
        else:
            return {
                'status': -1,
                'msg': '卖出现货失败，请排查',
            }
    else:
        return {
            'status': -1,
            'msg': f'划转币本位至现货账户失败，划转数量{amount}，请检查余额是否充足',
        }


# cta_usdt表相关操作
def cta_usdt_create_strategy(data):
    try:
        strategy = data['strategy']
        symbol = data['symbol']
        interval = data['interval']
        cta = data['cta']
        period = int(data['period'])
        cta_key = f'{symbol}_{interval}_{cta}_{period}'
        init_value = Decimal(data['init_value'])
        net_value = init_value
        trade_ratio = data['trade_ratio']
        open_tpsl = int(data['open_tpsl'])
        takeprofit_percentage = Decimal(data['takeprofit_percentage'])
        takeprofit_drawdown_percentage = Decimal(
            data['takeprofit_drawdown_percentage'])
        stoploss_percentage = Decimal(data['stoploss_percentage'])

        res = CtaUsdt.query.filter(CtaUsdt.cta_key == cta_key).first()
        if res is not None:
            return {'status': 0, 'msg': 'create cta strategy success'}

        item = CtaUsdt(
            strategy=strategy,
            cta_key=cta_key,
            symbol=symbol,
            interval=interval,
            cta=cta,
            period=period,
            init_value=init_value,
            net_value=net_value,
            trade_ratio=trade_ratio,
            open_tpsl=open_tpsl,
            takeprofit_percentage=takeprofit_percentage,
            takeprofit_drawdown_percentage=takeprofit_drawdown_percentage,
            stoploss_percentage=stoploss_percentage)
        db.session.add(item)
        db.session.commit()
        return {'status': 0, 'msg': 'create cta strategy success'}
    except Exception as e:
        log_print(e)
        return {'status': 500, 'msg': str(e)}


def cta_usdt_update_strategy(data):
    try:
        id = data['id']
        item = CtaUsdt.query.get(id)
        item.trade_ratio = data['trade_ratio']
        item.open_tpsl = int(data['open_tpsl'])
        item.takeprofit_percentage = Decimal(data['takeprofit_percentage'])
        item.takeprofit_drawdown_percentage = Decimal(
            data['takeprofit_drawdown_percentage'])
        item.stoploss_percentage = Decimal(data['stoploss_percentage'])
        db.session.commit()
        return {'status': 0, 'msg': 'update cta strategy success'}
    except Exception as e:
        log_print(e)
        return {'status': 500, 'msg': str(e)}


def cta_usdt_get_trade_info(cta_key):
    try:
        item = CtaUsdt.query.filter(CtaUsdt.cta_key == cta_key).first()
        return {
            'strategy': item.strategy,
            'symbol': item.symbol,
            'signal': item.signal,
            'init_value': item.init_value,
            'net_value': item.net_value,
            'open_price': item.open_price,
            'close_price': item.close_price,
            'trade_ratio': item.trade_ratio,
            'position_amount': item.position_amount,
            'takeprofit_percentage': item.takeprofit_percentage,
            'takeprofit_drawdown_percentage':
                item.takeprofit_drawdown_percentage,
            'stoploss_percentage': item.stoploss_percentage,
            'open_tpsl': item.open_tpsl,
            'interval': item.interval,
        }
    except Exception as e:
        log_print(e)
        send_wechat(str(e))
        return None


def cta_usdt_get_startegy_params_by_cta_key(cta_key):
    try:
        item = CtaUsdt.query.filter(CtaUsdt.cta_key == cta_key).first()
        return item.strategy, item.symbol, item.interval, item.cta, item.period
    except Exception as e:
        log_print(e)
        return None


def cta_usdt_get_all_running_strategy():
    '''
    return: [..., [strategy, symbol, interval, cta,
    period, position_amount, is_tpsl], ...]
    '''
    try:
        params_list = []
        items = CtaUsdt.query.filter(CtaUsdt.is_del == 0,
                                     CtaUsdt.is_running == 1).all()
        for item in items:
            params_list.append([
                item.strategy, item.symbol, item.interval, item.cta,
                item.period, item.position_amount, item.is_tpsl
            ])
        return params_list
    except Exception as e:
        log_print(e)
        return None


def cta_usdt_get_all_running_strategy_cta_keys():
    try:
        cta_keys = []
        items = CtaUsdt.query.filter(CtaUsdt.is_del == 0,
                                     CtaUsdt.is_running == 1).all()
        for item in items:
            cta_keys.append(item.cta_key)
        return cta_keys
    except Exception as e:
        log_print(e)
        return None


def cta_usdt_get_all_need_tpsl_cta_keys():
    try:
        cta_keys = []
        items = CtaUsdt.query.filter(CtaUsdt.is_del == 0,
                                     CtaUsdt.is_running == 1,
                                     CtaUsdt.open_tpsl == 1,
                                     CtaUsdt.signal != 0).all()
        for item in items:
            cta_keys.append(item.cta_key)
        return cta_keys
    except Exception as e:
        log_print(e)
        return None


def cta_usdt_open_limit_order(exchange,
                              symbol,
                              order_amount,
                              min_qty,
                              price_precision,
                              last_price,
                              reduce_only=False):
    if exchange is None or symbol is None:
        return False
    if order_amount == 0:
        return True

    min_notional = get_exchange_info(exchange, use_notional=True)
    twap_amount = 1000  # 默认500刀以上触发拆单
    side = 'BUY' if order_amount > 0 else 'SELL'

    # 计算下单方向、价格
    if order_amount > 0:
        price = last_price * 1.03
    else:
        price = last_price * 0.97

    # 对下单价格这种最小下单精度
    price = float(f'{price:.{price_precision[symbol]}f}')

    order_amount = abs(order_amount)

    twap_order_num = math.floor(order_amount * last_price / twap_amount)
    for i in range(0, twap_order_num):
        if order_amount * last_price < twap_amount + min_notional[symbol]:
            log_print(f'{symbol} 不需要进一步拆单，可直接下单')
            break
        log_print(f'{symbol} twap下单，正在进行第 {i + 1} 次下单')
        quantity = twap_amount / last_price
        quantity = float(f'{quantity:.{min_qty[symbol]}f}')
        log_print(f'本次下单量 = {quantity}')

        # 下单参数
        params = {
            'symbol': symbol,
            'side': side,
            'type': 'LIMIT',
            'price': price,
            'quantity': quantity,
            'clientOrderId': str(time.time()),
            'timeInForce': 'GTC',
            'reduceOnly': reduce_only
        }
        # 下单
        log_print('下单参数：', params)

        try:
            # open_order = exchange.fapiPrivate_post_order(params=params)
            open_order = robust(func=exchange.fapiPrivate_post_order,
                                params=params,
                                func_name='cta_usdt_open_limit_order')
            log_print('下单完成，下单信息：', open_order)
            # send_wechat(f'下单完成，下单信息：{open_order}')
            log_print(f'{symbol} twap下单，正在进行第 {i + 1} 次下单成功')
        except Exception as e:
            log_print('下单出错')
            log_print(e)
            send_wechat(f'下单出错：{str(e)}')
            return False
        order_amount -= quantity
        order_amount = float(f'{order_amount:.{min_qty[symbol]}f}')
        log_print(f'剩余下单量 = {order_amount}')
        time.sleep(2)

    order_amount = float(f'{order_amount:.{min_qty[symbol]}f}')
    log_print(f'残单处理，残单量 = {order_amount}')
    if order_amount == 0 or order_amount * last_price < 5:
        log_print(f'残单下单量为{order_amount}或价值小于5U,无需下单')
        return True
    # 下单参数
    params = {
        'symbol': symbol,
        'side': side,
        'type': 'LIMIT',
        'price': price,
        'quantity': order_amount,
        'clientOrderId': str(time.time()),
        'timeInForce': 'GTC',
        'reduceOnly': reduce_only
    }
    # 下单
    log_print('下单参数：', params)

    try:
        # open_order = exchange.fapiPrivate_post_order(params=params)
        open_order = robust(func=exchange.fapiPrivate_post_order,
                            params=params,
                            func_name='cta_usdt_open_limit_order')
        log_print('下单完成，下单信息：', open_order)
        # send_wechat(f'下单完成，下单信息：{open_order}')
        log_print('残单下单成功')
    except Exception as e:
        log_print('下单出错')
        log_print(e)
        send_wechat(f'下单出错：{str(e)}')
        return False

    return True


def cta_usdt_update_trade_info(cta_key, data):
    try:
        item = CtaUsdt.query.filter(CtaUsdt.cta_key == cta_key).first()
        for key, value in data.items():
            setattr(item, key, value)
        db.session.commit()
        log_print(f'{cta_key}交易信息写入成功')
    except Exception as e:
        log_print(f'{cta_key}交易信息写入失败')
        log_print(e)


def cta_usdt_get_list(symbol, is_running, cta, signal):
    cta_usdt_items = CtaUsdt.query.filter(CtaUsdt.is_del == 0).order_by(
        CtaUsdt.symbol).all()
    items = []
    for c in cta_usdt_items:
        items.append(c.to_dict())

    if len(items) == 0:
        return {'status': 0, 'msg': '', 'data': {'items': []}}

    df = pd.DataFrame(items)
    df['signal_time'].fillna(pd.Timestamp('1970-01-01'), inplace=True)
    if symbol is not None and symbol != '':
        df = df[df['symbol'] == symbol]
    if is_running is not None and is_running != '':
        df = df[df['is_running'] == int(is_running)]
    if cta is not None and cta != '':
        df = df[df['cta'] == cta]
    if signal is not None and signal != '':
        df = df[df['signal'] == int(signal)]
    items = df.to_dict('records')

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def cta_usdt_stop_after(exchange, trade_info, cta_key):
    symbol = trade_info['symbol']
    open_price = trade_info['open_price']  # 策略上次开仓价
    init_value = trade_info['init_value']
    net_value = trade_info['net_value']  # 策略当前净值
    trade_ratio = trade_info['trade_ratio']  # 策略杠杆
    position_amount = trade_info['position_amount']  # 策略当前持仓
    min_qty, price_precision = get_exchange_info(exchange)  # 下单量精度，价格精度
    last_price = fetch_binance_ticker_data(exchange, symbol)  # 最新价格
    if open_price is not None and open_price != Decimal(0):
        net_value = (
                            (Decimal(last_price) / open_price - 1) * trade_info['signal'] *
                            trade_ratio + 1
                    ) * net_value  # 计算最新的net_value，当前价格/开仓价格-1是涨跌幅，根据上一个signal类型及杠杆确定实际盈亏百分比，加1之后乘以之前记录的net_value，得到最新的net_value
    target_amount = 0  # 目标下单量
    order_amount = target_amount - position_amount  # 所需下单量 = 目标下单量 - 当前持仓量
    target_amount = float(f'{target_amount:.{min_qty[symbol]}f}')
    order_amount = float(f'{order_amount:.{min_qty[symbol]}f}')
    log_print(f'标的{symbol}所需下单量={order_amount}')
    # 下单并更新数据库
    if cta_usdt_open_limit_order(exchange, symbol, order_amount, min_qty,
                                 price_precision, last_price):
        log_print(f'{cta_key}下单成功')
        send_wechat(f'{cta_key}下单成功')
        data = {
            'signal': 0,
            'signal_time': datetime.now(),
            'close_price': last_price,
            'profit': net_value - init_value,
            'net_value': net_value,
            'position_amount': target_amount,
            'is_running': 0,
            'is_tpsl': 0,
        }
        log_print(f'交易信息{data}')
        cta_usdt_update_trade_info(cta_key, data)
        send_wechat(f'{cta_key}策略停止成功')
    else:
        log_print(f'{cta_key}停止策略下单函数执行失败')
        send_wechat(f'{cta_key}停止策略下单函数执行失败')


def cta_usdt_tpsl_close_order(exchange, trade_info, cta_key):
    symbol = trade_info['symbol']
    open_price = trade_info['open_price']  # 策略上次开仓价
    init_value = trade_info['init_value']
    net_value = trade_info['net_value']  # 策略当前净值
    trade_ratio = trade_info['trade_ratio']  # 策略杠杆
    position_amount = trade_info['position_amount']  # 策略当前持仓
    min_qty, price_precision = get_exchange_info(exchange)  # 下单量精度，价格精度
    last_price = fetch_binance_ticker_data(exchange, symbol)  # 最新价格
    if open_price is not None and open_price != Decimal(0):
        net_value = (
                            (Decimal(last_price) / open_price - 1) * trade_info['signal'] *
                            trade_ratio + 1
                    ) * net_value  # 计算最新的net_value，当前价格/开仓价格-1是涨跌幅，根据上一个signal类型及杠杆确定实际盈亏百分比，加1之后乘以之前记录的net_value，得到最新的net_value
    target_amount = 0  # 目标下单量
    order_amount = target_amount - position_amount  # 所需下单量 = 目标下单量 - 当前持仓量
    target_amount = float(f'{target_amount:.{min_qty[symbol]}f}')
    order_amount = float(f'{order_amount:.{min_qty[symbol]}f}')
    log_print(f'标的{symbol}所需下单量={order_amount}')
    # 下单并更新数据库
    if cta_usdt_open_limit_order(exchange, symbol, order_amount, min_qty,
                                 price_precision, last_price):
        log_print(f'{cta_key}下单成功')
        send_wechat(f'{cta_key}下单成功')
        data = {
            'signal': 0,
            'signal_time': datetime.now(),
            'close_price': last_price,
            'profit': net_value - init_value,
            'net_value': net_value,
            'position_amount': target_amount,
            'is_running': 1,
            'is_tpsl': 1,
        }
        log_print(f'交易信息{data}')
        cta_usdt_update_trade_info(cta_key, data)
        send_wechat(f'{cta_key}策略止盈止损成功')
        return True
    else:
        log_print(f'{cta_key}策略止盈止损下单函数执行失败')
        send_wechat(f'{cta_key}策略止盈止损下单函数执行失败')
        return False


# cta策略评价相关函数
# 由交易信号产生实际持仓
def position_for_binance_future(df):
    """
    根据signal产生实际持仓。考虑各种不能买入卖出的情况。
    所有的交易都是发生在产生信号的K线的结束时
    :param df:
    :return:
    """

    # ===由signal计算出实际的每天持有仓位
    # 在产生signal的k线结束的时候，进行买入
    df['signal'].fillna(method='ffill', inplace=True)
    df['signal'].fillna(value=0, inplace=True)  # 将初始行数的signal补全为0
    df['pos'] = df['signal'].shift()
    df['pos'].fillna(value=0, inplace=True)  # 将初始行数的pos补全为0

    # # ===对无法买卖的时候做出相关处理
    # # 例如：下午4点清算，无法交易；股票、期货当天涨跌停的时候无法买入；股票的t+1交易制度等等。
    # # 当前周期持仓无法变动的K线
    # condition = (df['candle_begin_time'].dt.hour == 16) & (df['candle_begin_time'].dt.minute == 0)
    # df.loc[condition, 'pos'] = None
    # # pos为空的时，不能买卖，只能和前一周期保持一致。
    # df['pos'].fillna(method='ffill', inplace=True)

    # 在实际操作中，不一定会直接跳过4点这个周期，而是会停止N分钟下单。此时可以注释掉上面的代码。

    # # ===将数据存入hdf文件中
    # # 删除无关中间变量
    # df.drop(['signal'], axis=1, inplace=True)

    return df


# =====计算资金曲线
# okex交割合约（usdt本位）资金曲线
def equity_curve_for_binance_USDT_future_next_open(df,
                                                   slippage=1 / 1000,
                                                   c_rate=4 / 10000,
                                                   leverage_rate=1,
                                                   face_value=0.01,
                                                   min_margin_ratio=1 / 100):
    """
    okex交割合约（usdt本位）资金曲线
    开仓价格是下根K线的开盘价，可以是其他的形式
    相比之前杠杆交易的资金曲线函数，逻辑简单很多：手续费的处理、爆仓的处理等。
    在策略中增加滑点的。滑点的处理和手续费是不同的。
    :param df:
    :param slippage:  滑点 ，可以用百分比，也可以用固定值。建议币圈用百分比，股票用固定值
    :param c_rate:  手续费，commission fees，默认为万分之5。不同市场手续费的收取方法不同，对结果有影响。比如和股票就不一样。
    :param leverage_rate:  杠杆倍数
    :param face_value:  一张合约的面值，0.01BTC
    :param min_margin_ratio: 最低保证金率，低于就会爆仓
    :return:
    """
    # =====下根k线开盘价
    df['next_open'] = df['open'].shift(-1)  # 下根K线的开盘价
    df['next_open'].fillna(value=df['close'], inplace=True)

    # =====找出开仓、平仓的k线
    condition1 = df['pos'] != 0  # 当前周期不为空仓
    condition2 = df['pos'] != df['pos'].shift(1)  # 当前周期和上个周期持仓方向不一样。
    open_pos_condition = condition1 & condition2

    condition1 = df['pos'] != 0  # 当前周期不为空仓
    condition2 = df['pos'] != df['pos'].shift(-1)  # 当前周期和下个周期持仓方向不一样。
    close_pos_condition = condition1 & condition2

    # =====对每次交易进行分组
    df.loc[open_pos_condition, 'start_time'] = df['candle_begin_time']
    df['start_time'].fillna(method='ffill', inplace=True)
    df.loc[df['pos'] == 0, 'start_time'] = pd.NaT

    # =====开始计算资金曲线
    initial_cash = 100000000  # 初始资金，默认为10000元
    # ===在开仓时
    # 在open_pos_condition的K线，以开盘价计算买入合约的数量。（当资金量大的时候，可以用5分钟均价）
    df.loc[open_pos_condition,
    'contract_num'] = initial_cash * leverage_rate / (face_value *
                                                      df['open'])
    df['contract_num'] = np.floor(df['contract_num'])  # 对合约张数向下取整
    # 开仓价格：理论开盘价加上相应滑点
    df.loc[open_pos_condition,
    'open_pos_price'] = df['open'] * (1 + slippage * df['pos'])
    # 开仓之后剩余的钱，扣除手续费
    df['cash'] = initial_cash - df['open_pos_price'] * face_value * df[
        'contract_num'] * c_rate  # 即保证金

    # ===开仓之后每根K线结束时
    # 买入之后cash，contract_num，open_pos_price不再发生变动
    for _ in ['contract_num', 'open_pos_price', 'cash']:
        df[_].fillna(method='ffill', inplace=True)
    df.loc[df['pos'] == 0, ['contract_num', 'open_pos_price', 'cash']] = None

    # ===在平仓时
    # 平仓价格
    df.loc[close_pos_condition,
    'close_pos_price'] = df['next_open'] * (1 - slippage * df['pos'])
    # 平仓之后剩余的钱，扣除手续费
    df.loc[close_pos_condition, 'close_pos_fee'] = df[
                                                       'close_pos_price'] * face_value * df['contract_num'] * c_rate

    # ===计算利润
    # 开仓至今持仓盈亏
    df['profit'] = face_value * df['contract_num'] * (
            df['close'] - df['open_pos_price']) * df['pos']
    # 平仓时理论额外处理
    df.loc[close_pos_condition, 'profit'] = face_value * df['contract_num'] * (
            df['close_pos_price'] - df['open_pos_price']) * df['pos']
    # 账户净值
    df['net_value'] = df['cash'] + df['profit']

    # ===计算爆仓
    # 至今持仓盈亏最小值
    df.loc[df['pos'] == 1, 'price_min'] = df['low']
    df.loc[df['pos'] == -1, 'price_min'] = df['high']
    df['profit_min'] = face_value * df['contract_num'] * (
            df['price_min'] - df['open_pos_price']) * df['pos']
    # 账户净值最小值
    df['net_value_min'] = df['cash'] + df['profit_min']
    # 计算保证金率
    df['margin_ratio'] = df['net_value_min'] / (
            face_value * df['contract_num'] * df['price_min'])
    # 计算是否爆仓
    df.loc[df['margin_ratio'] <= (min_margin_ratio + c_rate), '是否爆仓'] = 1

    # ===平仓时扣除手续费
    df.loc[close_pos_condition, 'net_value'] -= df['close_pos_fee']
    # 应对偶然情况：下一根K线开盘价格价格突变，在平仓的时候爆仓。此处处理有省略，不够精确。
    df.loc[close_pos_condition & (df['net_value'] < 0), '是否爆仓'] = 1

    # ===对爆仓进行处理
    df['是否爆仓'] = df.groupby('start_time')['是否爆仓'].fillna(method='ffill')
    df.loc[df['是否爆仓'] == 1, 'net_value'] = 0

    # =====计算资金曲线
    df['equity_change'] = df['net_value'].pct_change()
    df.loc[open_pos_condition,
    'equity_change'] = df.loc[open_pos_condition,
    'net_value'] / initial_cash - 1  # 开仓日的收益率
    df['equity_change'].fillna(value=0, inplace=True)
    df['equity_curve'] = (1 + df['equity_change']).cumprod()

    # =====删除不必要的数据，并存储
    df.drop([
        'next_open', 'contract_num', 'open_pos_price', 'cash',
        'close_pos_price', 'close_pos_fee', 'profit', 'net_value', 'price_min',
        'profit_min', 'net_value_min', 'margin_ratio', '是否爆仓'
    ],
        axis=1,
        inplace=True)

    return df


# ======= 策略评价 =========
# 将资金曲线数据，转化为交易数据
def transfer_equity_curve_to_trade(equity_curve):
    """
    将资金曲线数据，转化为一笔一笔的交易
    :param equity_curve: 资金曲线函数计算好的结果，必须包含pos
    :return:
    """
    # =选取开仓、平仓条件
    condition1 = equity_curve['pos'] != 0
    condition2 = equity_curve['pos'] != equity_curve['pos'].shift(1)
    open_pos_condition = condition1 & condition2

    # =计算每笔交易的start_time
    if 'start_time' not in equity_curve.columns:
        equity_curve.loc[open_pos_condition,
        'start_time'] = equity_curve['candle_begin_time']
        equity_curve['start_time'].fillna(method='ffill', inplace=True)
        equity_curve.loc[equity_curve['pos'] == 0, 'start_time'] = pd.NaT

    # =对每次交易进行分组，遍历每笔交易
    trade = pd.DataFrame()  # 计算结果放在trade变量中
    for _index, group in equity_curve.groupby('start_time'):
        # 记录每笔交易
        # 本次交易方向
        trade.loc[_index, 'signal'] = group['pos'].iloc[0]

        # 本次交易杠杆倍数
        if 'leverage_rate' in group:
            trade.loc[_index, 'leverage_rate'] = group['leverage_rate'].iloc[0]

        g = group[group['pos'] != 0]  # 去除pos=0的行
        # 本次交易结束那根K线的开始时间
        trade.loc[_index, 'end_bar'] = g.iloc[-1]['candle_begin_time']
        # 开仓价格
        trade.loc[_index, 'start_price'] = g.iloc[0]['open']
        # 平仓信号的价格
        trade.loc[_index, 'end_price'] = g.iloc[-1]['close']
        # 持仓k线数量
        trade.loc[_index, 'bar_num'] = g.shape[0]
        # 本次交易收益
        trade.loc[_index, 'change'] = (group['equity_change'] + 1).prod() - 1
        # 本次交易结束时资金曲线
        trade.loc[_index, 'end_equity_curve'] = g.iloc[-1]['equity_curve']
        # 本次交易中资金曲线最低值
        trade.loc[_index, 'min_equity_curve'] = g['equity_curve'].min()
    return trade


# 计算策略评价指标
def strategy_evaluate(equity_curve, trade):
    """
    :param equity_curve: 带资金曲线的df
    :param trade: transfer_equity_curve_to_trade的输出结果，每笔交易的df
    :return:
    """

    # ===新建一个dataframe保存回测指标
    results = pd.DataFrame()

    # ===计算累积净值
    results.loc[0, '累积净值'] = round(equity_curve['equity_curve'].iloc[-1], 2)

    # ===计算年化收益
    annual_return = (equity_curve['equity_curve'].iloc[-1] /
                     equity_curve['equity_curve'].iloc[0]) ** (
                            '1 days 00:00:00' /
                            (equity_curve['candle_begin_time'].iloc[-1] -
                             equity_curve['candle_begin_time'].iloc[0]) * 365) - 1
    results.loc[0, '年化收益'] = str(round(annual_return, 2)) + ' 倍'

    # ===计算最大回撤，最大回撤的含义：《如何通过3行代码计算最大回撤》https://mp.weixin.qq.com/s/Dwt4lkKR_PEnWRprLlvPVw
    # 计算当日之前的资金曲线的最高点
    equity_curve['max2here'] = equity_curve['equity_curve'].expanding().max()
    # 计算到历史最高值到当日的跌幅，drowdwon
    equity_curve['dd2here'] = equity_curve['equity_curve'] / equity_curve[
        'max2here'] - 1
    # 计算最大回撤，以及最大回撤结束时间
    end_date, max_draw_down = tuple(
        equity_curve.sort_values(by=['dd2here']).iloc[0][[
            'candle_begin_time', 'dd2here'
        ]])
    # 计算最大回撤开始时间
    start_date = equity_curve[
        equity_curve['candle_begin_time'] <= end_date].sort_values(
        by='equity_curve', ascending=False).iloc[0]['candle_begin_time']
    # 将无关的变量删除
    equity_curve.drop(['max2here', 'dd2here'], axis=1, inplace=True)
    results.loc[0, '最大回撤'] = format(max_draw_down, '.2%')
    results.loc[0, '最大回撤开始时间'] = str(start_date)
    results.loc[0, '最大回撤结束时间'] = str(end_date)

    # ===年化收益/回撤比
    results.loc[0, '年化收益回撤比'] = round(abs(annual_return / max_draw_down), 2)

    # ===统计每笔交易
    results.loc[0, '盈利笔数'] = len(trade.loc[trade['change'] > 0])  # 盈利笔数
    results.loc[0, '亏损笔数'] = len(trade.loc[trade['change'] <= 0])  # 亏损笔数
    results.loc[0, '胜率'] = format(results.loc[0, '盈利笔数'] / len(trade),
                                    '.2%')  # 胜率

    results.loc[0, '每笔交易平均盈亏'] = format(trade['change'].mean(),
                                                '.2%')  # 每笔交易平均盈亏
    results.loc[0, '盈亏收益比'] = round(trade.loc[trade['change'] > 0]['change'].mean() / \
                                         trade.loc[trade['change'] < 0]['change'].mean() * (-1), 2)  # 盈亏比
    results.loc[0, '单笔最大盈利'] = format(trade['change'].max(), '.2%')  # 单笔最大盈利
    results.loc[0, '单笔最大亏损'] = format(trade['change'].min(), '.2%')  # 单笔最大亏损

    # ===统计持仓时间，会比实际时间少一根K线的是距离
    trade['持仓时间'] = trade['end_bar'] - trade.index
    max_days, max_seconds = trade['持仓时间'].max().days, trade['持仓时间'].max(
    ).seconds
    max_hours = max_seconds // 3600
    max_minute = (max_seconds - max_hours * 3600) // 60
    results.loc[0, '单笔最长持有时间'] = str(max_days) + ' 天 ' + str(
        max_hours) + ' 小时 ' + str(max_minute) + ' 分钟'  # 单笔最长持有时间

    min_days, min_seconds = trade['持仓时间'].min().days, trade['持仓时间'].min(
    ).seconds
    min_hours = min_seconds // 3600
    min_minute = (min_seconds - min_hours * 3600) // 60
    results.loc[0, '单笔最短持有时间'] = str(min_days) + ' 天 ' + str(
        min_hours) + ' 小时 ' + str(min_minute) + ' 分钟'  # 单笔最短持有时间

    mean_days, mean_seconds = trade['持仓时间'].mean().days, trade['持仓时间'].mean(
    ).seconds
    mean_hours = mean_seconds // 3600
    mean_minute = (mean_seconds - mean_hours * 3600) // 60
    results.loc[0, '平均持仓周期'] = str(mean_days) + ' 天 ' + str(
        mean_hours) + ' 小时 ' + str(mean_minute) + ' 分钟'  # 平均持仓周期

    # ===连续盈利亏算
    results.loc[0, '最大连续盈利笔数'] = max([
        len(list(v))
        for k, v in itertools.groupby(np.where(trade['change'] > 0, 1, np.nan))
    ])  # 最大连续盈利笔数
    results.loc[0, '最大连续亏损笔数'] = max([
        len(list(v))
        for k, v in itertools.groupby(np.where(trade['change'] < 0, 1, np.nan))
    ])  # 最大连续亏损笔数

    # ===每月收益率
    equity_curve.set_index('candle_begin_time', inplace=True)
    monthly_return = equity_curve[[
        'equity_change'
    ]].resample(rule='M').apply(lambda x: f'{((1 + x).prod() - 1) * 100:.2f}%')

    return results.T, monthly_return


def get_cta_usdt_evaluate_params(exchange,
                                 symbol='BTCUSDT',
                                 interval='1h',
                                 cta='adapt_bolling',
                                 period=55,
                                 switch='no',
                                 start_date=None):
    global temp_df, temp_symbol, temp_interval, temp_cta, temp_period, temp_start_date
    if exchange is None or symbol == '' or 'cta' == '' or switch != 'yes' or period == '':
        return {
            'status': 0,
            'msg': '',
            'data': {
                'rows': [{
                    'key': '过于先进',
                    'value': '不便展示'
                }]
            }
        }
    period = int(period)

    face_value = 1
    if start_date is not None:
        start_date = datetime.fromtimestamp(int(start_date))
    if temp_symbol == symbol and temp_interval == interval and temp_start_date == start_date and temp_df is not None:
        df = temp_df
    else:
        if symbol.endswith('USDT'):
            min_qty, price_precision = get_exchange_info(exchange)
            symbol_qty = min_qty[symbol]
            face_value = 1 / pow(10, symbol_qty)
            face_value = float(f'{face_value:.{min_qty[symbol]}f}')
            df = get_kline(exchange, symbol, interval, 10000, start_date)
        elif symbol.endswith('PERP'):
            df = dapi_get_kline(exchange, symbol, interval, 10000, start_date)
    # 临时变量赋值
    temp_df = df.copy()
    temp_symbol = symbol
    temp_interval = interval
    temp_cta = cta
    temp_period = period
    temp_start_date = start_date
    df, *_ = getattr(factors, cta)(df, period)
    df = position_for_binance_future(df)
    df = equity_curve_for_binance_USDT_future_next_open(df,
                                                        face_value=face_value)
    trade = transfer_equity_curve_to_trade(df)
    r, monthly_return = strategy_evaluate(df, trade)
    rows = []
    r_dict = r.to_dict('spilt')
    r_index = r_dict['index']
    r_data = r_dict['data']
    for i in range(0, len(r_index)):
        rows.append({'key': r_index[i], 'value': r_data[i][0]})
    # monthly_return.reset_index(inplace=True)
    # monthly_return['candle_begin_time'] = monthly_return[
    #     'candle_begin_time'].apply(str)
    # monthly_dict = monthly_return.to_dict()
    # for i in range(0, len(monthly_dict['candle_begin_time'])):
    #     rows.append({
    #         'key': monthly_dict['candle_begin_time'][i],
    #         'value': monthly_dict['equity_change'][i]
    #     })
    return {'status': 0, 'msg': '', 'data': {'count': 0, 'rows': rows}}


def get_cta_usdt_evaluate_monthly_params(exchange,
                                         symbol='BTCUSDT',
                                         interval='1h',
                                         cta='adapt_bolling',
                                         period=55,
                                         switch='no',
                                         start_date=None):
    global temp_df, temp_symbol, temp_interval, temp_cta, temp_period, temp_start_date
    if exchange is None or symbol == '' or 'cta' == '' or switch != 'yes' or period == '':
        return {
            'status': 0,
            'msg': '',
            'data': {
                'rows': [{
                    'key': '过于先进',
                    'value': '不便展示'
                }]
            }
        }
    period = int(period)

    face_value = 1
    if start_date is not None:
        start_date = datetime.fromtimestamp(int(start_date))
    if temp_symbol == symbol and temp_interval == interval and temp_start_date == start_date and temp_df is not None:
        df = temp_df
    else:
        if symbol.endswith('USDT'):
            min_qty, price_precision = get_exchange_info(exchange)
            symbol_qty = min_qty[symbol]
            face_value = 1 / pow(10, symbol_qty)
            face_value = float(f'{face_value:.{min_qty[symbol]}f}')
            df = get_kline(exchange, symbol, interval, 10000, start_date)
        elif symbol.endswith('PERP'):
            df = dapi_get_kline(exchange, symbol, interval, 10000, start_date)
    # 临时变量赋值
    temp_df = df.copy()
    temp_symbol = symbol
    temp_interval = interval
    temp_cta = cta
    temp_period = period
    temp_start_date = start_date
    df, *_ = getattr(factors, cta)(df, period)
    df = position_for_binance_future(df)
    df = equity_curve_for_binance_USDT_future_next_open(df,
                                                        face_value=face_value)
    trade = transfer_equity_curve_to_trade(df)
    r, monthly_return = strategy_evaluate(df, trade)
    rows = []
    # r_dict = r.to_dict('spilt')
    # r_index = r_dict['index']
    # r_data = r_dict['data']
    # for i in range(0, len(r_index)):
    #     rows.append({'key': r_index[i], 'value': r_data[i][0]})
    monthly_return.reset_index(inplace=True)
    monthly_return['candle_begin_time'] = monthly_return[
        'candle_begin_time'].apply(str)
    monthly_dict = monthly_return.to_dict()
    for i in range(0, len(monthly_dict['candle_begin_time'])):
        rows.append({
            'key': monthly_dict['candle_begin_time'][i],
            'value': monthly_dict['equity_change'][i]
        })
    return {'status': 0, 'msg': '', 'data': {'count': 0, 'rows': rows}}


def deribit_open_limit_order(exchange, instrument_name, amount, direction):
    if exchange is None or instrument_name == '':
        return {
            'status': 500,
            'msg': 'params error',
        }

    try:
        # 获取该期权合约的持仓信息
        params = {'instrument_name': instrument_name}
        instrument_params = exchange.public_get_get_instrument(
            params)['result']
        min_qty = int(
            math.log(float(instrument_params['min_trade_amount']), 0.1))
        amount = float(f'{amount:.{min_qty}f}')

        # 获取该期权合约的Ask、Bid
        params = {'instrument_name': instrument_name}
        tickers = exchange.public_get_ticker(params)['result']
        best_bid_price = float(tickers['best_bid_price'])
        best_ask_price = float(tickers['best_ask_price'])
        mark_price = float(tickers['mark_price'])
        log_print(
            f'bid:{best_bid_price} ask:{best_ask_price} mark_price:{mark_price}'
        )

        # 下单
        params = {
            'instrument_name': instrument_name,
            'amount': amount,
            'type': 'limit',
            'time_in_force': 'good_til_cancelled'
        }
        if direction == 'buy':
            params['price'] = best_ask_price
            res = exchange.private_get_buy(params)
        elif direction == 'sell':
            params['price'] = best_bid_price
            res = exchange.private_get_sell(params)

        log_print(res)
        return {
            'status': 0,
            'msg': '下单成功',
        }
    except Exception as e:
        log_print(f'下单失败: {e}')
        return {
            'status': -1,
            'msg': str(e),
        }


def calculate_historical_vols(df, sessions_in_year):
    # calculate first log returns using the open
    log_returns = []
    log_returns.append(np.log(df.loc[0, 'close'] / df.loc[0, 'open']))
    # calculate all but first log returns using close to close
    for index in range(len(df) - 1):
        log_returns.append(
            np.log(df.loc[index + 1, 'close'] / df.loc[index, 'close']))
    df = df.assign(log_returns=log_returns)

    # log returns squared - using high and low - for Parkinson volatility
    high_low_log_returns_squared = []
    for index in range(len(df)):
        high_low_log_returns_squared.append(
            np.log(df.loc[index, 'high'] / df.loc[index, 'low']) ** 2)
    df = df.assign(high_low_log_returns_squared=high_low_log_returns_squared)

    # calculate the 7-day standard deviation and vol
    if len(df) > 6:
        sd_7_day = [np.nan] * 6
        vol_7_day = [np.nan] * 6
        park_vol_7_day = [np.nan] * 6
        for index in range(len(df) - 6):
            sd = np.std(df.loc[index:index + 6, 'log_returns'], ddof=1)
            sd_7_day.append(sd)
            vol_7_day.append(sd * np.sqrt(sessions_in_year))
            park_vol_7_day.append(
                np.sqrt((1 / (4 * 7 * np.log(2)) * sum(
                    df.loc[index:index + 6, 'high_low_log_returns_squared'])))
                * np.sqrt(sessions_in_year))
        df = df.assign(sd_7_day=sd_7_day)
        df = df.assign(vol_7_day=vol_7_day)
        df = df.assign(park_vol_7_day=park_vol_7_day)

    # calculate the 30-day standard deviation and vol
    if len(df) > 29:
        sd_30_day = [np.nan] * 29
        vol_30_day = [np.nan] * 29
        park_vol_30_day = [np.nan] * 29
        for index in range(len(df) - 29):
            sd = np.std(df.loc[index:index + 29, 'log_returns'], ddof=1)
            sd_30_day.append(sd)
            vol_30_day.append(sd * np.sqrt(sessions_in_year))
            park_vol_30_day.append(
                np.sqrt((1 / (4 * 30 * np.log(2)) * sum(
                    df.loc[index:index + 29, 'high_low_log_returns_squared'])))
                * np.sqrt(sessions_in_year))
        df = df.assign(sd_30_day=sd_30_day)
        df = df.assign(vol_30_day=vol_30_day)
        df = df.assign(park_vol_30_day=park_vol_30_day)

    # calculate the 60-day standard deviation and vol
    if len(df) > 59:
        sd_60_day = [np.nan] * 59
        vol_60_day = [np.nan] * 59
        park_vol_60_day = [np.nan] * 59
        for index in range(len(df) - 59):
            sd = np.std(df.loc[index:index + 59, 'log_returns'], ddof=1)
            sd_60_day.append(sd)
            vol_60_day.append(sd * np.sqrt(sessions_in_year))
            park_vol_60_day.append(
                np.sqrt((1 / (4 * 60 * np.log(2)) * sum(
                    df.loc[index:index + 59, 'high_low_log_returns_squared'])))
                * np.sqrt(sessions_in_year))
        df = df.assign(sd_60_day=sd_60_day)
        df = df.assign(vol_60_day=vol_60_day)
        df = df.assign(park_vol_60_day=park_vol_60_day)

    # calculate the 90-day standard deviation and vol
    if len(df) > 89:
        sd_90_day = [np.nan] * 89
        vol_90_day = [np.nan] * 89
        park_vol_90_day = [np.nan] * 89
        for index in range(len(df) - 89):
            sd = np.std(df.loc[index:index + 89, 'log_returns'], ddof=1)
            sd_90_day.append(sd)
            vol_90_day.append(sd * np.sqrt(sessions_in_year))
            park_vol_90_day.append(
                np.sqrt((1 / (4 * 90 * np.log(2)) * sum(
                    df.loc[index:index + 89, 'high_low_log_returns_squared'])))
                * np.sqrt(sessions_in_year))
        df = df.assign(sd_90_day=sd_90_day)
        df = df.assign(vol_90_day=vol_90_day)
        df = df.assign(park_vol_90_day=park_vol_90_day)

    # calculate the 180-day standard deviation and vol
    if len(df) > 179:
        sd_180_day = [np.nan] * 179
        vol_180_day = [np.nan] * 179
        park_vol_180_day = [np.nan] * 179
        for index in range(len(df) - 179):
            sd = np.std(df.loc[index:index + 179, 'log_returns'], ddof=1)
            sd_180_day.append(sd)
            vol_180_day.append(sd * np.sqrt(sessions_in_year))
            park_vol_180_day.append(
                np.sqrt((1 / (4 * 180 * np.log(2)) *
                         sum(df.loc[index:index + 179,
                             'high_low_log_returns_squared']))) *
                np.sqrt(sessions_in_year))
        df = df.assign(sd_180_day=sd_180_day)
        df = df.assign(vol_180_day=vol_180_day)
        df = df.assign(park_vol_180_day=park_vol_180_day)

        return df


# cta_usd通过json添加
def cta_usd_create_strategy_by_json(data):
    try:
        msg = {'status': 0, 'msg': []}
        # data = json.loads(data)
        print("通过json添加策略:", data)
        strategy_list = eval(data['info'])
        print(strategy_list)
        # print("数据:", data['info'])
        strategy = data['strategy']
        open_tpsl = int(data['open_tpsl'])
        takeprofit_percentage = Decimal(data['takeprofit_percentage'])
        takeprofit_drawdown_percentage = Decimal(data['takeprofit_drawdown_percentage'])
        stoploss_percentage = Decimal(data['stoploss_percentage'])

        for single_strategy in strategy_list:
            print(single_strategy)
            symbol = single_strategy['symbol'] + 'USD_PERP'
            interval = single_strategy['interval']
            cta = single_strategy['cta']
            init_value = math.floor(Decimal(single_strategy['init_value']) / len(single_strategy['period']))
            net_value = init_value
            trade_ratio = single_strategy['trade_ratio']
            for single_period in single_strategy['period']:
                print(single_period)
                period = int(single_period)
                cta_key = f'{symbol}_{interval}_{cta}_{period}'
                try:
                    res = CtaUsd.query.filter(CtaUsd.cta_key == cta_key).first()
                    if res is not None:
                        msg['msg'].append(f'{cta_key}策略已经存在')
                    else:
                        item = CtaUsd(
                            strategy=strategy,
                            cta_key=cta_key,
                            symbol=symbol,
                            interval=interval,
                            cta=cta,
                            period=period,
                            init_value=init_value,
                            net_value=net_value,
                            trade_ratio=trade_ratio,
                            open_tpsl=open_tpsl,
                            takeprofit_percentage=takeprofit_percentage,
                            takeprofit_drawdown_percentage=takeprofit_drawdown_percentage,
                            stoploss_percentage=stoploss_percentage
                        )
                        db.session.add(item)
                        db.session.commit()
                        msg['msg'].append(f'{cta_key}策略创建成功!')

                        # 自动对该币种添加半套策略, 默认值0.5
                        if auto_add_re:
                            try:
                                strategy = data['strategy']
                                symbol = data['symbol']
                                cta = 'rebalance'
                                cta_key = f'{symbol}_{cta}'
                                init_value = Decimal(0)
                                net_value = init_value
                                trade_ratio = 0.5

                                res = CtaUsdRebalance.query.filter(
                                    CtaUsdRebalance.cta_key == cta_key).first()
                                if res is None:
                                    item = CtaUsdRebalance(strategy=strategy,
                                                           cta_key=cta_key,
                                                           symbol=symbol,
                                                           cta=cta,
                                                           init_value=init_value,
                                                           net_value=net_value,
                                                           trade_ratio=trade_ratio,
                                                           open_tpsl='0')
                                    db.session.add(item)
                                    db.session.commit()
                                    msg['msg'].append(f'{symbol}半套策略自动创建成功!')
                            except Exception as e:
                                msg['msg'].append(f"{data['strategy']}半套策略创建失败!")
                except Exception as e:
                    msg['msg'].append(f'创建{cta_key}策略出错{e}!')
        return msg
    except Exception as e:
        log_print(e)
        return {'status': 500, 'msg': str(e)}


# cta_usd表相关操作
def cta_usd_create_strategy(data):
    if isinstance(data['period'], str) and (',' in data['period']):
        # 多参数的添加
        period_list = data['period'].split(',')
        msg = {'status': 0, 'msg': []}
        try:
            for period in period_list:
                strategy = data['strategy']
                symbol = data['symbol']
                interval = data['interval']
                cta = data['cta']
                period = int(period)
                cta_key = f'{symbol}_{interval}_{cta}_{period}'
                # init_value = Decimal(data['init_value'])
                init_value = math.floor(Decimal(data['init_value']) / len(period_list))
                net_value = init_value
                trade_ratio = data['trade_ratio']
                open_tpsl = int(data['open_tpsl'])
                takeprofit_percentage = Decimal(data['takeprofit_percentage'])
                takeprofit_drawdown_percentage = Decimal(
                    data['takeprofit_drawdown_percentage'])
                stoploss_percentage = Decimal(data['stoploss_percentage'])

                res = CtaUsd.query.filter(CtaUsd.cta_key == cta_key).first()
                if res is not None:
                    msg['msg'].append(f'{cta_key}策略已存在!')

                item = CtaUsd(
                    strategy=strategy,
                    cta_key=cta_key,
                    symbol=symbol,
                    interval=interval,
                    cta=cta,
                    period=period,
                    init_value=init_value,
                    net_value=net_value,
                    trade_ratio=trade_ratio,
                    open_tpsl=open_tpsl,
                    takeprofit_percentage=takeprofit_percentage,
                    takeprofit_drawdown_percentage=takeprofit_drawdown_percentage,
                    stoploss_percentage=stoploss_percentage)
                db.session.add(item)
                db.session.commit()
                msg['msg'].append(f'{cta_key}策略创建成功!')
            return msg
        except Exception as e:
            log_print(e)
            return {'status': 500, 'msg': str(e)}
    else:
        msg = {'status': 0, 'msg': []}
        try:
            strategy = data['strategy']
            symbol = data['symbol']
            interval = data['interval']
            cta = data['cta']
            period = int(data['period'])
            cta_key = f'{symbol}_{interval}_{cta}_{period}'
            init_value = Decimal(data['init_value'])
            net_value = init_value
            trade_ratio = data['trade_ratio']
            open_tpsl = int(data['open_tpsl'])
            takeprofit_percentage = Decimal(data['takeprofit_percentage'])
            takeprofit_drawdown_percentage = Decimal(
                data['takeprofit_drawdown_percentage'])
            stoploss_percentage = Decimal(data['stoploss_percentage'])

            res = CtaUsd.query.filter(CtaUsd.cta_key == cta_key).first()
            if res is not None:
                msg['msg'].append(f'{cta_key}策略已经存在')

            item = CtaUsd(
                strategy=strategy,
                cta_key=cta_key,
                symbol=symbol,
                interval=interval,
                cta=cta,
                period=period,
                init_value=init_value,
                net_value=net_value,
                trade_ratio=trade_ratio,
                open_tpsl=open_tpsl,
                takeprofit_percentage=takeprofit_percentage,
                takeprofit_drawdown_percentage=takeprofit_drawdown_percentage,
                stoploss_percentage=stoploss_percentage)
            db.session.add(item)
            db.session.commit()
            msg['msg'].append(f'{cta_key}策略创建成功!')
            if auto_add_re:
                try:
                    strategy = data['strategy']
                    symbol = data['symbol']
                    cta = 'rebalance'
                    cta_key = f'{symbol}_{cta}'
                    init_value = Decimal(0)
                    net_value = init_value
                    trade_ratio = 0.5

                    res = CtaUsdRebalance.query.filter(
                        CtaUsdRebalance.cta_key == cta_key).first()
                    if res is None:
                        item = CtaUsdRebalance(strategy=strategy,
                                               cta_key=cta_key,
                                               symbol=symbol,
                                               cta=cta,
                                               init_value=init_value,
                                               net_value=net_value,
                                               trade_ratio=trade_ratio,
                                               open_tpsl='0')
                        db.session.add(item)
                        db.session.commit()
                        msg['msg'].append(f'{symbol}半套策略自动创建成功!')
                except Exception as e:
                    msg['msg'].append(f"{data['strategy']}半套策略创建失败!")
            return msg
        except Exception as e:
            log_print(e)
            return {'status': 500, 'msg': str(e)}


def cta_usd_update_strategy(data):
    try:
        print("1", data)
        id = data['id']
        print(type(data))
        print("2", data)
        print(type(data))
        item = CtaUsd.query.get(id)
        print(item)
        # item.init_value = Decimal(data['init_value'])
        item.trade_ratio = data['trade_ratio']
        item.open_tpsl = int(data['open_tpsl'])
        item.takeprofit_percentage = Decimal(data['takeprofit_percentage'])
        item.takeprofit_drawdown_percentage = Decimal(
            data['takeprofit_drawdown_percentage'])
        item.stoploss_percentage = Decimal(data['stoploss_percentage'])
        db.session.commit()
        return {'status': 0, 'msg': '策略更新成功'}
    except Exception as e:
        log_print(e)
        return {'status': 500, 'msg': str(e)}


def cta_usd_get_trade_info(cta_key):
    try:
        item = CtaUsd.query.filter(CtaUsd.cta_key == cta_key).first()
        return {
            'strategy': item.strategy,
            'symbol': item.symbol,
            'signal': item.signal,
            'init_value': item.init_value,
            'net_value': item.net_value,
            'open_price': item.open_price,
            'close_price': item.close_price,
            'trade_ratio': item.trade_ratio,
            'position_amount': item.position_amount,
            'takeprofit_percentage': item.takeprofit_percentage,
            'takeprofit_drawdown_percentage':
                item.takeprofit_drawdown_percentage,
            'stoploss_percentage': item.stoploss_percentage,
            'open_tpsl': item.open_tpsl,
            'interval': item.interval,
        }
    except Exception as e:
        log_print(e)
        send_wechat(str(e))
        return None


def cta_usd_get_startegy_params_by_cta_key(cta_key):
    try:
        item = CtaUsd.query.filter(CtaUsd.cta_key == cta_key).first()
        return item.strategy, item.symbol, item.interval, item.cta, item.period
    except Exception as e:
        log_print(e)
        return None


def cta_usd_get_all_running_strategy():
    '''
    return: [..., [strategy, symbol, interval, cta,
    period, position_amount, is_tpsl], ...]
    '''
    try:
        params_list = []
        items = CtaUsd.query.filter(CtaUsd.is_del == 0,
                                    CtaUsd.is_running == 1).all()
        for item in items:
            params_list.append([
                item.strategy, item.symbol, item.interval, item.cta,
                item.period, item.position_amount, item.is_tpsl
            ])
        return params_list
    except Exception as e:
        log_print(e)
        return None


def cta_usd_get_all_running_strategy_cta_keys():
    try:
        cta_keys = []
        items = CtaUsd.query.filter(CtaUsd.is_del == 0,
                                    CtaUsd.is_running == 1).all()
        for item in items:
            cta_keys.append(item.cta_key)
        return cta_keys
    except Exception as e:
        log_print(e)
        return None


def cta_usd_get_all_need_tpsl_cta_keys():
    try:
        cta_keys = []
        items = CtaUsd.query.filter(CtaUsd.is_del == 0, CtaUsd.is_running == 1,
                                    CtaUsd.open_tpsl == 1,
                                    CtaUsd.signal != 0).all()
        for item in items:
            cta_keys.append(item.cta_key)
        return cta_keys
    except Exception as e:
        log_print(e)
        return None


def cta_usd_open_limit_order(exchange,
                             symbol,
                             order_amount,
                             price_precision,
                             last_price,
                             reduce_only=False,
                             order_func=None):
    if exchange is None or symbol is None:
        return False
    if order_amount == 0:
        return True

    twap_amount = 50  # 50张以上触发拆弹
    side = 'BUY' if order_amount > 0 else 'SELL'

    # 计算下单方向、价格
    if order_amount > 0:
        price = last_price * 1.03
    else:
        price = last_price * 0.97

    # 对下单价格这种最小下单精度
    price = float(f'{price:.{price_precision[symbol]}f}')

    order_amount = abs(order_amount)
    order_amount = float(f'{order_amount:.0f}')

    twap_order_num = math.floor(order_amount / twap_amount)
    for i in range(0, twap_order_num):
        log_print(f'{symbol} twap下单，正在进行第 {i + 1} 次下单')
        quantity = twap_amount
        log_print(f'本次下单张数 = {quantity}')

        # 下单参数
        params = {
            'symbol': symbol,
            'side': side,
            'type': 'LIMIT',
            'price': price,
            'quantity': quantity,
            'clientOrderId': str(time.time()),
            'timeInForce': 'GTC',
            'reduceOnly': reduce_only
        }
        # 下单
        log_print('下单参数：', params)

        try:
            open_order = robust(func=order_func or exchange.dapiPrivate_post_order,
                                params=params,
                                func_name='cta_usd_open_limit_order')
            log_print('下单完成，下单信息：', open_order)
            # send_wechat(f'下单完成，下单信息：{open_order}')
            log_print(f'{symbol} twap下单，正在进行第 {i + 1} 次下单成功')
        except Exception as e:
            log_print('下单出错')
            log_print(e)
            send_wechat(f'下单出错：{str(e)}')
            return False
        order_amount -= quantity
        order_amount = float(f'{order_amount:.0f}')
        log_print(f'剩余下单张数 = {order_amount}')
        time.sleep(2)

    order_amount = float(f'{order_amount:.0f}')
    log_print(f'残单处理，残单张数 = {order_amount}')
    if order_amount == 0:
        log_print(f'残单下单张数为{order_amount},无需下单')
        return True
    # 下单参数
    params = {
        'symbol': symbol,
        'side': side,
        'type': 'LIMIT',
        'price': price,
        'quantity': order_amount,
        'clientOrderId': str(time.time()),
        'timeInForce': 'GTC',
        'reduceOnly': reduce_only
    }
    # 下单
    log_print('下单参数：', params)

    try:
        open_order = robust(func=order_func or exchange.dapiPrivate_post_order,
                            params=params,
                            func_name='cta_usd_open_limit_order')
        log_print('下单完成，下单信息：', open_order)
        # send_wechat(f'下单完成，下单信息：{open_order}')
        log_print('残单下单成功')
    except Exception as e:
        log_print('下单出错')
        log_print(e)
        send_wechat(f'下单出错：{str(e)}')
        return False

    return True


def cta_usd_update_trade_info(cta_key, data):
    try:
        item = CtaUsd.query.filter(CtaUsd.cta_key == cta_key).first()
        for key, value in data.items():
            setattr(item, key, value)
        db.session.commit()
        log_print(f'{cta_key}交易信息写入成功')
    except Exception as e:
        log_print(f'{cta_key}交易信息写入失败')
        log_print(e)


def cta_usd_get_symbol_all_positions(symbol):
    try:
        position = 0
        items = CtaUsd.query.filter(CtaUsd.symbol == symbol).all()
        for item in items:
            position += item.position
        return position
    except Exception as e:
        log_print(f'获取{symbol}现有策略持仓失败')
        log_print(e)
        return 0


def cta_usd_get_list(symbol, is_running, cta, signal):
    cta_usdt_items = CtaUsd.query.filter(CtaUsd.is_del == 0).order_by(
        CtaUsd.symbol).all()
    items = []
    for c in cta_usdt_items:
        items.append(c.to_dict())

    if len(items) == 0:
        return {'status': 0, 'msg': '', 'data': {'items': []}}

    df = pd.DataFrame(items)
    df['signal_time'].fillna(pd.Timestamp('1970-01-01'), inplace=True)
    if symbol is not None and symbol != '':
        df = df[df['symbol'] == symbol]
    if is_running is not None and is_running != '':
        df = df[df['is_running'] == int(is_running)]
    if cta is not None and cta != '':
        df = df[df['cta'] == cta]
    if signal is not None and signal != '':
        df = df[df['signal'] == int(signal)]
    items = df.to_dict('records')

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def cta_usd_delete_after(exchange, trade_info, cta_key):
    try:
        item = CtaUsd.query.filter(CtaUsd.cta_key == cta_key).first()
        db.session.delete(item)
        db.session.commit()
        log_print(f'{cta_key}策略删除成功')
    except Exception as e:
        log_print(f'{cta_key}策略删除成功')
        log_print(e)


def cta_usd_stop_after(exchange,
                       trade_info,
                       cta_key,
                       account_type=ACCOUNT_TYPE_STANDARD):
    symbol = trade_info['symbol']
    open_price = trade_info['open_price']  # 策略上次开仓价
    init_value = trade_info['init_value']
    net_value = trade_info['net_value']  # 策略当前净值
    trade_ratio = trade_info['trade_ratio']  # 策略杠杆
    position_amount = trade_info['position_amount']  # 策略当前持仓
    price_precision = get_dapi_exchange_info(exchange)  # 下单量精度，价格精度
    last_price = fetch_binance_dapi_ticker_data(exchange, symbol)  # 最新价格
    account = make_binance_account_adapter(exchange, account_type)
    if open_price is not None and open_price != Decimal(0):
        net_value = ((Decimal(last_price) / open_price - 1) *
                     trade_info['signal'] * trade_ratio + 1) * net_value
    target_amount = 0  # 目标下单量
    order_amount = target_amount - position_amount  # 所需下单量 = 目标下单量 - 当前持仓量
    target_amount = float(f'{target_amount:.0f}')
    order_amount = float(f'{order_amount:.0f}')
    log_print(f'标的{symbol}所需下单张数={order_amount}')
    # 下单并更新数据库
    if cta_usd_open_limit_order(exchange, symbol, order_amount,
                                price_precision, last_price,
                                order_func=account.place_cm_order):
        log_print(f'{cta_key}下单成功')
        send_wechat(f'{cta_key}下单成功')
        data = {
            'signal': 0,
            'signal_time': datetime.now(),
            'close_price': last_price,
            'profit': net_value - init_value,
            'net_value': net_value,
            'position_amount': target_amount,
            'is_running': 0,
            'is_tpsl': 0,
        }
        log_print(f'交易信息{data}')
        cta_usd_update_trade_info(cta_key, data)
        send_wechat(f'{cta_key}策略停止成功')
    else:
        log_print(f'{cta_key}停止策略下单函数执行失败')
        send_wechat(f'{cta_key}停止策略下单函数执行失败')


def cta_usd_tpsl_close_order(exchange,
                             trade_info,
                             cta_key,
                             account_type=ACCOUNT_TYPE_STANDARD):
    symbol = trade_info['symbol']
    open_price = trade_info['open_price']  # 策略上次开仓价
    init_value = trade_info['init_value']
    net_value = trade_info['net_value']  # 策略当前净值
    trade_ratio = trade_info['trade_ratio']  # 策略杠杆
    position_amount = trade_info['position_amount']  # 策略当前持仓
    price_precision = get_dapi_exchange_info(exchange)  # 下单量精度，价格精度
    last_price = fetch_binance_dapi_ticker_data(exchange, symbol)  # 最新价格
    account = make_binance_account_adapter(exchange, account_type)
    if open_price is not None and open_price != Decimal(0):
        net_value = ((Decimal(last_price) / open_price - 1) *
                     trade_info['signal'] * trade_ratio + 1) * net_value
    target_amount = 0  # 目标下单量
    order_amount = target_amount - position_amount  # 所需下单量 = 目标下单量 - 当前持仓量
    target_amount = float(f'{target_amount:.0f}')
    order_amount = float(f'{order_amount:.0f}')
    log_print(f'标的{symbol}所需下单张数={order_amount}')
    # 下单并更新数据库
    if cta_usd_open_limit_order(exchange, symbol, order_amount,
                                price_precision, last_price,
                                order_func=account.place_cm_order):
        log_print(f'{cta_key}下单成功')
        send_wechat(f'{cta_key}下单成功')
        data = {
            'signal': 0,
            'signal_time': datetime.now(),
            'close_price': last_price,
            'profit': net_value - init_value,
            'net_value': net_value,
            'position_amount': target_amount,
            'is_running': 1,
            'is_tpsl': 1,
        }
        log_print(f'交易信息{data}')
        cta_usd_update_trade_info(cta_key, data)
        send_wechat(f'{cta_key}策略止盈止损成功')
        return True
    else:
        log_print(f'{cta_key}策略止盈止损下单函数执行失败')
        send_wechat(f'{cta_key}策略止盈止损下单函数执行失败')
        return False


def cta_usd_rebalance_create_strategy(data):
    try:
        strategy = data['strategy']
        symbol = data['symbol']
        cta = data['cta']
        cta_key = f'{symbol}_{cta}'
        init_value = Decimal(0)
        net_value = init_value
        trade_ratio = data['trade_ratio']

        res = CtaUsdRebalance.query.filter(
            CtaUsdRebalance.cta_key == cta_key).first()
        if res is not None:
            return {'status': 0, 'msg': 'create rebalance strategy success'}

        item = CtaUsdRebalance(strategy=strategy,
                               cta_key=cta_key,
                               symbol=symbol,
                               cta=cta,
                               init_value=init_value,
                               net_value=net_value,
                               trade_ratio=trade_ratio,
                               open_tpsl='0')
        db.session.add(item)
        db.session.commit()
        return {'status': 0, 'msg': 'create rebalance strategy success'}
    except Exception as e:
        log_print(e)
        return {'status': 500, 'msg': str(e)}


def cta_usd_rebalance_update_strategy(data):
    try:
        id = data['id']
        item = CtaUsdRebalance.query.get(id)
        item.trade_ratio = data['trade_ratio']
        db.session.commit()
        return {'status': 0, 'msg': 'update rebalance strategy success'}
    except Exception as e:
        log_print(e)
        return {'status': 500, 'msg': str(e)}


def cta_usd_rebalance_update_all_strategy(data):
    msg = {'status': 0, 'msg': []}
    try:
        item_list = CtaUsdRebalance.query.all()
        for item in item_list:
            item.trade_ratio = data['trade_ratio']
            db.session.commit()
            msg['msg'].append(f'{item.symbol}修改套保比例成功!')
        return msg
    except Exception as e:
        log_print(e)
        return {'status': 500, 'msg': str(e)}


def cta_usd_rebalance_get_trade_info(cta_key):
    try:
        item = CtaUsdRebalance.query.filter(
            CtaUsdRebalance.cta_key == cta_key).first()
        return {
            'strategy': item.strategy,
            'symbol': item.symbol,
            'init_value': item.init_value,
            'net_value': item.net_value,
            'trade_ratio': item.trade_ratio,
            'position_amount': item.position_amount,
        }
    except Exception as e:
        log_print(e)
        send_wechat(str(e))
        return None


def cta_usd_rebalance_get_list(symbol, is_running, cta, signal):
    cta_usdt_items = CtaUsdRebalance.query.filter(
        CtaUsdRebalance.is_del == 0).all()
    items = []
    for c in cta_usdt_items:
        items.append(c.to_dict())

    if len(items) == 0:
        return {'status': 0, 'msg': '', 'data': {'items': []}}

    df = pd.DataFrame(items)
    df.sort_values(by=['cta_key'], inplace=True)
    df['signal_time'].fillna(pd.Timestamp('1970-01-01'), inplace=True)
    if symbol is not None:
        df = df[df['symbol'] == symbol]
    if is_running is not None:
        df = df[df['is_running'] == is_running]
    if cta is not None:
        df = df[df['cta'] == cta]
    if signal is not None:
        df = df[df['signal'] == signal]
    items = df.to_dict('records')

    return {
        'status': 0,
        'msg': '',
        'data': {
            'items': items,
            'total': len(items)
        }
    }


def cta_usd_rebalance_get_strategy_rebalance_cta_keys(strategy,
                                                      running_only=False):
    try:
        cta_keys = []
        query = CtaUsdRebalance.query.filter(
            CtaUsdRebalance.strategy == strategy, CtaUsdRebalance.is_del == 0)
        if running_only:
            query = query.filter(CtaUsdRebalance.is_running == 1)
        items = query.all()
        for item in items:
            cta_keys.append(item.cta_key)
        return cta_keys
    except Exception as e:
        log_print(e)
        return []


def cta_usd_rebalance_get_cta_key(strategy, symbol):
    try:
        item = CtaUsdRebalance.query.filter(
            CtaUsdRebalance.strategy == strategy,
            CtaUsdRebalance.symbol == symbol).first()
        return item.cta_key
    except Exception as e:
        log_print(e)
        return None


def cta_usd_rebalance_update_trade_info(cta_key, data):
    try:
        item = CtaUsdRebalance.query.filter(
            CtaUsdRebalance.cta_key == cta_key).first()
        for key, value in data.items():
            setattr(item, key, value)
        db.session.commit()
        log_print(f'{cta_key}交易信息写入成功')
    except Exception as e:
        log_print(f'{cta_key}交易信息写入失败')
        log_print(e)


def cta_usd_rebalance_force_rebalance(exchange, strategy, symbol):
    if exchange is None or strategy == '' or symbol == '':
        return {
            'status': 500,
            'msg': 'params error',
        }

    account = make_binance_account_adapter(exchange,
                                           get_strategy_account_type(strategy))
    account_info = account.get_cm_account()
    assets = account_info['assets']
    # positions = account_info['positions']
    # assets = [s for s in assets if float(s['walletBalance']) > 0]
    # positions = [p for p in positions if float(p['positionAmt']) != 0]
    if len(assets) == 0:
        return {
            'status': 0,
            'msg': '无需执行',
        }

    price_precision = get_dapi_exchange_info(exchange)
    last_price = fetch_binance_dapi_ticker_data(exchange, symbol)

    matched_asset = None
    for s in assets:
        if f'{s["asset"]}USD_PERP' == symbol:
            matched_asset = s
            break
    if matched_asset is None:
        return {
            'status': 0,
            'msg': f'{symbol}没有可半套的币本位资产',
        }
    s = matched_asset
    margin_balance = float(s['marginBalance'])
    margin_balance_usd = margin_balance * last_price

    cta_key = cta_usd_rebalance_get_cta_key(strategy, symbol)
    trade_info = cta_usd_rebalance_get_trade_info(cta_key)
    if trade_info is None:
        log_print(f'{cta_key}强制半套执行出错，请排查')
        send_wechat(f'{cta_key}强制半套执行出错，请排查')
        return {
            'status': -1,
            'msg': '获取trade_info失败',
        }

    qty = margin_balance_usd / 10 if s['asset'] not in [
        'BTC'
    ] else margin_balance_usd / 100
    qty *= float(trade_info['trade_ratio'])
    qty = round(qty)  # 下单数量取整
    need_order_amount = qty - abs(trade_info['position_amount'])
    if need_order_amount == 0:
        log_print(f'{cta_key}强制半套执行完成')
        return {
            'status': 0,
            'msg': '需要下单量为0，无需执行',
        }

    if cta_usd_open_limit_order(exchange,
                                symbol,
                                -need_order_amount,
                                price_precision,
                                last_price,
                                order_func=account.place_cm_order):
        data = {
            'init_value': margin_balance_usd,
            'net_value': margin_balance_usd,
            'position_amount': -qty,
        }
        cta_usd_rebalance_update_trade_info(cta_key, data)
        log_print(f'{cta_key}强制半套执行完成')
    else:
        log_print(f'{cta_key}强制半套执行失败，请排查')
        send_wechat(f'{cta_key}强制半套执行失败，请排查')
    return {
        'status': 0,
        'msg': '强制半套执行成功',
    }


def cta_usd_rebalance_force_all_rebalance(exchange, strategy):
    if exchange is None or strategy == '':
        return {
            'status': 500,
            'msg': 'params error',
        }

    account = make_binance_account_adapter(exchange,
                                           get_strategy_account_type(strategy))
    account_info = account.get_cm_account()
    assets = account_info['assets']

    if len(assets) == 0:
        return {
            'status': 0,
            'msg': '无需执行',
        }

    price_precision = get_dapi_exchange_info(exchange)

    all_msg = {
        'status': 0,
        'msg': [],
    }
    rebalance_list = CtaUsdRebalance.query.filter(
        CtaUsdRebalance.strategy == strategy, CtaUsdRebalance.is_del == 0).all()
    for cta_rebalance in rebalance_list:

        symbol = cta_rebalance.symbol

        last_price = fetch_binance_dapi_ticker_data(exchange, symbol)

        matched_asset = None
        for s in assets:
            if f'{s["asset"]}USD_PERP' == symbol:
                matched_asset = s
                break
        if matched_asset is None:
            all_msg['msg'].append(f'{symbol}没有可半套的币本位资产')
            continue
        s = matched_asset
        margin_balance = float(s['marginBalance'])
        margin_balance_usd = margin_balance * last_price

        cta_key = cta_usd_rebalance_get_cta_key(strategy, symbol)
        trade_info = cta_usd_rebalance_get_trade_info(cta_key)
        if trade_info is None:
            log_print(f'{cta_key}强制半套执行出错，请排查')
            send_wechat(f'{cta_key}强制半套执行出错，请排查')
            all_msg['msg'].append(f'{cta_key}获取trade_info失败')
            continue

        qty = margin_balance_usd / 10 if s['asset'] not in [
            'BTC'
        ] else margin_balance_usd / 100
        qty *= float(trade_info['trade_ratio'])
        qty = round(qty)  # 下单数量取整
        need_order_amount = qty - abs(trade_info['position_amount'])
        if need_order_amount == 0:
            log_print(f'{cta_key}强制半套执行完成')
            all_msg['msg'].append(f'{cta_key}需要下单量为0，无需执行')
            continue

        if cta_usd_open_limit_order(exchange,
                                    symbol,
                                    -need_order_amount,
                                    price_precision,
                                    last_price,
                                    order_func=account.place_cm_order):
            data = {
                'init_value': margin_balance_usd,
                'net_value': margin_balance_usd,
                'position_amount': -qty,
            }
            cta_usd_rebalance_update_trade_info(cta_key, data)
            log_print(f'{cta_key}强制半套执行完成')
            all_msg['msg'].append(f'{cta_key}强制加套执行成功')
        else:
            log_print(f'{cta_key}强制半套执行失败，请排查')
            send_wechat(f'{cta_key}强制半套执行失败，请排查')
            all_msg['msg'].append(f'{cta_key}强制加套执行失败')
    return all_msg


def cta_usd_get_all_rebalance_strategy():
    try:
        params_list = []
        items = CtaUsdRebalance.query.filter(CtaUsdRebalance.is_del == 0).all()
        for item in items:
            params_list.append([
                item.strategy, item.symbol, item.interval, item.cta,
                item.period, item.position_amount
            ])
        return params_list
    except Exception as e:
        log_print(e)
        return None
