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
