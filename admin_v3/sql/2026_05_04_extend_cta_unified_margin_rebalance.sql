ALTER TABLE `cta_unified_margin_rebalance`
  ADD COLUMN `buy_mode` varchar(32) NOT NULL DEFAULT 'cash' COMMENT '底仓买入模式' AFTER `hedge_market`,
  ADD COLUMN `margin_side_effect_type` varchar(64) NOT NULL DEFAULT '' COMMENT '统一账户杠杆买入方式' AFTER `buy_mode`,
  ADD COLUMN `target_quote_usd` decimal(20,4) unsigned NOT NULL DEFAULT '0.0000' COMMENT '目标买入名义USDT' AFTER `margin_side_effect_type`,
  ADD COLUMN `last_borrow_asset` varchar(64) NOT NULL DEFAULT '' COMMENT '最近借款资产' AFTER `last_buy_order_id`,
  ADD COLUMN `last_borrow_amount` decimal(20,8) unsigned NOT NULL DEFAULT '0.00000000' COMMENT '最近借款数量' AFTER `last_borrow_asset`,
  ADD COLUMN `last_executed_base_qty` decimal(20,8) unsigned NOT NULL DEFAULT '0.00000000' COMMENT '最近成交基础币数量' AFTER `last_borrow_amount`,
  ADD COLUMN `base_wallet_source` varchar(64) NOT NULL DEFAULT 'MARGIN_OR_SPOT' COMMENT '底仓钱包来源' AFTER `last_executed_base_qty`;
