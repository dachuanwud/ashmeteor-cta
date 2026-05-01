# CTA 回测工程 Agent 指南

## 工程定位

这是一个 Python 加密货币 CTA 研究与运营工程，主要由三块组成：

- `crypto_cta/`：本地 CTA 回测框架，负责整理 K 线、运行单参数/多参数回测、计算资金曲线和评价指标、输出 CSV/HTML 结果。
- `bn_data/`：币安公开数据下载与后处理模块，负责拉取 daily/monthly K 线压缩包、合并数据、完整性检查，并生成 `crypto_cta` 可消费的数据。
- `admin_v3/`：Flask + SQLAlchemy 管理后台，包含账户/策略管理、CTA 状态、止盈止损任务、AMIS 页面和部分实盘操作能力。

这个工程目前不是标准 Python package。很多脚本依赖在对应目录下运行，并使用 `from config import *`、`from factors import *` 这类本地短导入。改动前先确认当前工作目录和 `PYTHONPATH`。

## 目录速览

- `crypto_cta/config.py`：回测配置，包括数据路径、币种池、策略名、参数、手续费/滑点/杠杆、最小下单量和输出字段。
- `crypto_cta/1_kline_data.py`：把 `bn_data` 下载的原始 zip/csv 数据转换成 `crypto_cta/data/pickle_data/<周期>/<币种>.pkl`。
- `crypto_cta/2_fast_backview.py`：按当前配置运行基准和单策略单参数回测。
- `crypto_cta/3_fastover.py`：参数遍历脚本，会多进程运行，且 `del_mode = True` 时会删除历史结果。
- `crypto_cta/4_strategy_evaluate.py`：结果评价和可视化入口。
- `crypto_cta/cta_api/`：回测核心、持仓转换、资金曲线、评价统计、绘图和工具函数。
- `crypto_cta/factors/`：回测策略因子目录。新策略应提供 `signal()` 和 `para_list()`。
- `crypto_cta/tests/`：unittest 测试，当前覆盖部分因子行为和 admin_v3 策略迁移预期。
- `bn_data/config.py`：下载路径、并发、代理、交易类型、币安 URL、数据完整性参数。
- `bn_data/main.py`：完整数据下载/更新流水线。
- `admin_v3/app.py`：Flask app 和路由。
- `admin_v3/functions.py`：ccxt 交易所对象、账户/策略工具、止盈止损、响应封装等核心业务函数。
- `admin_v3/model.py`：SQLAlchemy 表模型。
- `admin_v3/sql/`：建表 SQL。
- `admin_v3/templates/`、`admin_v3/static/`：AMIS 页面和前端静态资源。
- `docs/superpowers/plans/`：已有实施计划，可作为历史意图参考，但不要当作当前代码事实。

## 环境与常用命令

三块代码建议分别使用各自 README 中的环境，不要随意合并依赖。

`crypto_cta`：

```bash
cd /Users/houjl/Downloads/CTA回测/crypto_cta
conda create -n crypto_cta python==3.8.19
conda activate crypto_cta
pip install -r requirements.txt
```

`bn_data`：

```bash
cd /Users/houjl/Downloads/CTA回测/bn_data
conda create -n get_crypto python==3.12.0
conda activate get_crypto
pip install -r requirements.txt
```

`admin_v3`：

```bash
cd /Users/houjl/Downloads/CTA回测/admin_v3
conda create -n alpha_admin python==3.8.5
conda activate alpha_admin
pip install -r requirements.txt
```

运行 `crypto_cta` 单元测试优先用：

```bash
cd /Users/houjl/Downloads/CTA回测
PYTHONPATH=crypto_cta python3 -m unittest discover -s crypto_cta/tests -v
```

只跑单个测试文件：

```bash
cd /Users/houjl/Downloads/CTA回测
PYTHONPATH=crypto_cta python3 -m unittest crypto_cta.tests.test_boll_breakout -v
```

## 数据与输出安全

- 默认把 `bn_data/output/`、`crypto_cta/data/pickle_data/`、`crypto_cta/data/output/`、浏览器/cache 目录视为生成物；除非用户明确要求，不要整理、删除或提交这些文件。
- 不要随手运行 `bn_data/main.py`。它会联网下载币安数据、依赖代理配置、写入大量文件，运行时间也可能很长。
- 不要随手运行 `crypto_cta/3_fastover.py`。它会多进程遍历参数，且当前配置下可能删除历史结果。
- 改数据路径时必须同时检查 `bn_data/config.py` 和 `crypto_cta/config.py`；当前 `crypto_cta/config.py` 指向 `/Users/houjl/Downloads/CTA回测/bn_data/output/market/swap_1m`。
- 保持结果文件编码习惯。很多 CSV 使用 `encoding='gbk'`，贸然改成 UTF-8 可能影响中文列名和表格打开效果。

## 交易与实盘安全

- `admin_v3` 是运营/实盘相关代码，`admin_v3/functions.py` 里有 ccxt 交易所对象和真实账户请求能力。
- 未经用户明确要求，不要调用实盘接口、下单/撤单/改杠杆相关函数、调度任务、止盈止损任务。
- 修改 admin 逻辑时优先做静态代码审查和单元级验证，不要默认启动 `admin_v3/app.py`。
- 如确实需要运行后台，先确认数据库 URI、`debug`、登录校验、IP 白名单和代理配置。
- `admin_v3/config.py` 当前包含本地数据库 URI、密钥/机器人 key 等敏感值。最终回复不要复述具体值，也不要把它们复制到文档或新文件中。

## 代码改动原则

- 保持小改动、局部改动。工程当前是脚本式结构，广泛使用全局配置和短导入，避免无需求的大重构。
- 新增 `crypto_cta` 因子时，遵循现有因子模块接口：
  - `signal(df, para=[...], proportion=1, leverage_rate=1)` 返回带稀疏 `signal` 列的 DataFrame。
  - `para_list()` 返回给 `3_fastover.py` 遍历的参数组合。
  - 需要沿用框架止损时，调用 `process_stop_loss_close()`。
  - 去掉重复信号，只保留仓位切换点，确保 `position_for_future()` 看到的是状态转换。
- pandas 逻辑要写清楚，特别注意链式赋值、in-place 修改、`shift()`、索引连续性和 NaN 处理。
- 从 `admin_v3/factors.py` 迁移策略到 `crypto_cta/factors/` 时，先用测试锁住行为，再抽公共工具或简化公式。
- 不要在无关任务中修改 `config.py` 的全局默认值。需要换币种、周期、日期或策略时，优先说明运行配置，必要时再询问用户。
- 不要改 `admin_v3/static/sdk/` 下的第三方前端静态资源，除非用户明确要求升级或替换。

## 验证策略

按改动风险选择最轻验证：

- 只改因子：运行对应的 `crypto_cta/tests/test_*.py`。
- 改回测核心：运行全部 `crypto_cta/tests`；如果本地数据存在，再做一个小范围单币种回测。
- 改下载器：默认不要做完整联网下载；优先测纯函数、路径生成或小范围 dry check。
- 改 admin 路由/工具：优先 import 级或函数级验证；只有用户明确要求时才启动 Flask、连接 DB 或触发外部接口。
- 只改文档：读回 markdown，确认路径、命令和敏感信息没有写错。

## 当前已知状态

- 当前 git 工作区可能是整体新导入状态，多个源码目录都是 untracked；不要把未跟踪目录当成可删除垃圾。
- `crypto_cta/tests/test_admin_v3_strategy_migration.py` 期望存在 `adapt_bolling`、`adapt_bolling_reverse`、`dc_flash`、`mtm_bolling` 等迁移因子。如果这些模块还没实现，该测试失败是符合迁移计划预期的。
- `crypto_cta/factors/boll_breakout.py` 是当前较清晰的新式因子模板。
- `admin_v3/factors.py` 里有大量旧接口策略公式。不要为了省事让 `crypto_cta` 直接依赖它，除非用户接受这种耦合。

## 与用户协作方式

- 默认用中文回答。
- 策略/回测问题先给直接结论，再引用具体脚本、函数或配置项支撑。
- 做代码改动时说明改了哪些文件，以及跑了什么验证、结果如何。
- 遇到会下载大量数据、触发实盘交易、改数据库、覆盖/删除回测结果的命令，先停下来征求用户确认。
