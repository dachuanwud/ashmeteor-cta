ALTER TABLE strategy
  ADD COLUMN account_type varchar(32) NOT NULL DEFAULT 'standard' COMMENT '账户类型: standard普通账户 unified统一账户'
  AFTER is_main;
