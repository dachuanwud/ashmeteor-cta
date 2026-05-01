# coding: utf-8
from sqlalchemy import Column, Float, String, TIMESTAMP, text, DateTime
from sqlalchemy.dialects.mysql import DECIMAL, INTEGER, TINYINT, VARCHAR
from exts import db


class LongBlackList(db.Model):
    __tablename__ = 'long_black_list'

    id = Column(INTEGER, primary_key=True, comment='主键ID')
    strategy = Column(VARCHAR(255),
                      nullable=False,
                      server_default=text("''"),
                      comment='所属策略')
    symbol = Column(VARCHAR(255),
                    nullable=False,
                    server_default=text("''"),
                    comment='标的名称')
    release_time = Column(DateTime, nullable=False, comment='黑名单解除时间')
    is_del = Column(TINYINT,
                    nullable=False,
                    server_default=text("'0'"),
                    comment='是否软删除')
    update_time = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment='更新时间')


class ShortBlackList(db.Model):
    __tablename__ = 'short_black_list'

    id = Column(INTEGER, primary_key=True, comment='主键ID')
    strategy = Column(VARCHAR(255),
                      nullable=False,
                      server_default=text("''"),
                      comment='所属策略')
    symbol = Column(VARCHAR(255),
                    nullable=False,
                    server_default=text("''"),
                    comment='标的名称')
    release_time = Column(DateTime, nullable=False, comment='黑名单解除时间')
    is_del = Column(TINYINT,
                    nullable=False,
                    server_default=text("'0'"),
                    comment='是否软删除')
    update_time = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment='更新时间')


class Strategy(db.Model):
    __tablename__ = 'strategy'

    id = Column(INTEGER, primary_key=True, comment='ID')
    strategy = Column(VARCHAR(255), nullable=False, comment='策略名称')
    account = Column(VARCHAR(255), nullable=False, comment='币安邮箱')
    apikey = Column(VARCHAR(255), nullable=False, comment='币安API')
    secret = Column(VARCHAR(255), nullable=False, comment='币安密钥')
    trade_ratio = Column(DECIMAL(10, 2),
                         nullable=False,
                         server_default=text("'1.00'"),
                         comment='策略杠杆')
    takeprofit_percentage = Column(DECIMAL(10, 2),
                                   nullable=False,
                                   server_default=text("'0.30'"),
                                   comment='止盈比例')
    stoploss_percentage = Column(DECIMAL(10, 2),
                                 nullable=False,
                                 server_default=text("'0.10'"),
                                 comment='止损比例')
    is_del = Column(TINYINT,
                    nullable=False,
                    server_default=text("'0'"),
                    comment='是否软删除')
    update_time = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment='上次更新时间')
    is_main = Column(TINYINT,
                    nullable=False,
                    server_default=text("'0'"),
                    comment='是否主账户')


class Deribit(db.Model):
    __tablename__ = 'deribit'

    id = Column(INTEGER, primary_key=True, comment='ID')
    strategy = Column(VARCHAR(255), nullable=False, comment='策略名称')
    account = Column(VARCHAR(255), nullable=False, comment='币安邮箱')
    apikey = Column(VARCHAR(255), nullable=False, comment='币安API')
    secret = Column(VARCHAR(255), nullable=False, comment='币安密钥')
    trade_ratio = Column(DECIMAL(10, 2),
                         nullable=False,
                         server_default=text("'1.00'"),
                         comment='策略杠杆')
    takeprofit_percentage = Column(DECIMAL(10, 2),
                                   nullable=False,
                                   server_default=text("'0.30'"),
                                   comment='止盈比例')
    stoploss_percentage = Column(DECIMAL(10, 2),
                                 nullable=False,
                                 server_default=text("'0.10'"),
                                 comment='止损比例')
    is_del = Column(TINYINT,
                    nullable=False,
                    server_default=text("'0'"),
                    comment='是否软删除')
    update_time = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment='上次更新时间')


class Takeprofit(db.Model):
    __tablename__ = 'takeprofit'

    id = Column(INTEGER, primary_key=True, comment='id')
    strategy = Column(String(100),
                      nullable=False,
                      server_default=text("''"),
                      comment='策略代号')
    symbol = Column(String(100),
                    nullable=False,
                    server_default=text("''"),
                    comment='标的名称')
    max_net_value = Column(Float(asdecimal=True),
                           nullable=False,
                           server_default=text("'1'"),
                           comment='最大净值')
    is_del = Column(TINYINT,
                    nullable=False,
                    server_default=text("'0'"),
                    comment='软删除')
    update_time = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment='最近修改时间')


class CtaUsdt(db.Model):
    __tablename__ = 'cta_usdt'

    def to_dict(self):
        return {
            c.name: getattr(self, c.name, None)
            for c in self.__table__.columns
        }

    id = Column(INTEGER, primary_key=True, comment='ID')
    strategy = Column(VARCHAR(255),
                      nullable=False,
                      server_default=text("''"),
                      comment='策略账户名称')
    cta_key = Column(VARCHAR(255),
                     nullable=False,
                     unique=True,
                     server_default=text("''"),
                     comment='cta策略唯一性标志')
    is_running = Column(INTEGER,
                        nullable=False,
                        server_default=text("'0'"),
                        comment='是否正在运行')
    symbol = Column(VARCHAR(255),
                    nullable=False,
                    server_default=text("''"),
                    comment='交易对')
    interval = Column(VARCHAR(255),
                      nullable=False,
                      server_default=text("''"),
                      comment='时间间隔')
    cta = Column(VARCHAR(255),
                 nullable=False,
                 server_default=text("''"),
                 comment='cta策略名称')
    period = Column(VARCHAR(255),
                    nullable=False,
                    server_default=text("''"),
                    comment='cta参数')
    signal = Column(INTEGER,
                    nullable=False,
                    server_default=text("'0'"),
                    comment='当前信号')
    signal_time = Column(DateTime, comment='当前信号产生时间')
    open_price = Column(DECIMAL(20, 6), comment='策略开仓价')
    close_price = Column(DECIMAL(20, 6), comment='策略上次平仓价')
    position_amount = Column(DECIMAL(20, 5),
                             nullable=False,
                             server_default=text("'0.00000'"),
                             comment='当前仓位')
    init_value = Column(DECIMAL(10, 2),
                        nullable=False,
                        server_default=text("'0.00'"),
                        comment='策略初始开仓金额')
    profit = Column(DECIMAL(10, 2),
                    nullable=False,
                    server_default=text("'0.00'"),
                    comment='策略盈利')
    net_value = Column(DECIMAL(10, 2),
                       nullable=False,
                       server_default=text("'1.00'"),
                       comment='策略当前净值')
    trade_ratio = Column(DECIMAL(10, 2),
                         nullable=False,
                         server_default=text("'1.00'"),
                         comment='策略杠杆')
    takeprofit_percentage = Column(DECIMAL(10, 2),
                                   nullable=False,
                                   server_default=text("'0.30'"),
                                   comment='止盈比例')
    takeprofit_drawdown_percentage = Column(DECIMAL(10, 2),
                                            nullable=False,
                                            server_default=text("'0.05'"),
                                            comment='吊灯止盈回调比例')
    stoploss_percentage = Column(DECIMAL(10, 2),
                                 nullable=False,
                                 server_default=text("'0.10'"),
                                 comment='止损比例')
    open_tpsl = Column(TINYINT,
                       nullable=False,
                       server_default=text("'1'"),
                       comment='是否开启止盈止损')
    is_tpsl = Column(TINYINT,
                    nullable=False,
                    server_default=text("'0'"),
                    comment='是否已触发止盈止损')
    is_del = Column(TINYINT,
                    nullable=False,
                    server_default=text("'0'"),
                    comment='是否软删除')
    update_time = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment='上次更新时间')


class CtaUsd(db.Model):
    __tablename__ = 'cta_usd'

    def to_dict(self):
        return {
            c.name: getattr(self, c.name, None)
            for c in self.__table__.columns
        }

    id = Column(INTEGER, primary_key=True, comment='ID')
    strategy = Column(VARCHAR(255),
                      nullable=False,
                      server_default=text("''"),
                      comment='策略账户名称')
    cta_key = Column(VARCHAR(255),
                     nullable=False,
                     unique=True,
                     server_default=text("''"),
                     comment='cta策略唯一性标志')
    is_running = Column(INTEGER,
                        nullable=False,
                        server_default=text("'0'"),
                        comment='是否正在运行')
    symbol = Column(VARCHAR(255),
                    nullable=False,
                    server_default=text("''"),
                    comment='交易对')
    interval = Column(VARCHAR(255),
                      nullable=False,
                      server_default=text("''"),
                      comment='时间间隔')
    cta = Column(VARCHAR(255),
                 nullable=False,
                 server_default=text("''"),
                 comment='cta策略名称')
    period = Column(VARCHAR(255),
                    nullable=False,
                    server_default=text("''"),
                    comment='cta参数')
    signal = Column(INTEGER,
                    nullable=False,
                    server_default=text("'0'"),
                    comment='当前信号')
    signal_time = Column(DateTime, comment='当前信号产生时间')
    open_price = Column(DECIMAL(20, 6), comment='策略开仓价')
    close_price = Column(DECIMAL(20, 6), comment='策略上次平仓价')
    position_amount = Column(DECIMAL(20, 5),
                             nullable=False,
                             server_default=text("'0.00000'"),
                             comment='当前仓位')
    init_value = Column(DECIMAL(10, 2),
                        nullable=False,
                        server_default=text("'0.00'"),
                        comment='策略初始开仓金额')
    profit = Column(DECIMAL(10, 2),
                    nullable=False,
                    server_default=text("'0.00'"),
                    comment='策略盈利')
    net_value = Column(DECIMAL(10, 2),
                       nullable=False,
                       server_default=text("'1.00'"),
                       comment='策略当前净值')
    trade_ratio = Column(DECIMAL(10, 2),
                         nullable=False,
                         server_default=text("'1.00'"),
                         comment='策略杠杆')
    takeprofit_percentage = Column(DECIMAL(10, 2),
                                   nullable=False,
                                   server_default=text("'0.30'"),
                                   comment='止盈比例')
    takeprofit_drawdown_percentage = Column(DECIMAL(10, 2),
                                            nullable=False,
                                            server_default=text("'0.05'"),
                                            comment='吊灯止盈回调比例')
    stoploss_percentage = Column(DECIMAL(10, 2),
                                 nullable=False,
                                 server_default=text("'0.10'"),
                                 comment='止损比例')
    open_tpsl = Column(TINYINT,
                       nullable=False,
                       server_default=text("'1'"),
                       comment='是否开启止盈止损')
    is_tpsl = Column(TINYINT,
                    nullable=False,
                    server_default=text("'0'"),
                    comment='是否已触发止盈止损')
    is_del = Column(TINYINT,
                    nullable=False,
                    server_default=text("'0'"),
                    comment='是否软删除')
    update_time = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment='上次更新时间')


class CtaUsdRebalance(db.Model):
    __tablename__ = 'cta_usd_rebalance'

    def to_dict(self):
        return {
            c.name: getattr(self, c.name, None)
            for c in self.__table__.columns
        }

    id = Column(INTEGER, primary_key=True, comment='ID')
    strategy = Column(VARCHAR(255),
                      nullable=False,
                      server_default=text("''"),
                      comment='策略账户名称')
    cta_key = Column(VARCHAR(255),
                     nullable=False,
                     unique=True,
                     server_default=text("''"),
                     comment='cta策略唯一性标志')
    is_running = Column(INTEGER,
                        nullable=False,
                        server_default=text("'0'"),
                        comment='是否正在运行')
    symbol = Column(VARCHAR(255),
                    nullable=False,
                    server_default=text("''"),
                    comment='交易对')
    interval = Column(VARCHAR(255),
                      nullable=False,
                      server_default=text("''"),
                      comment='时间间隔')
    cta = Column(VARCHAR(255),
                 nullable=False,
                 server_default=text("'rebalance'"),
                 comment='cta策略名称')
    period = Column(VARCHAR(255),
                    nullable=False,
                    server_default=text("''"),
                    comment='cta参数')
    signal = Column(INTEGER,
                    nullable=False,
                    server_default=text("'0'"),
                    comment='当前信号')
    signal_time = Column(DateTime, comment='当前信号产生时间')
    open_price = Column(DECIMAL(20, 6), comment='策略开仓价')
    close_price = Column(DECIMAL(20, 6), comment='策略上次平仓价')
    position_amount = Column(DECIMAL(20, 5),
                             nullable=False,
                             server_default=text("'0.00000'"),
                             comment='当前仓位')
    init_value = Column(DECIMAL(10, 2),
                        nullable=False,
                        server_default=text("'0.00'"),
                        comment='策略初始开仓金额')
    profit = Column(DECIMAL(10, 2),
                    nullable=False,
                    server_default=text("'0.00'"),
                    comment='策略盈利')
    net_value = Column(DECIMAL(10, 2),
                       nullable=False,
                       server_default=text("'1.00'"),
                       comment='策略当前净值')
    trade_ratio = Column(DECIMAL(10, 2),
                         nullable=False,
                         server_default=text("'1.00'"),
                         comment='策略杠杆')
    takeprofit_percentage = Column(DECIMAL(10, 2),
                                   nullable=False,
                                   server_default=text("'0.30'"),
                                   comment='止盈比例')
    takeprofit_drawdown_percentage = Column(DECIMAL(10, 2),
                                            nullable=False,
                                            server_default=text("'0.05'"),
                                            comment='吊灯止盈回调比例')
    stoploss_percentage = Column(DECIMAL(10, 2),
                                 nullable=False,
                                 server_default=text("'0.10'"),
                                 comment='止损比例')
    open_tpsl = Column(TINYINT,
                       nullable=False,
                       server_default=text("'1'"),
                       comment='是否开启止盈止损')
    is_del = Column(TINYINT,
                    nullable=False,
                    server_default=text("'0'"),
                    comment='是否软删除')
    update_time = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment='上次更新时间')