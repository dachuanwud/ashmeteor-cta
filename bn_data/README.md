# 数据处理脚本说明

该文档提供了关于数据处理脚本的详细信息，包括如何安装环境、运行程序以及数据结果的说明。

## 概述

该脚本用于处理交易数据，包括获取、下载、清理旧数据、合并和分析等步骤，最终生成中性PKL数据文件。

## 前置条件

* 确保所有依赖库已安装。
* 配置文件 (config.py) 中的参数正确配置。

## 环境安装

### 1. 安装miniconda
- miniconda官方网站:https://docs.anaconda.com/miniconda/
- (windows)在windows系统里，打开windows powershell，执行以下命令

```
curl https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe -o miniconda.exe
Start-Process -FilePath ".\miniconda.exe" -ArgumentList "/S" -Wait
del miniconda.exe
```

- 如果windows powershell执行命令失败，下载到本地安装即可

    https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe

- (Linux)进入终端，执行命令

```
mkdir -p ~/miniconda3
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda3/miniconda.sh
bash ~/miniconda3/miniconda.sh -b -u -p ~/miniconda3
rm ~/miniconda3/miniconda.sh
```

- 配置conda环境变量

```
~\Miniconda3
~\Miniconda3\Scripts
~\Miniconda3\Library\bin
```

- (windows环境)禁用powershell安全策略

```
set-ExecutionPolicy RemoteSigned
```

- 执行```conda init```初始化conda环境


### 2. 创建虚拟环境

打开终端（或命令提示符），执行以下命令创建虚拟环境：

```
conda create -n get_crypto python==3.12.0
```

确保已安装Python 3.7或更高版本。可以从Python官网下载。

3. 激活虚拟环境

```
conda activate get_crypto
```

4. 安装依赖库
    
    确保在虚拟环境中，执行以下命令安装依赖库：
```
pip install -r requirements.txt
```

5. 执行程序，在虚拟环境里执行

```
python main.py
```

## 配置文件说明

在运行脚本前，请确保config.py文件配置正确。该文件应包含以下参数：

### 路径配置

- ```root_path```: 脚本的根目录路径。
- ```market_path```: 存储市场数据的路径。自动创建 output/market 目录。
- ```funding_path```: 存储资金数据的路径。位于 market_path/funding 下。
- ```pickle_path```: 存储生成的 PKL 数据文件的路径。位于 output/pickle_data 下。


### 系统配置

- ```cpu```: 可用的 CPU 核心数量，用于并发处理。
- ```CONCURRENCY```: 并发级别，默认为 CPU 核心数的两倍。
- ```semaphore```: 控制并发请求的信号量，最大值为 2 * cpu 和 8 之间的较小值。
- ```api_semaphore```: 控制 API 请求的信号量，最大值为 2 * cpu 和 2 之间的较小值。

### 网络配置

- ```proxy```: 代理服务器地址，用于网络请求。
- ```use_proxy_download_file```: 是否使用代理下载文件，布尔值。
- ```file_proxy```: 下载文件时使用的代理地址。

### 下载与分析配置

- ```blind```: 网络请求失败时是否打印异常信息，True 为不打印，False 为打印。
- ```thunder```: 是否快速更新，布尔值。
- ```retry_times```: 下载失败时的重试次数

### 数据完整性配置

- ```force_analyse```: 是否强制进行数据完整性分析，True 为强制分析。
- ```need_analyse_set```: 需要进行完整性分析的目录集合。
- ```daily_updated_set```: 每日更新的数据集合。
- ```daily_err_occur```: 上次更新时是否发生异常中断，布尔值。

### 更新配置

- ```update_to_now```: 是否更新至最近时间，布尔值。
- ```rolling_period```: 滚动更新的时间周期，以小时为单位。

### URL 配置

- ```BASE_URL```: 数据的基础 URL。
- ```root_center_url```: 数据的中心 URL。

### 交易配置

- ```SETTLED_SWAP_SYMBOLS```: 已结算的合约交易对及其时间范围。
- ```SETTLED_SPOT_SYMBOLS```: 已结算的现货交易对。
- ```swap_delist_symbol_set```: 已退市的合约交易对集合。

### 数据前缀配置

- ```prefix```: 数据前缀路径，取决于交易类型。
- ```metrics_prefix```: 指标数据的前缀路径，仅用于合约交易

### 时间间隔配置

- ```interval_microsecond```: 各时间间隔的微秒数。
- ```interval_param```: 各时间间隔的 relativedelta 参数。

## 主要功能

1. 初始化设置
    - 打印 CPU 核心数。
    - 获取当前时间作为起始时间。
2. 获取交易对信息
    - 调用 async_get_usdt_symbols 获取 USDT 交易对。
    - 根据交易类型过滤交易对。

3. 获取数据目录
    - 异步获取每日和每月的数据列表。
    - 打印最近两个月的每日和每月数据包数量。

4. 清理旧数据
    - 调用 clean_old_daily_zip 清理旧的每日数据。

5. 下载数据
    - 随机打乱数据包列表以优化网络带宽使用。
    - 异步下载所有数据包。
    - 处理下载错误并重试。

6. 合并数据
    - 将每日数据合并为每月数据。
    - 更新最新数据的时间戳。

7. 分析数据
    - 根据需要分析下载的数据。

8. 生成PKL数据
    - 生成中性PKL数据文件。

## 注意事项
- 确保网络连接正常，以便下载和处理数据。
- 确保有足够的磁盘空间来存储下载的数据和生成的文件。

