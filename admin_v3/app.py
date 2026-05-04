from gevent import pywsgi, monkey

monkey.patch_all()

from datetime import datetime
from flask import Flask, render_template, request, jsonify, make_response, session, g, redirect, url_for, abort
from functions import *
from model import Deribit, Strategy
from schedule_task import *
from concurrent.futures import ThreadPoolExecutor
from exts import db
from auth import authenticate_login
from config import google_key, sql_uri, users, debug, ip_white_list, tpsl_blacklist, alpha_tpsl_time, cta_tpsl_time, super_mm, super_users, super_password

app = Flask(__name__, static_url_path='/')
app.config['JSON_AS_ASCII'] = False
app.config['SQLALCHEMY_DATABASE_URI'] = sql_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SCHEDULER_TIMEZONE'] = 'Asia/Shanghai'
app.config['SESSION_COOKIE_SAMESITE'] = "Lax"

db.init_app(app)
scheduler.init_app(app)

binance_list = []
deribit_list = []
excutor = ThreadPoolExecutor(2)

with app.app_context():
    st = Strategy.query.filter(Strategy.is_del == 0)
    binance_list = get_binance_list(st)
    duck = Deribit.query.filter(Deribit.is_del == 0)
    deribit_list = get_deribit_list(duck)


@app.before_request
def before_request():
    g.user = None
    if 'user_id' in session:
        user = [u for u in users if u.id == session['user_id']][0]
        g.user = user

    client_ip = str(request.remote_addr)
    if not debug:
        if ('*' not in ip_white_list) and (client_ip not in ip_white_list):
            abort(403)


@app.route('/')
def admin():
    if debug:
        return render_template('admin.html')
    if not g.user:
        return redirect(url_for('login'))
    return render_template('admin.html')


@app.route('/admin/schema', methods=['GET'])
def admin_schema():
    res = make_response(render_template('admin.json'))
    res.mimetype = 'application/json'
    res.headers['Cache-Control'] = 'no-store'
    return res


@app.route("/login", methods=['GET', 'POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res
    if request.method == 'POST':
        # 登录操作
        session.pop('user_id', None)
        data = request.get_json()
        username = data['username']
        credential = data['google_code']
        user = authenticate_login(username, credential, users, google_key,
                                  super_mm, super_users, super_password)
        if user:
            session['user_id'] = user.id
            res = make_response(jsonify({'status': 0, 'msg': '请刷新页面'}))
            res = decorate_res(res)
            return res
        else:
            res = make_response(
                jsonify({'status': 500, 'msg': '用户名或验证码/密码错误'}))
            res = decorate_res(res)
            return res
    if request.method == 'GET':
        if g.user:
            return redirect(url_for('admin'))
    return render_template("login.html")


@app.route('/account/add_account', methods=['POST'])
def account_add():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res

    if request.method == 'POST':
        data = request.get_json()
        strategy_update_params(data)
        res = make_response(jsonify(add_account(data)))
        res = decorate_res(res)
        return res


@app.route('/account/refresh', methods=['GET'])
def account_refresh():
    global binance_list, deribit_list
    with app.app_context():
        st = Strategy.query.filter(Strategy.is_del == 0)
        binance_list = get_binance_list(st)
        duck = Deribit.query.filter(Deribit.is_del == 0)
        deribit_list = get_deribit_list(duck)
    res = make_response(jsonify({'status': 0, 'msg': '更新账户列表成功'}))
    res = decorate_res(res)
    return res


@app.route('/account/list', methods=['GET'])
def account_list():
    res = make_response(jsonify(get_account_list(binance_list)))
    res = decorate_res(res)
    return res


@app.route('/account/v2/overview', methods=['GET'])
def account_v2_overview():
    strategy = request.args.get('strategy')
    section = request.args.get('section')
    exchange = get_exchange(binance_list, strategy)
    account_type = get_exchange_account_type(binance_list, strategy)
    overview = get_account_v2_overview(exchange, strategy, account_type)
    if section:
        overview = get_account_v2_overview_section(overview, section)
    res = make_response(jsonify(overview))
    res = decorate_res(res)
    return res


@app.route('/deribit/account/list', methods=['GET'])
def deribit_account_list():
    res = make_response(jsonify(get_account_list(deribit_list)))
    res = decorate_res(res)
    return res


@app.route('/fapi/multiassetsmargin', methods=['GET'])
def fapi_multiassetsmargin():
    strategy = request.args.get('strategy')
    exchange = get_exchange(binance_list, strategy)
    res = make_response(jsonify(set_multiassetsmargin(exchange)))
    res = decorate_res(res)
    return res


@app.route('/api/change_leverage', methods=['GET'])
def api_change_leverage():
    strategy = request.args.get('strategy')
    type = request.args.get('type')
    leverage = request.args.get('leverage')
    exchange = get_exchange(binance_list, strategy)
    res = make_response(jsonify(change_leverage(exchange, type, leverage)))
    res = decorate_res(res)
    return res


@app.route('/api/change_positionside', methods=['GET'])
def api_change_positionside():
    strategy = request.args.get('strategy')
    type = request.args.get('type')
    exchange = get_exchange(binance_list, strategy)
    res = make_response(jsonify(change_positionside_dual(exchange, type)))
    res = decorate_res(res)
    return res


@app.route('/account/margin', methods=['GET'])
def account_margin():
    strategy = request.args.get('strategy')
    exchange = get_exchange(binance_list, strategy)
    account_type = get_exchange_account_type(binance_list, strategy)
    res = make_response(jsonify(get_account_margin(exchange, account_type)))
    res = decorate_res(res)
    return res


@app.route('/account/balance', methods=['GET'])
def account_balance():
    strategy = request.args.get('strategy')
    exchange = get_exchange(binance_list, strategy)
    account_type = get_exchange_account_type(binance_list, strategy)
    res = make_response(jsonify(get_account_balance(exchange, account_type)))
    res = decorate_res(res)
    return res


@app.route('/account_management/balance', methods=['GET'])
def account_management_balance():
    res = make_response(jsonify(get_account_management_balance(binance_list)))
    res = decorate_res(res)
    return res


@app.route('/dapi/account/balance', methods=['GET'])
def dapi_account_balance():
    strategy = request.args.get('strategy')
    exchange = get_exchange(binance_list, strategy)
    account_type = get_exchange_account_type(binance_list, strategy)
    res = make_response(jsonify(get_dapi_account_status(exchange,
                                                        account_type)))
    res = decorate_res(res)
    return res


@app.route('/deribit/account/balance', methods=['GET'])
def deribit_account_balance():
    strategy = request.args.get('strategy')
    exchange = get_exchange(deribit_list, strategy)
    res = make_response(jsonify(get_deribit_account_balance(exchange)))
    res = decorate_res(res)
    return res


@app.route('/subaccount_management/list', methods=['GET'])
def subaccount_management_list():
    exchange = get_main_exchange(binance_list)
    res = make_response(jsonify(get_subaccount_management_list(exchange)))
    res = decorate_res(res)
    return res


@app.route('/account/position', methods=['GET'])
def account_position():
    strategy = request.args.get('strategy')
    exchange = get_exchange(binance_list, strategy)
    account_type = get_exchange_account_type(binance_list, strategy)
    res = make_response(jsonify(get_account_positions_list(exchange,
                                                           account_type)))
    res = decorate_res(res)
    return res


@app.route('/account_management/uni_transfer', methods=['GET'])
def account_management_uni_transfer():
    exchange = get_main_exchange(binance_list)
    fromAccount = request.args.get('fromAccount')
    fromWallet = request.args.get('fromWallet')
    toAccount = request.args.get('toAccount')
    toWallet = request.args.get('toWallet')
    asset = request.args.get('symbol')
    amount = request.args.get('amount')
    fromEmail = get_email(binance_list, fromAccount)
    toEmail = get_email(binance_list, toAccount)

    res = make_response(
        jsonify(
            post_account_management_uni_transfer(exchange, fromEmail,
                                                 fromWallet, toEmail, toWallet,
                                                 asset, amount)))
    res = decorate_res(res)
    return res


@app.route('/account_management/transfer', methods=['GET'])
def account_management_transfer():
    account = request.args.get('account')
    type = request.args.get('type')
    asset = request.args.get('asset')
    amount = request.args.get('amount')
    exchange = get_exchange(binance_list, account)

    res = make_response(
        jsonify(post_account_management_transfer(exchange, asset, type,
                                                 amount)))
    res = decorate_res(res)
    return res


@app.route('/account_management/uni_tranfer_history', methods=['GET'])
def account_management_uni_transfer_history():
    exchange = get_main_exchange(binance_list)
    res = make_response(
        jsonify(get_account_management_uni_transfer_history(exchange)))
    res = decorate_res(res)
    return res


@app.route('/dapi/account/position', methods=['GET'])
def dapi_account_position():
    strategy = request.args.get('strategy')
    exchange = get_exchange(binance_list, strategy)
    account_type = get_exchange_account_type(binance_list, strategy)
    res = make_response(jsonify(get_dapi_account_positions_list(exchange,
                                                                account_type)))
    res = decorate_res(res)
    return res


@app.route('/deribit/account/position', methods=['GET'])
def deribit_account_position():
    strategy = request.args.get('strategy')
    exchange = get_exchange(deribit_list, strategy)
    res = make_response(jsonify(get_deribit_account_positions_list(exchange)))
    res = decorate_res(res)
    return res


@app.route('/all_account/balance', methods=['GET'])
def all_account_balance():
    res = make_response(jsonify(get_all_account_balance(binance_list)))
    res = decorate_res(res)
    return res


@app.route('/all_account/position', methods=['GET'])
def all_account_position():
    res = make_response(jsonify(get_all_account_positions_list(binance_list)))
    res = decorate_res(res)
    return res


@app.route('/fapi/fundingrate', methods=['GET'])
def fapi_fundingrate():
    exchange = get_default_exchange(binance_list)
    res = make_response(jsonify(get_fapi_fundingrate(exchange)))
    res = decorate_res(res)
    return res


@app.route('/fapi/taker_by_ratio', methods=['GET'])
def fapi_taker_by_ratio():
    exchange = get_default_exchange(binance_list)
    res = make_response(jsonify(get_taker_by_ratio(exchange)))
    res = decorate_res(res)
    return res


@app.route('/fapi/bbw_all', methods=['GET'])
def fapi_bbw_all():
    exchange = get_default_exchange(binance_list)
    interval = request.args.get('interval')
    res = make_response(jsonify(get_bbw_for_all(exchange, interval)))
    res = decorate_res(res)
    return res


@app.route('/strategy/get_row', methods=['GET'])
def strategy_row():
    strategy = request.args.get('strategy')
    res = make_response(jsonify(strategy_get_row(strategy)))
    res = decorate_res(res)
    return res


@app.route('/strategy/tpsl/start', methods=['GET'])
def strategy_tpsl_start():
    strategy = request.args.get('strategy')
    exchange = get_exchange(binance_list, strategy)
    account_type = get_exchange_account_type(binance_list, strategy)
    if account_type == 'unified':
        res = make_response({'status': 0, 'msg': '统一账户跳过旧U本位止盈止损监测'})
        res = decorate_res(res)
        return res
    if exchange is not None:
        if alpha_tpsl_time.find('m') >= 0:
            scheduler.add_job(id=f'{strategy}_tpsl',
                              func=alpha_takeprofit_and_stoploss,
                              args=[exchange, strategy],
                              trigger='cron',
                              minute=f"*/{alpha_tpsl_time.split('m')[0]}",
                              misfire_grace_time=300)
        elif alpha_tpsl_time.find('s') >= 0:
            scheduler.add_job(id=f'{strategy}_tpsl',
                              func=alpha_takeprofit_and_stoploss,
                              args=[exchange, strategy],
                              trigger='cron',
                              second=f"*/{alpha_tpsl_time.split('s')[0]}",
                              misfire_grace_time=300)
    res = make_response({'status': 0, 'msg': ''})
    res = decorate_res(res)
    return res


@app.route('/strategy/tpsl/start_all', methods=['GET'])
def strategy_tpsl_start_all():
    for binance in binance_list:
        strategy = binance['strategy']
        exchange = binance['exchange']
        if strategy in tpsl_blacklist or binance.get('account_type') == 'unified':
            continue
        if alpha_tpsl_time.find('m') >= 0:
            scheduler.add_job(id=f'{strategy}_tpsl',
                              func=alpha_takeprofit_and_stoploss,
                              args=[exchange, strategy],
                              trigger='cron',
                              minute=f"*/{alpha_tpsl_time.split('m')[0]}",
                              misfire_grace_time=300)
        elif alpha_tpsl_time.find('s') >= 0:
            scheduler.add_job(id=f'{strategy}_tpsl',
                              func=alpha_takeprofit_and_stoploss,
                              args=[exchange, strategy],
                              trigger='cron',
                              second=f"*/{alpha_tpsl_time.split('s')[0]}",
                              misfire_grace_time=300)
    res = make_response({'status': 0, 'msg': ''})
    res = decorate_res(res)
    return res


@app.route('/strategy/tpsl/stop', methods=['GET'])
def strategy_tpsl_stop():
    strategy = request.args.get('strategy')
    try:
        scheduler.remove_job(f'{strategy}_tpsl')
    except:
        pass
    res = make_response({'status': 0, 'msg': ''})
    res = decorate_res(res)
    return res


@app.route('/strategy/tpsl/stop_all', methods=['GET'])
def strategy_tpsl_stop_all():
    for binance in binance_list:
        strategy = binance['strategy']
        try:
            scheduler.remove_job(f'{strategy}_tpsl')
        except:
            continue
    res = make_response({'status': 0, 'msg': ''})
    res = decorate_res(res)
    return res


@app.route('/strategy/update', methods=['POST', 'OPTIONS'])
def strategy_update():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res

    if request.method == 'POST':
        data = request.get_json()
        strategy_update_params(data)
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res


@app.route('/blacklist/long/list', methods=['GET'])
def backlist_long_list():
    strategy = request.args.get('strategy')
    res = make_response(jsonify(long_backlist_list(strategy)))
    res = decorate_res(res)
    return res


@app.route('/blacklist/long/create', methods=['POST', 'OPTIONS'])
def backlist_long_create():
    strategy = request.args.get('strategy')
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res

    if request.method == 'POST':
        data = request.get_json()
        res = make_response(jsonify(long_backlist_create(strategy, data)))
        res = decorate_res(res)
        return res


@app.route('/blacklist/long/update', methods=['POST', 'OPTIONS'])
def backlist_long_update():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res

    if request.method == 'POST':
        data = request.get_json()
        long_backlist_update(data)
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res


@app.route('/blacklist/long/delete', methods=['GET'])
def backlist_long_delete():
    id = request.args.get('id')
    long_backlist_delete(id)
    res = make_response(jsonify({'status': 0, 'msg': ''}))
    res = decorate_res(res)
    return res


@app.route('/blacklist/short/list', methods=['GET'])
def backlist_short_list():
    strategy = request.args.get('strategy')
    res = make_response(jsonify(short_backlist_list(strategy)))
    res = decorate_res(res)
    return res


@app.route('/blacklist/short/create', methods=['POST', 'OPTIONS'])
def backlist_short_create():
    strategy = request.args.get('strategy')
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res

    if request.method == 'POST':
        data = request.get_json()
        res = make_response(jsonify(short_backlist_create(strategy, data)))
        res = decorate_res(res)
        return res


@app.route('/blacklist/short/update', methods=['POST', 'OPTIONS'])
def backlist_short_update():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res

    if request.method == 'POST':
        data = request.get_json()
        short_backlist_update(data)
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res


@app.route('/blacklist/short/delete', methods=['GET'])
def backlist_short_delete():
    id = request.args.get('id')
    short_backlist_delete(id)
    res = make_response(jsonify({'status': 0, 'msg': ''}))
    res = decorate_res(res)
    return res


@app.route('/strategy/close_order', methods=['GET'])
def strategy_close_order():
    strategy = request.args.get('strategy')
    symbol = request.args.get('symbol')
    exchange = get_exchange(binance_list, strategy)
    res = make_response(jsonify(close_order(exchange, symbol)))
    res = decorate_res(res)
    return res


@app.route('/dapi/strategy/close_order', methods=['GET'])
def dapi_strategy_close_order():
    strategy = request.args.get('strategy')
    symbol = request.args.get('symbol')
    exchange = get_exchange(binance_list, strategy)
    res = make_response(jsonify(dapi_close_order(exchange, symbol)))
    res = decorate_res(res)
    return res


@app.route('/deribit/strategy/close_position', methods=['GET'])
def deribit_strategy_close_position():
    strategy = request.args.get('strategy')
    instrument_name = request.args.get('instrument_name')
    exchange = get_exchange(deribit_list, strategy)
    res = make_response(
        jsonify(deribit_close_position(exchange, instrument_name)))
    res = decorate_res(res)
    return res


@app.route('/strategy/open_order', methods=['POST', 'OPTIONS'])
def strategy_open_order():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res

    if request.method == 'POST':
        strategy = request.args.get('strategy')
        exchange = get_exchange(binance_list, strategy)
        data = request.get_json()
        res = make_response(jsonify(open_order(exchange, data)))
        res = decorate_res(res)
        return res


@app.route('/dapi/strategy/open_order', methods=['POST', 'OPTIONS'])
def dapi_strategy_open_order():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res

    if request.method == 'POST':
        strategy = request.args.get('strategy')
        exchange = get_exchange(binance_list, strategy)
        data = request.get_json()
        res = make_response(jsonify(dapi_open_order(exchange, data)))
        res = decorate_res(res)
        return res


@app.route('/blacklist/symbol_list', methods=['GET'])
def blacklist_symbol_list():
    exchange = get_default_exchange(binance_list)
    res = make_response(jsonify(get_symbol_list(exchange)))
    res = decorate_res(res)
    return res


@app.route('/account_management/same_account_asset_list', methods=['GET'])
def same_account_asset_list():
    account = request.args.get('account')
    type = request.args.get('type')
    exchange = get_exchange(binance_list, account)
    res = make_response(jsonify(get_same_account_asset_list(exchange, type)))
    res = decorate_res(res)
    return res


@app.route('/account_management/asset_list', methods=['GET'])
def asset_list():
    fromAccount = request.args.get('fromAccount')
    fromWallet = request.args.get('fromWallet')
    toWallet = request.args.get('toWallet')
    exchange = get_exchange(binance_list, fromAccount)
    res = make_response(jsonify(get_asset_list(exchange, fromWallet,
                                               toWallet)))
    res = decorate_res(res)
    return res


@app.route('/account_management/same_account_max_free_asset', methods=['GET'])
def same_account_max_free_asset():
    strategy = request.args.get('account')
    exchange = get_exchange(binance_list, strategy)
    type = request.args.get('type')
    asset = request.args.get('asset')
    res = make_response(
        jsonify(get_same_account_max_free_asset(exchange, type, asset)))
    res = decorate_res(res)
    return res


@app.route('/account_management/max_free_asset', methods=['GET'])
def max_free_asset():
    strategy = request.args.get('fromAccount')
    exchange = get_exchange(binance_list, strategy)
    fromWallet = request.args.get('fromWallet')
    asset = request.args.get('symbol')
    res = make_response(
        jsonify(get_max_free_asset(exchange, fromWallet, asset)))
    res = decorate_res(res)
    return res


@app.route('/dapi/symbol_list', methods=['GET'])
def dapi_symbol_list():
    exchange = get_default_exchange(binance_list)
    res = make_response(jsonify(get_dapi_perp_symbol_list(exchange)))
    res = decorate_res(res)
    return res


@app.route('/account/today_orders', methods=['GET'])
def account_today_orders():
    strategy = request.args.get('strategy')
    exchange = get_exchange(binance_list, strategy)
    account_type = get_exchange_account_type(binance_list, strategy)
    res = make_response(jsonify(get_account_today_orders(exchange,
                                                         account_type)))
    res = decorate_res(res)
    return res


@app.route('/dapi/account/today_orders', methods=['GET'])
def dapi_account_today_orders():
    strategy = request.args.get('strategy')
    symbol = request.args.get('symbol')
    exchange = get_exchange(binance_list, strategy)
    account_type = get_exchange_account_type(binance_list, strategy)
    res = make_response(
        jsonify(get_dapi_account_today_orders(exchange, symbol, account_type)))
    res = decorate_res(res)
    return res


@app.route('/echarts/account/balance', methods=['GET'])
def echarts_account_balance():
    strategy = request.args.get('strategy')
    res = make_response(jsonify(get_account_balance_echarts(strategy)))
    res = decorate_res(res)
    return res


@app.route('/echarts/account_management/balance', methods=['GET'])
def echarts_account_management_balance():
    exchange = get_main_exchange(binance_list)
    res = make_response(
        jsonify(get_account_management_balance_echarts(exchange)))
    res = decorate_res(res)
    return res


@app.route('/dapi/echarts/account/balance', methods=['GET'])
def dapi_echarts_account_balance():
    strategy = request.args.get('strategy')
    res = make_response(jsonify(get_dapi_account_balance_echarts(strategy)))
    res = decorate_res(res)
    return res


@app.route('/deribit/echarts/account/balance', methods=['GET'])
def deribit_echarts_account_balance():
    strategy = request.args.get('strategy')
    res = make_response(jsonify(get_deribit_account_balance_echarts(strategy)))
    res = decorate_res(res)
    return res


@app.route('/deribit/echarts/account/crypto', methods=['GET'])
def deribit_echarts_account_crypto():
    strategy = request.args.get('strategy')
    res = make_response(jsonify(get_deribit_crypto_coin_echarts(strategy)))
    res = decorate_res(res)
    return res


@app.route('/deribit/echarts/index', methods=['GET'])
def deribit_echarts_index():
    symbol = request.args.get('symbol')
    exchange = get_default_exchange(binance_list)
    res = make_response(jsonify(get_deribit_index_echarts(exchange, symbol)))
    res = decorate_res(res)
    return res


@app.route('/deribit/echarts/dvol', methods=['GET'])
def deribit_echarts_dvol():
    symbol = request.args.get('symbol')
    exchange = get_default_exchange(deribit_list)
    res = make_response(jsonify(get_deribit_dvol_echarts(exchange, symbol)))
    res = decorate_res(res)
    return res


@app.route('/deribit/echarts/history_vol', methods=['GET'])
def deribit_echarts_history_vol():
    symbol = request.args.get('symbol')
    exchange = get_default_exchange(binance_list)
    res = make_response(
        jsonify(get_deribit_history_volatility_echarts(exchange, symbol)))
    res = decorate_res(res)
    return res


@app.route('/echarts/fapi/bbw', methods=['GET'])
def echarts_fapi_bbw():
    symbol = request.args.get('symbol')
    interval = request.args.get('interval')
    exchange = get_default_exchange(binance_list)
    res = make_response(jsonify(get_bbw_echarts(exchange, symbol, interval)))
    res = decorate_res(res)
    return res


@app.route('/echarts/kline', methods=['GET'])
def echarts_kline():
    strategy = request.args.get('strategy')
    symbol = request.args.get('symbol')
    interval = request.args.get('interval')
    period = request.args.get('period')
    cta = request.args.get('cta')
    start_date = request.args.get('start_date')
    if len(start_date) == 0:
        start_date = None
    exchange = get_exchange(binance_list, strategy)
    res = make_response(
        jsonify(
            get_echarts_kline(exchange, symbol, interval, cta, period,
                              start_date)))
    res = decorate_res(res)
    return res


@app.route('/strategy/exchange_info', methods=['GET'])
def strategy_exchange_info():
    strategy = request.args.get('strategy')
    symbol = request.args.get('symbol')
    exchange = get_exchange(binance_list, strategy)
    res = make_response(jsonify(get_strategy_exchange_info(exchange, symbol)))
    res = decorate_res(res)
    return res


@app.route('/dapi/strategy/exchange_info', methods=['GET'])
def dapi_strategy_exchange_info():
    strategy = request.args.get('strategy')
    symbol = request.args.get('symbol')
    exchange = get_exchange(binance_list, strategy)
    res = make_response(
        jsonify(get_dapi_strategy_exchange_info(exchange, symbol)))
    res = decorate_res(res)
    return res


@app.route('/account/openorders', methods=['GET'])
def account_openorders():
    strategy = request.args.get('strategy')
    exchange = get_exchange(binance_list, strategy)
    account_type = get_exchange_account_type(binance_list, strategy)
    res = make_response(jsonify(get_account_openorders(exchange,
                                                        account_type)))
    res = decorate_res(res)
    return res


@app.route('/dapi/account/openorders', methods=['GET'])
def dapi_account_openorders():
    strategy = request.args.get('strategy')
    exchange = get_exchange(binance_list, strategy)
    res = make_response(jsonify(get_dapi_account_openorders(exchange)))
    res = decorate_res(res)
    return res


@app.route('/strategy/delete_order', methods=['GET'])
def strategy_delete_order():
    strategy = request.args.get('strategy')
    symbol = request.args.get('symbol')
    orderId = request.args.get('orderId')
    exchange = get_exchange(binance_list, strategy)
    res = make_response(jsonify(delete_order(exchange, symbol, orderId)))
    res = decorate_res(res)
    return res


@app.route('/dapi/strategy/delete_order', methods=['GET'])
def dapi_strategy_delete_order():
    strategy = request.args.get('strategy')
    symbol = request.args.get('symbol')
    orderId = request.args.get('orderId')
    exchange = get_exchange(binance_list, strategy)
    res = make_response(jsonify(dapi_delete_order(exchange, symbol, orderId)))
    res = decorate_res(res)
    return res


@app.route('/dapi/buy_coin', methods=['GET'])
def dapi_buy_coin():
    strategy = request.args.get('strategy')
    asset = request.args.get('asset')
    mode = request.args.get('mode')
    num = request.args.get('num')
    balance = request.args.get('balance')
    hedge_ratio = request.args.get('hedge_ratio')
    live_trade_enabled = request.args.get('live_trade_enabled', 0)
    exchange = get_exchange(binance_list, strategy)
    account_type = get_exchange_account_type(binance_list, strategy)
    res = make_response(
        jsonify(dapi_buy_coin_and_transfer(exchange, asset, mode, num,
                                           balance, account_type, strategy,
                                           hedge_ratio, live_trade_enabled)))
    res = decorate_res(res)
    return res


@app.route('/dapi/buy_coin_list', methods=['GET'])
def dapi_buy_coin_list():
    strategy = request.args.get('strategy')
    asset_lists = request.args.get('asset_lists')
    mode = request.args.get('mode')
    num = request.args.get('num')
    balance = request.args.get('balance')
    hedge_ratio = request.args.get('hedge_ratio')
    live_trade_enabled = request.args.get('live_trade_enabled', 0)
    exchange = get_exchange(binance_list, strategy)
    account_type = get_exchange_account_type(binance_list, strategy)
    res = make_response(
        jsonify(dapi_buy_coin_list_and_transfer(exchange, asset_lists, mode, num,
                                   balance, account_type, strategy,
                                   hedge_ratio, live_trade_enabled)))
    res = decorate_res(res)
    return res


@app.route('/cta/unified/margin_rebalance/create_or_update',
           methods=['POST', 'OPTIONS'])
def cta_unified_margin_rebalance_create_or_update():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res
    data = request.get_json() or {}
    res = make_response(jsonify(create_or_update_unified_margin_rebalance(
        data.get('strategy'), data.get('asset'), data.get('hedge_ratio', '0.5'),
        data.get('live_trade_enabled', 0),
        hedge_market=data.get('hedge_market', 'um'),
        buy_mode=data.get('buy_mode', 'cash'),
        margin_side_effect_type=data.get('margin_side_effect_type', ''),
        target_quote_usd=data.get('target_quote_usd', '0'))))
    res = decorate_res(res)
    return res


@app.route('/cta/unified/base_asset/buy/preview',
           methods=['POST', 'OPTIONS'])
def cta_unified_base_asset_buy_preview():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res
    data = request.get_json(silent=True) or request.form or {}
    strategy = data.get('strategy')
    exchange = get_exchange(binance_list, strategy)
    res = make_response(jsonify(preview_unified_base_asset_buy(
        exchange,
        strategy,
        data.get('asset', 'ETH'),
        data.get('quote_usd') or data.get('num') or '0',
        data.get('buy_mode', 'margin'),
        data.get('hedge_ratio', '0.5'))))
    res = decorate_res(res)
    return res


@app.route('/cta/unified/base_asset/buy/execute',
           methods=['POST', 'OPTIONS'])
def cta_unified_base_asset_buy_execute():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res
    data = request.get_json(silent=True) or request.form or {}
    strategy = data.get('strategy')
    exchange = get_exchange(binance_list, strategy)
    res = make_response(jsonify(execute_unified_base_asset_buy(
        exchange,
        strategy,
        data.get('asset', 'ETH'),
        data.get('quote_usd') or data.get('num') or '0',
        data.get('buy_mode', 'margin'),
        data.get('hedge_ratio', '0.5'),
        data.get('live_trade_enabled', 0))))
    res = decorate_res(res)
    return res


@app.route('/cta/unified/margin_rebalance/list', methods=['GET'])
def cta_unified_margin_rebalance_list():
    strategy = request.args.get('strategy')
    asset = request.args.get('asset')
    res = make_response(jsonify(
        cta_unified_margin_rebalance_get_list(binance_list, strategy, asset)))
    res = decorate_res(res)
    return res


@app.route('/cta/unified/margin_rebalance/force',
           methods=['POST', 'OPTIONS'])
def cta_unified_margin_rebalance_force_route():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res
    data = request.get_json() or {}
    strategy = data.get('strategy')
    asset = data.get('asset')
    exchange = get_exchange(binance_list, strategy)
    res = make_response(jsonify(
        cta_unified_margin_rebalance_force(exchange, strategy, asset)))
    res = decorate_res(res)
    return res


@app.route('/dapi/sell_coin', methods=['GET'])
def dapi_sell_coin():
    strategy = request.args.get('strategy')
    asset = request.args.get('asset')
    mode = request.args.get('mode')
    num = request.args.get('num')
    balance = request.args.get('balance')
    exchange = get_exchange(binance_list, strategy)
    res = make_response(
        jsonify(
            dapi_transfer_and_sell_coin(exchange, asset, mode, num, balance)))
    res = decorate_res(res)
    return res


@app.route('/cta/usdt/list', methods=['GET'])
def cta_usdt_list():
    symbol = request.args.get('symbol')
    is_running = request.args.get('is_running')
    cta = request.args.get('cta')
    signal = request.args.get('signal')
    res = make_response(
        jsonify(cta_usdt_get_list(symbol, is_running, cta, signal)))
    res = decorate_res(res)
    return res


@app.route('/cta/usdt/create', methods=['POST', 'OPTIONS'])
def cta_usdt_create():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res

    if request.method == 'POST':
        data = request.get_json()
        res = make_response(jsonify(cta_usdt_create_strategy(data)))
        res = decorate_res(res)
        return res


@app.route('/cta/usdt/update', methods=['POST', 'OPTIONS'])
def cta_usdt_update():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res

    if request.method == 'POST':
        data = request.get_json()
        res = make_response(jsonify(cta_usdt_update_strategy(data)))
        res = decorate_res(res)
        return res


@app.route('/cta/usdt/start', methods=['GET'])
def cta_usdt_start():
    cta_key = request.args.get('cta_key')
    try:
        strategy, symbol, interval, cta, period = cta_usdt_get_startegy_params_by_cta_key(
            cta_key)
    except Exception as e:
        res = make_response(jsonify({'status': 500, 'msg': str(e)}))
        res = decorate_res(res)
        return res

    exchange = get_exchange(binance_list, strategy)
    excutor.submit(cta_excute_init, exchange, symbol, interval, cta, period)
    res = make_response(jsonify({'status': 0, 'msg': ''}))
    res = decorate_res(res)
    return res


@app.route('/cta/usdt/stop', methods=['GET'])
def cta_usdt_stop():
    cta_key = request.args.get('cta_key')
    try:
        scheduler.remove_job(cta_key)
        log_print(f'{cta_key}定时器已被移除')
    except:
        log_print(f'{cta_key}定时器已被移除')
    trade_info = cta_usdt_get_trade_info(cta_key)
    exchange = get_exchange(binance_list, trade_info['strategy'])
    cta_usdt_stop_after(exchange, trade_info, cta_key)  # is_running状态在函数内改变了
    res = make_response(jsonify({'status': 0, 'msg': ''}))
    res = decorate_res(res)
    return res


@app.route('/cta/usdt/start_all', methods=['GET'])
def cta_usdt_start_all():
    try:
        params_list = cta_usdt_get_all_running_strategy()
    except Exception as e:
        res = make_response(jsonify({'status': 500, 'msg': str(e)}))
        res = decorate_res(res)
        return res

    for params in params_list:
        strategy = params[0]
        exchange = get_exchange(binance_list, strategy)
        params[0] = exchange
    excutor.submit(cta_excute_init_all, params_list)
    res = make_response(jsonify({'status': 0, 'msg': ''}))
    res = decorate_res(res)
    return res


@app.route('/cta/usdt/stop_all', methods=['GET'])
def cta_usdt_stop_all():
    cta_keys = cta_usdt_get_all_running_strategy_cta_keys()
    for cta_key in cta_keys:
        try:
            scheduler.remove_job(cta_key)
            log_print(f'{cta_key}定时器已被移除')
        except:
            log_print(f'{cta_key}定时器已被移除')
        trade_info = cta_usdt_get_trade_info(cta_key)
        exchange = get_exchange(binance_list, trade_info['strategy'])
        cta_usdt_stop_after(exchange, trade_info,
                            cta_key)  # is_running状态在函数内改变了
    res = make_response(jsonify({'status': 0, 'msg': ''}))
    res = decorate_res(res)
    return res


@app.route('/cta/usdt/evaluate', methods=['GET'])
def cta_usdt_evaluate():
    strategy = request.args.get('strategy')
    symbol = request.args.get('symbol')
    interval = request.args.get('interval')
    period = request.args.get('period')
    cta = request.args.get('cta')
    switch = request.args.get('evaluate_switch')
    start_date = request.args.get('start_date')
    if len(start_date) == 0:
        start_date = None
    exchange = get_exchange(binance_list, strategy)
    res = make_response(
        jsonify(
            get_cta_usdt_evaluate_params(exchange, symbol, interval, cta,
                                         period, switch, start_date)))
    res = decorate_res(res)
    return res


@app.route('/cta/usdt/monthly', methods=['GET'])
def cta_usdt_monthly():
    strategy = request.args.get('strategy')
    symbol = request.args.get('symbol')
    interval = request.args.get('interval')
    period = request.args.get('period')
    cta = request.args.get('cta')
    switch = request.args.get('evaluate_switch')
    start_date = request.args.get('start_date')
    if len(start_date) == 0:
        start_date = None
    exchange = get_exchange(binance_list, strategy)
    res = make_response(
        jsonify(
            get_cta_usdt_evaluate_monthly_params(exchange, symbol, interval,
                                                 cta, period, switch,
                                                 start_date)))
    res = decorate_res(res)
    return res


@app.route('/cta/usd/list', methods=['GET'])
def cta_usd_list():
    symbol = request.args.get('symbol')
    is_running = request.args.get('is_running')
    cta = request.args.get('cta')
    signal = request.args.get('signal')
    res = make_response(
        jsonify(cta_usd_get_list(symbol, is_running, cta, signal)))
    res = decorate_res(res)
    return res


@app.route('/cta/usd/create', methods=['POST', 'OPTIONS'])
def cta_usd_create():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res

    if request.method == 'POST':
        data = request.get_json()
        res = make_response(jsonify(cta_usd_create_strategy(data)))
        res = decorate_res(res)
        return res


@app.route('/cta/usd/create_json', methods=['POST', 'OPTIONS'])
def cta_usd_create_json():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res

    if request.method == 'POST':
        data = request.get_json()
        res = make_response(jsonify(cta_usd_create_strategy_by_json(data)))
        res = decorate_res(res)
        return res


@app.route('/cta/usd/update', methods=['POST', 'OPTIONS'])
def cta_usd_update():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res

    if request.method == 'POST':
        data = request.get_json()
        res = make_response(jsonify(cta_usd_update_strategy(data)))
        res = decorate_res(res)
        return res


@app.route('/cta/usd/start', methods=['GET'])
def cta_usd_start():
    cta_key = request.args.get('cta_key')
    sync_last_signal = request.args.get('sync_last_signal') == '1'
    try:
        strategy, symbol, interval, cta, period = cta_usd_get_startegy_params_by_cta_key(
            cta_key)
    except Exception as e:
        res = make_response(jsonify({'status': 500, 'msg': str(e)}))
        res = decorate_res(res)
        return res

    exchange = get_exchange(binance_list, strategy)
    account_type = get_exchange_account_type(binance_list, strategy)
    excutor.submit(cta_usd_excute_init, exchange, symbol, interval, cta,
                   period, account_type, sync_last_signal=sync_last_signal)
    res = make_response(jsonify({'status': 0, 'msg': ''}))
    res = decorate_res(res)
    return res


@app.route('/cta/usd/stop', methods=['GET'])
def cta_usd_stop():
    cta_key = request.args.get('cta_key')
    try:
        scheduler.remove_job(cta_key)
        log_print(f'{cta_key}定时器已被移除')
    except:
        log_print(f'{cta_key}定时器已被移除')
    trade_info = cta_usd_get_trade_info(cta_key)
    exchange = get_exchange(binance_list, trade_info['strategy'])
    account_type = get_exchange_account_type(binance_list,
                                             trade_info['strategy'])
    cta_usd_stop_after(exchange, trade_info, cta_key,
                       account_type)  # is_running状态在函数内改变了
    res = make_response(jsonify({'status': 0, 'msg': ''}))
    res = decorate_res(res)
    return res


@app.route('/cta/usd/delete', methods=['GET'])
def cta_usd_delete():
    cta_key = request.args.get('cta_key')
    try:
        scheduler.remove_job(cta_key)
        log_print(f'{cta_key}定时器已被移除')
    except:
        log_print(f'{cta_key}定时器已被移除')
    trade_info = cta_usd_get_trade_info(cta_key)
    exchange = get_exchange(binance_list, trade_info['strategy'])
    # 使用数据库删除该策略
    cta_usd_delete_after(exchange, trade_info, cta_key)  # is_running状态在函数内改变了
    res = make_response(jsonify({'status': 0, 'msg': '删除完毕'}))
    res = decorate_res(res)
    return res


@app.route('/cta/usd/start_all', methods=['GET'])
def cta_usd_start_all():
    try:
        params_list = cta_usd_get_all_running_strategy()
    except Exception as e:
        res = make_response(jsonify({'status': 500, 'msg': str(e)}))
        res = decorate_res(res)
        return res

    for params in params_list:
        strategy = params[0]
        exchange = get_exchange(binance_list, strategy)
        account_type = get_exchange_account_type(binance_list, strategy)
        params[0] = exchange
        params.append(account_type)
    excutor.submit(cta_usd_excute_init_all, params_list)
    res = make_response(jsonify({'status': 0, 'msg': ''}))
    res = decorate_res(res)
    return res


@app.route('/cta/usd/stop_all', methods=['GET'])
def cta_usd_stop_all():
    cta_keys = cta_usd_get_all_running_strategy_cta_keys()
    for cta_key in cta_keys:
        try:
            scheduler.remove_job(cta_key)
            log_print(f'{cta_key}定时器已被移除')
        except:
            log_print(f'{cta_key}定时器已被移除')
        trade_info = cta_usd_get_trade_info(cta_key)
        exchange = get_exchange(binance_list, trade_info['strategy'])
        account_type = get_exchange_account_type(binance_list,
                                                 trade_info['strategy'])
        cta_usd_stop_after(exchange, trade_info,
                           cta_key, account_type)  # is_running状态在函数内改变了
    res = make_response(jsonify({'status': 0, 'msg': ''}))
    res = decorate_res(res)
    return res


@app.route('/cta/usd/rebalance/list', methods=['GET'])
def cta_usd_rebalance_list():
    symbol = request.args.get('symbol')
    is_running = request.args.get('is_running')
    cta = request.args.get('cta')
    signal = request.args.get('signal')
    res = make_response(
        jsonify(cta_usd_rebalance_get_list(symbol, is_running, cta, signal)))
    res = decorate_res(res)
    return res


@app.route('/cta/usd/rebalance/create', methods=['POST', 'OPTIONS'])
def cta_usd_rebalance_create():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res

    if request.method == 'POST':
        data = request.get_json()
        res = make_response(jsonify(cta_usd_rebalance_create_strategy(data)))
        res = decorate_res(res)
        return res


@app.route('/cta/usd/rebalance/update', methods=['POST', 'OPTIONS'])
def cta_usd_rebalance_update():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res

    if request.method == 'POST':
        data = request.get_json()
        res = make_response(jsonify(cta_usd_rebalance_update_strategy(data)))
        res = decorate_res(res)
        return res

@app.route('/cta/usd/rebalance/update_all', methods=['POST', 'OPTIONS'])
def cta_usd_rebalance_update_all():
    if request.method == 'OPTIONS':
        res = make_response(jsonify({'status': 0, 'msg': ''}))
        res = decorate_res(res)
        return res

    if request.method == 'POST':
        data = request.get_json()
        res = make_response(jsonify(cta_usd_rebalance_update_all_strategy(data)))
        res = decorate_res(res)
        return res


@app.route('/cta/usd/rebalance/force', methods=['GET'])
def cta_usd_rebalance_force():
    strategy = request.args.get('strategy')
    symbol = request.args.get('symbol')
    exchange = get_exchange(binance_list, strategy)
    res = make_response(
        jsonify(cta_usd_rebalance_force_rebalance(exchange, strategy, symbol)))
    res = decorate_res(res)
    return res


@app.route('/cta/usd/rebalance/force_all', methods=['POST'])
def cta_usd_rebalance_force_all():
    data = request.get_json()
    strategy = data['strategy']
    exchange = get_exchange(binance_list, strategy)
    res = make_response(
        jsonify(cta_usd_rebalance_force_all_rebalance(exchange, strategy)))
    res = decorate_res(res)
    return res


def init_ledger(flag):
    if not flag:
        return
    # 启动账户净值记录的定时任务
    scheduler.add_job(id='account_net_value',
                      func=account_net_value,
                      args=binance_list,
                      trigger='cron',
                      minute='*/10',
                      misfire_grace_time=300)
    scheduler.add_job(id='total_account_net_value',
                      func=total_account_net_value,
                      args=[binance_list],
                      trigger='cron',
                      minute='*/10',
                      misfire_grace_time=300)
    # 启动账户净值记录的定时任务
    scheduler.add_job(id='dapi_account_net_value',
                      func=dapi_account_net_value,
                      args=binance_list,
                      trigger='cron',
                      minute='*/10',
                      misfire_grace_time=300)
    scheduler.add_job(id='scheduler_deribit_account_balance',
                      func=scheduler_deribit_account_balance,
                      args=deribit_list,
                      trigger='cron',
                      minute='*/10',
                      misfire_grace_time=300)


def init_alpha(flag):
    if not flag:
        return
    # 启动黑名单外的策略自动止盈止损
    strategy_tpsl_start_all()


# 初始化U本位CTA相关策略
def init_cta_usdt(flag):
    if not flag:
        return
    # 启动在运行的U本位cta策略
    cta_usdt_start_all()
    # 启动U本位CTA策略止盈止损的定时任务
    if cta_tpsl_time.find('m') > 0:
        scheduler.add_job(id=f'cta_usdt_tpsl',
                          func=cta_usdt_takeprofit_and_stoploss,
                          args=[binance_list],
                          trigger='cron',
                          minute=f"*/{cta_tpsl_time.split('m')[0]}",
                          misfire_grace_time=300)
    elif cta_tpsl_time.find('s') > 0:
        scheduler.add_job(id=f'cta_usdt_tpsl',
                          func=cta_usdt_takeprofit_and_stoploss,
                          args=[binance_list],
                          trigger='cron',
                          second=f"*/{cta_tpsl_time.split('s')[0]}",
                          misfire_grace_time=300)
    # 启动U本位CTA策略定时校准任务
    scheduler.add_job(id=f'cta_signal_check_all',
                      func=cta_signal_check_all,
                      args=[binance_list],
                      trigger='cron',
                      minute='5',
                      misfire_grace_time=300)

    # 启动U本位CTA策略BNB燃烧
    scheduler.add_job(id=f'cta_usdt_replenish_bnb',
                      func=cta_usdt_replenish_bnb,
                      args=[binance_list],
                      trigger='cron',
                      minute='49',
                      misfire_grace_time=300)


# 初始化币本位CTA相关策略
def init_cta_usd(flag):
    if not flag:
        return
    # 启动在运行的币本位cta策略
    cta_usd_start_all()
    # 处理ADL
    scheduler.add_job(id=f'cta_usd_adl_handle',
                      func=cta_usd_adl_handle,
                      args=binance_list,
                      trigger='cron',
                      minute=f"*/9",
                      misfire_grace_time=300)
    # 处理半套
    scheduler.add_job(id=f'cta_usd_rebalance',
                      func=cta_usd_rebalance,
                      args=binance_list,
                      trigger='cron',
                      minute=f"*/16",
                      misfire_grace_time=300)
    # 启动币本位CTA策略止盈止损的定时任务
    if cta_tpsl_time.find('m') > 0:
        scheduler.add_job(id=f'cta_usd_tpsl',
                          func=cta_usd_takeprofit_and_stoploss,
                          args=[binance_list],
                          trigger='cron',
                          minute=f"*/{cta_tpsl_time.split('m')[0]}",
                          misfire_grace_time=300)
    elif cta_tpsl_time.find('s') > 0:
        scheduler.add_job(id=f'cta_usd_tpsl',
                          func=cta_usd_takeprofit_and_stoploss,
                          args=[binance_list],
                          trigger='cron',
                          second=f"*/{cta_tpsl_time.split('s')[0]}",
                          misfire_grace_time=300)
    # 启动币本位CTA策略定时校准任务
    scheduler.add_job(id=f'cta_usd_signal_check_all',
                      func=cta_usd_signal_check_all,
                      args=[binance_list],
                      trigger='cron',
                      minute='10',
                      misfire_grace_time=300)


def init_strategy():
    # 需要启动就填True，反之填False
    init_ledger(True)
    init_alpha(True)
    init_cta_usdt(True)
    init_cta_usd(True)


if __name__ == '__main__':
    with app.app_context():
        scheduler.start()
        init_strategy()
        if debug:
            app.run(host='0.0.0.0', port=5000)
        else:
            server = pywsgi.WSGIServer(('0.0.0.0', 5000), app)
            server.serve_forever()
