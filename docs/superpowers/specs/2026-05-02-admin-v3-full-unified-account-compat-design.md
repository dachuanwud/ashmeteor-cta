# Admin v3 统一账户全功能兼容设计

## 背景

Admin v3 原始实现按币安普通账户拆成现货、U 本位合约和币本位合约三条接口链路，分别调用 `sapi`、`fapi`、`dapi`。统一账户使用 Portfolio Margin API，资金、仓位和交易接口集中在 `papi` 下。平台已经完成了统一账户字段、币本位 CTA/半套的部分适配，但买币兑换、U 本位 CTA、账户净值、手动交易、订单管理和资金管理仍可能误走旧接口。

目标是在保留普通账户行为不变的前提下，让账户类型为 `unified` 的策略在所有可用功能里自动走 Portfolio Margin API。任何暂时无法安全映射的功能必须显式禁用或返回清晰错误，不能落回旧接口静默执行。

## 设计原则

- 兼容优先：普通账户继续走现有 `fapi/dapi/sapi`，统一账户才切到 `papi`。
- 适配器集中：上层业务不直接判断 Binance endpoint，统一通过账户适配器选择接口。
- 分阶段上线：先只读，再订单，再策略，再资金兑换，最后净值和后台任务。
- 真实交易保护：新增交易能力必须有单元测试和 dry-run/只读验证脚本；部署验证阶段不自动下单。
- 显式能力边界：无法安全支持的功能返回“不支持统一账户”，避免误调用旧接口。

## 功能矩阵

| 功能 | 普通账户 | 统一账户 | 改造策略 |
| --- | --- | --- | --- |
| 账户余额 | `fapi/dapi/sapi` | `/papi/v1/account`, `/papi/v1/balance` | 统一为 account adapter 的 read-only 方法 |
| U 本位仓位 | `/fapi/v2/positionRisk` | `/papi/v1/um/positionRisk` | 新增 UM 适配器方法 |
| 币本位仓位 | `/dapi/v1/positionRisk` | `/papi/v1/cm/positionRisk` | 已部分完成，补齐订单查询/撤单 |
| U 本位下单 | `/fapi/v1/order` | `/papi/v1/um/order` | CTA/手动交易走适配器 |
| 币本位下单 | `/dapi/v1/order` | `/papi/v1/cm/order` | 已用于 CTA/半套，继续扩展到手动交易 |
| 买 ETH / 兑换币 | 现货或旧转账流程 | `/papi/v1/margin/order` | 统一账户使用 Margin Order，普通账户保留旧流程 |
| 开放订单 | `fapi/dapi openOrders` | `/papi/v1/um/openOrders`, `/papi/v1/cm/openOrders`, `/papi/v1/margin/openOrders` | 按市场类型路由 |
| 撤单 | `fapi/dapi/sapi delete order` | `/papi/v1/um/order`, `/papi/v1/cm/order`, `/papi/v1/margin/order` | 按市场类型路由 |
| 成交记录 | `fapi/dapi/sapi userTrades` | UM/CM/Margin trade list | 按市场类型路由 |
| 半套 | `dapi` | `/papi/v1/cm/*` | 保持当前实现，补 dry-run 输出 |
| 净值统计 | 旧普通账户表 | `papi account/balance` | 统一账户单独净值计算，不复用旧 fapi/dapi 假设 |
| 旧 alpha 止盈止损 | `fapi` | 不自动支持 | 保留跳过统一账户，后续单独迁移 |

## 适配器接口

`admin_v3/binance_account.py` 作为统一入口，扩展出以下能力：

- `get_account_summary()`：返回账户权益、可用余额、账户状态。
- `get_balance_assets()`：返回资产余额，统一字段包括 `asset`、`totalWalletBalance`、`umWalletBalance`、`cmWalletBalance`。
- `get_um_position_risk(params=None)`：U 本位仓位。
- `get_cm_position_risk(params=None)`：币本位仓位。
- `place_um_order(params)`：U 本位下单。
- `place_cm_order(params)`：币本位下单。
- `place_margin_order(params)`：统一账户买币/卖币；普通账户返回不支持或保留旧现货逻辑。
- `get_open_orders(market_type, params=None)`：按 `um/cm/margin` 查询开放订单。
- `cancel_order(market_type, params)`：按 `um/cm/margin` 撤单。
- `get_user_trades(market_type, params)`：按 `um/cm/margin` 查询成交。

上层函数只接受 `exchange`、`account_type`、`market_type`，不直接拼接具体 Binance 私有方法名。

## UI 兼容

现有页面不拆分普通账户和统一账户入口，但需要在危险按钮旁表现账户类型：

- 普通账户显示原按钮和原接口。
- 统一账户显示同一个操作按钮，但后端走新适配器。
- 尚未完成的统一账户功能返回明确错误，前端 toast 显示原因。
- 买币/卖币按钮在统一账户下必须走新 Margin Order dry-run/confirm 流程，不能使用旧 `/dapi/buy_coin` 直接操作。

## 风险控制

- 交易接口默认不在部署脚本中执行真实订单。
- 所有下单函数必须支持注入 `order_func` 或 dry-run recorder。
- 服务端日志必须能看出路由到了 `standard` 还是 `unified`。
- 新增统一账户交易接口先用 API 只读和构造参数测试验证，再由用户手动确认实盘动作。
- 任何资金转移/买币/启动策略动作必须由用户在 UI 中手动触发，不由部署脚本自动触发。

## 阶段划分

1. 适配器基础层：补齐 UM/CM/Margin 的查询、下单、撤单、成交方法和单元测试。
2. 只读页面迁移：余额、仓位、开放订单、成交记录按账户类型路由。
3. 手动订单迁移：U 本位、币本位手动开平仓和撤单按账户类型路由。
4. CTA 统一账户补齐：U 本位 CTA、币本位 CTA、半套、ADL、TPSL 全部走适配器。
5. 买币兑换迁移：统一账户买 ETH/卖 ETH 走 `/papi/v1/margin/order`，保留普通账户旧流程。
6. 后台净值和资金管理：统一账户净值、账户管理、转账相关功能独立实现。
7. 部署验证：本地单测、服务器单测、只读 API 验证、Web 页面可视化验证。

## 验收标准

- 普通账户功能入口和旧测试保持通过。
- 统一账户所有已支持功能不再调用旧 `fapi/dapi/sapi` 私有交易接口。
- 统一账户不支持的功能有明确错误消息。
- `admin_v3/tests` 覆盖适配器路由、空参数、订单/撤单/成交查询。
- 服务器部署后 `admin_v3.service` 为 active，登录页返回 200。
- 真实账户验证只做只读或 dry-run，不在验证脚本里下单。

## 官方接口依据

- Portfolio Margin base endpoint: `https://papi.binance.com`
- UM 下单: `POST /papi/v1/um/order`
- CM 下单: `POST /papi/v1/cm/order`
- Margin 买卖币: `POST /papi/v1/margin/order`
- 账户信息: `GET /papi/v1/account`
- 账户余额: `GET /papi/v1/balance`
- UM 仓位: `GET /papi/v1/um/positionRisk`
- CM 仓位: `GET /papi/v1/cm/positionRisk`
