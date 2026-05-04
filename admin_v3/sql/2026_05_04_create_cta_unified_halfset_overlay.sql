CREATE TABLE IF NOT EXISTS `cta_unified_halfset_overlay` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `strategy` varchar(255) NOT NULL DEFAULT '' COMMENT '统一账户策略名称',
  `asset` varchar(64) NOT NULL DEFAULT '' COMMENT '现货/杠杆底仓资产',
  `cta_key` varchar(255) NOT NULL DEFAULT '' COMMENT 'CTA策略唯一标识',
  `symbol` varchar(64) NOT NULL DEFAULT '' COMMENT 'U本位CTA标的',
  `interval` varchar(64) NOT NULL DEFAULT '4h' COMMENT 'CTA周期',
  `cta` varchar(255) NOT NULL DEFAULT 'adapt_bolling_anti_chase' COMMENT 'CTA策略名称',
  `period` varchar(255) NOT NULL DEFAULT '[200,20]' COMMENT 'CTA参数',
  `weight` decimal(10,4) NOT NULL DEFAULT '1.0000' COMMENT 'CTA共享权重',
  `trade_ratio` decimal(10,4) NOT NULL DEFAULT '1.0000' COMMENT 'CTA权重增强因子',
  `is_running` tinyint NOT NULL DEFAULT '0' COMMENT '是否参与完整半套协调',
  `last_signal` int NOT NULL DEFAULT '0' COMMENT '最近CTA信号',
  `target_qty` decimal(20,8) NOT NULL DEFAULT '0.00000000' COMMENT 'CTA记账目标',
  `last_signal_time` datetime DEFAULT NULL COMMENT '最近CTA信号时间',
  `last_status` int NOT NULL DEFAULT '0' COMMENT '最近状态',
  `last_msg` varchar(255) NOT NULL DEFAULT '' COMMENT '最近提示',
  `is_del` tinyint NOT NULL DEFAULT '0' COMMENT '是否软删除',
  `update_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_cta_key_active` (`cta_key`, `is_del`),
  KEY `idx_strategy_asset_running` (`strategy`, `asset`, `is_running`, `is_del`),
  KEY `idx_strategy_symbol` (`strategy`, `symbol`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='统一账户完整半套CTA Overlay';

INSERT INTO `cta_unified_halfset_overlay` (
  `strategy`,
  `asset`,
  `cta_key`,
  `symbol`,
  `interval`,
  `cta`,
  `period`,
  `weight`,
  `trade_ratio`,
  `is_running`,
  `last_signal`,
  `target_qty`,
  `last_signal_time`,
  `last_status`,
  `last_msg`,
  `is_del`
)
SELECT
  h.`strategy`,
  h.`asset`,
  h.`cta_key`,
  h.`hedge_symbol`,
  h.`interval`,
  h.`cta`,
  h.`period`,
  '1.0000',
  h.`cta_trade_ratio`,
  h.`is_running`,
  h.`last_signal`,
  h.`cta_target_qty`,
  h.`last_signal_time`,
  h.`last_status`,
  '从旧完整半套单CTA配置迁移',
  0
FROM `cta_unified_halfset_mode` h
LEFT JOIN `cta_unified_halfset_overlay` o
  ON o.`cta_key` = h.`cta_key` AND o.`is_del` = 0
WHERE h.`is_del` = 0
  AND h.`cta_key` <> ''
  AND o.`id` IS NULL;
