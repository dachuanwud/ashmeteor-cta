CREATE TABLE `strategy` (
  `id` int unsigned NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `strategy` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '策略名称',
  `account` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '币安邮箱',
  `is_main` tinyint NOT NULL DEFAULT '0' COMMENT '是否主账户 ',
  `account_type` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'standard' COMMENT '账户类型: standard普通账户 unified统一账户',
  `apikey` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '币安API',
  `secret` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '币安密钥',
  `trade_ratio` decimal(10,2) unsigned NOT NULL DEFAULT '1.00' COMMENT '策略杠杆',
  `takeprofit_percentage` decimal(10,2) unsigned NOT NULL DEFAULT '0.30' COMMENT '止盈比例',
  `stoploss_percentage` decimal(10,2) unsigned NOT NULL DEFAULT '0.10' COMMENT '止损比例',
  `is_del` tinyint unsigned NOT NULL DEFAULT '0' COMMENT '是否软删除',
  `update_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '上次更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `strategy` (`strategy`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
;

CREATE TABLE `deribit` (
  `id` int unsigned NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `strategy` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '策略名称',
  `account` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '币安邮箱',
  `apikey` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '币安API',
  `secret` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '币安密钥',
  `trade_ratio` decimal(10,2) unsigned NOT NULL DEFAULT '1.00' COMMENT '策略杠杆',
  `takeprofit_percentage` decimal(10,2) unsigned NOT NULL DEFAULT '0.30' COMMENT '止盈比例',
  `stoploss_percentage` decimal(10,2) unsigned NOT NULL DEFAULT '0.10' COMMENT '止损比例',
  `is_del` tinyint unsigned NOT NULL DEFAULT '0' COMMENT '是否软删除',
  `update_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '上次更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `strategy` (`strategy`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
;

CREATE TABLE `long_black_list` (
  `id` int unsigned NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `strategy` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '所属策略',
  `symbol` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '标的名称',
  `release_time` datetime NOT NULL COMMENT '黑名单解除时间',
  `is_del` tinyint unsigned NOT NULL DEFAULT '0' COMMENT '软删除',
  `update_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
;

CREATE TABLE `short_black_list` (
  `id` int unsigned NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `strategy` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '所属策略',
  `symbol` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '标的名称',
  `release_time` datetime NOT NULL COMMENT '黑名单解除时间',
  `is_del` tinyint unsigned NOT NULL DEFAULT '0' COMMENT '软删除',
  `update_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
;

CREATE TABLE `cta_usdt` (
  `id` int unsigned NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `strategy` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '策略账户名称',
  `cta_key` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT 'cta策略唯一性标志',
  `is_running` int unsigned NOT NULL DEFAULT '0' COMMENT '是否正在运行',
  `symbol` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '交易对',
  `interval` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '时间间隔',
  `cta` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT 'cta策略名称',
  `period` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT 'cta参数',
  `signal` int NOT NULL DEFAULT '0' COMMENT '当前信号',
  `signal_time` datetime DEFAULT NULL COMMENT '当前信号产生时间',
  `open_price` decimal(20,6) DEFAULT NULL COMMENT '策略开仓价',
  `close_price` decimal(20,6) DEFAULT NULL COMMENT '策略上次平仓价',
  `position_amount` decimal(20,5) NOT NULL DEFAULT '0.00000' COMMENT '当前仓位',
  `init_value` decimal(10,2) NOT NULL DEFAULT '0.00' COMMENT '策略初始开仓金额',
  `profit` decimal(10,2) NOT NULL DEFAULT '0.00' COMMENT '策略盈利',
  `net_value` decimal(10,2) unsigned NOT NULL DEFAULT '1.00' COMMENT '策略当前净值',
  `trade_ratio` decimal(10,2) unsigned NOT NULL DEFAULT '1.00' COMMENT '策略杠杆',
  `takeprofit_percentage` decimal(10,2) unsigned NOT NULL DEFAULT '0.30' COMMENT '止盈比例',
  `takeprofit_drawdown_percentage` decimal(10,2) unsigned NOT NULL DEFAULT '0.05' COMMENT '吊灯止盈回调比例',
  `stoploss_percentage` decimal(10,2) unsigned NOT NULL DEFAULT '0.10' COMMENT '止损比例',
  `open_tpsl` tinyint unsigned NOT NULL DEFAULT '1' COMMENT '是否开启止盈止损',
  `is_tpsl` tinyint unsigned NOT NULL DEFAULT '0' COMMENT '是否已触发止盈止损',
  `is_del` tinyint unsigned NOT NULL DEFAULT '0' COMMENT '是否软删除',
  `update_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '上次更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `cta_key` (`cta_key`) USING BTREE COMMENT 'cta策略唯一标志key'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
;

CREATE TABLE `cta_usd` (
  `id` int unsigned NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `strategy` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '策略账户名称',
  `cta_key` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT 'cta策略唯一性标志',
  `is_running` int unsigned NOT NULL DEFAULT '0' COMMENT '是否正在运行',
  `symbol` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '交易对',
  `interval` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '时间间隔',
  `cta` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT 'cta策略名称',
  `period` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT 'cta参数',
  `signal` int NOT NULL DEFAULT '0' COMMENT '当前信号',
  `signal_time` datetime DEFAULT NULL COMMENT '当前信号产生时间',
  `open_price` decimal(20,6) DEFAULT NULL COMMENT '策略开仓价',
  `close_price` decimal(20,6) DEFAULT NULL COMMENT '策略上次平仓价',
  `position_amount` decimal(20,5) NOT NULL DEFAULT '0.00000' COMMENT '当前仓位',
  `init_value` decimal(10,2) NOT NULL DEFAULT '0.00' COMMENT '策略初始开仓金额',
  `profit` decimal(10,2) NOT NULL DEFAULT '0.00' COMMENT '策略盈利',
  `net_value` decimal(10,2) unsigned NOT NULL DEFAULT '1.00' COMMENT '策略当前净值',
  `trade_ratio` decimal(10,2) unsigned NOT NULL DEFAULT '1.00' COMMENT '策略杠杆',
  `takeprofit_percentage` decimal(10,2) unsigned NOT NULL DEFAULT '0.30' COMMENT '止盈比例',
  `takeprofit_drawdown_percentage` decimal(10,2) unsigned NOT NULL DEFAULT '0.05' COMMENT '吊灯止盈回调比例',
  `stoploss_percentage` decimal(10,2) unsigned NOT NULL DEFAULT '0.10' COMMENT '止损比例',
  `open_tpsl` tinyint unsigned NOT NULL DEFAULT '1' COMMENT '是否开启止盈止损',
  `is_tpsl` tinyint unsigned NOT NULL DEFAULT '0' COMMENT '是否已触发止盈止损',
  `is_del` tinyint unsigned NOT NULL DEFAULT '0' COMMENT '是否软删除',
  `update_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '上次更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `cta_key` (`cta_key`) USING BTREE COMMENT 'cta策略唯一标志key'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
;

CREATE TABLE `cta_usd_rebalance` (
  `id` int unsigned NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `strategy` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '策略账户名称',
  `cta_key` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT 'cta策略唯一性标志',
  `is_running` int unsigned NOT NULL DEFAULT '0' COMMENT '是否正在运行',
  `symbol` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '交易对',
  `interval` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '时间间隔',
  `cta` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'rebalance' COMMENT 'cta策略名称',
  `period` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT 'cta参数',
  `signal` int NOT NULL DEFAULT '0' COMMENT '当前信号',
  `signal_time` datetime DEFAULT NULL COMMENT '当前信号产生时间',
  `open_price` decimal(20,6) DEFAULT NULL COMMENT '策略开仓价',
  `close_price` decimal(20,6) DEFAULT NULL COMMENT '策略上次平仓价',
  `position_amount` decimal(20,5) NOT NULL DEFAULT '0.00000' COMMENT '当前仓位',
  `init_value` decimal(10,2) NOT NULL DEFAULT '0.00' COMMENT '策略初始开仓金额',
  `profit` decimal(10,2) NOT NULL DEFAULT '0.00' COMMENT '策略盈利',
  `net_value` decimal(10,2) unsigned NOT NULL DEFAULT '1.00' COMMENT '策略当前净值',
  `trade_ratio` decimal(10,2) unsigned NOT NULL DEFAULT '1.00' COMMENT '策略杠杆',
  `takeprofit_percentage` decimal(10,2) unsigned NOT NULL DEFAULT '0.30' COMMENT '止盈比例',
  `takeprofit_drawdown_percentage` decimal(10,2) unsigned NOT NULL DEFAULT '0.05' COMMENT '吊灯止盈回调比例',
  `stoploss_percentage` decimal(10,2) unsigned NOT NULL DEFAULT '0.10' COMMENT '止损比例',
  `open_tpsl` tinyint unsigned NOT NULL DEFAULT '1' COMMENT '是否开启止盈止损',
  `is_del` tinyint unsigned NOT NULL DEFAULT '0' COMMENT '是否软删除',
  `update_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '上次更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `cta_key` (`cta_key`) USING BTREE COMMENT 'cta策略唯一标志key'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
;

CREATE TABLE `cta_unified_margin_rebalance` (
  `id` int unsigned NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `strategy` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '策略账户名称',
  `asset` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '现货/杠杆资产',
  `spot_symbol` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '买币交易对',
  `hedge_symbol` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT 'U本位半套交易对',
  `hedge_market` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'um' COMMENT '半套市场类型',
  `hedge_ratio` decimal(10,4) unsigned NOT NULL DEFAULT '0.5000' COMMENT '半套比例',
  `target_base_qty` decimal(20,8) unsigned NOT NULL DEFAULT '0.00000000' COMMENT '目标基础币数量',
  `hedged_base_qty` decimal(20,8) unsigned NOT NULL DEFAULT '0.00000000' COMMENT '已半套基础币数量',
  `is_running` tinyint unsigned NOT NULL DEFAULT '1' COMMENT '是否启用',
  `live_trade_enabled` tinyint unsigned NOT NULL DEFAULT '0' COMMENT '是否允许真实下单',
  `last_buy_order_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '最近买币订单ID',
  `last_rebalance_time` datetime DEFAULT NULL COMMENT '最近半套时间',
  `last_status` int NOT NULL DEFAULT '0' COMMENT '最近执行状态',
  `last_msg` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '最近执行信息',
  `is_del` tinyint unsigned NOT NULL DEFAULT '0' COMMENT '是否软删除',
  `update_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '上次更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_strategy_asset` (`strategy`,`asset`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
;
