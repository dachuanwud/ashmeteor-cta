CREATE TABLE `strategy` (
  `id` int unsigned NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `strategy` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '策略名称',
  `account` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '币安邮箱',
  `is_main` tinyint NOT NULL DEFAULT '0' COMMENT '是否主账户 ',
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
