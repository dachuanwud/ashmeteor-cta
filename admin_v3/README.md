ver 1.4.221023


# conda 环境配置

```
conda create -n alpha_admin python==3.8.5

pip install -r requirements.txt
```

如果安装 ccxt 失败，可以先手动安装

```
pip install ccxt==1.87.71
```

# 数据库配置

为了能够直接使用，确保表结构相同，建表语句如下

```
/******************************************/
/*   DatabaseName = alpha   */
/*   TableName = strategy   */
/******************************************/
CREATE TABLE `strategy` (
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
```

```
/******************************************/
/*   DatabaseName = alpha   */
/*   TableName = long_black_list   */
/******************************************/
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

```

```
/******************************************/
/*   DatabaseName = alpha   */
/*   TableName = short_black_list   */
/******************************************/
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
```

# config 配置项解析

## sql_uri

链接数据库的 uri
格式如下
'mysql+pymysql://用户名:密码@ip:port/数据库名'

## google_key

谷歌验证码的对应密钥

## cookie_secret

加密 cookie 所需对应密钥

## amis_edit_origin

amis 编辑器的 origin，在线预览时会涉及跨域问题，需要填写改 origin

## local_origin

本地启动时的 origin，解决跨域问题（flask 直接自己启动不会涉及该问题）

## users

添加你所需的登录名称

## proxy

添加你所需的代理，不需要留空即可

## ip_white_list

允许访问的IP白名单

# 使用指南

- 没有数据库的先去建库，建表
- 手动写 sql，打开 strategy 表，手动填入币安 api，secret 等信息
- 改写admin.json和login.json中的内容，将请求的api改成自己的服务器的ip或域名，本地调试请改成127.0.0.1:port
- 将两个json的内容填到对应的html文件中，聪明的你应该能看出来填到哪
- 改写config.py中的各项配置文件，记得关注debug的状态
- 运行 app.py
- 打开进入主页，本地调试没有额外配置的情况下是http://127.0.0.1:5000，远程调试是http://服务器IP:port
- 服务器部署，请记得打开阿里云上的防火墙，并且打开ubuntu本地的防火墙，以5000端口为例，执行  sudo ufw allow 5000
- 输入用户名和谷歌验证码进行验证登录
- 登录成功后刷新页面即可

# AMIS 在线编辑器页面

https://aisuda.github.io/amis-editor-demo/

# 其他注意事项

debug模式下特点
- IP白名单无效，任何IP均可访问
- 无需登录校验，可直接打开策略管理界面
- 可通过amis在线编辑器直接访问
- web服务为flask本身的服务，不建议用作生产环境