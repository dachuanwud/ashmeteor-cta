from dataclasses import dataclass
from decimal import Decimal
import os

root_path = os.path.abspath(os.path.dirname(__file__))
data_path = os.path.join(root_path, 'data')
if not os.path.exists(data_path):
    os.mkdir(data_path)
deribit_path = os.path.join(data_path, 'deribit')
if not os.path.exists(deribit_path):
    os.mkdir(deribit_path)
alpha_path = os.path.join(data_path, 'alpha')
if not os.path.exists(alpha_path):
    os.mkdir(alpha_path)
fapi_path = os.path.join(data_path, 'fapi')
if not os.path.exists(fapi_path):
    os.mkdir(fapi_path)
dapi_path = os.path.join(data_path, 'dapi')
if not os.path.exists(dapi_path):
    os.mkdir(dapi_path)

debug = os.getenv('ASHMETEOR_DEBUG', '').lower() in ('1', 'true', 'yes')

# 链接mysql的uri
sql_uri = os.getenv('ASHMETEOR_SQL_URI', 'mysql+pymysql://root:password@localhost:3306/alpha')

# 生成谷歌验证码的密钥
google_key = os.getenv('ASHMETEOR_GOOGLE_KEY', '')

# 自动添加半套策略
auto_add_re = True

# 自动校准功能, 会导致半路自动上车
pos_infer = False

# 超级密码 临时有用可以用到
super_mm = os.getenv('ASHMETEOR_SUPER_MM', '')

# amis在线编辑器的域（debug模式下可用）（废弃，暂时用不到）
amis_edit_origin = 'https://aisuda.github.io'

# 实际部署的域(废弃，暂时用不到)
local_origin = ''

# 允许外部访问的ip白名单
# 允许外部访问的ip白名单
ip_white_list = [
    ip.strip()
    for ip in os.getenv('ASHMETEOR_IP_WHITE_LIST', '*').split(',')
    if ip.strip()
]

# 自动止盈止损不需要覆盖的策略
tpsl_blacklist = ['strategy1', 'strategy2']

# 自动止盈止损拉黑时间(单位：小时)
blacklist_hours = 48

# 吊灯止盈回调比例
takeprofit_drawdown_percentage = Decimal(0.1)

# 中性策略监测止盈止损频率
alpha_tpsl_time = '10s'

# CTA策略监测止盈止损频率
cta_tpsl_time = '30s'

# CTA策略是否使用bar内止损(默认方式), False则按照信号周期止损
# 注:选择False时 cta_tpsl_time可放大 减少权重消耗
cta_stoploss_inside_bar = False

# 企业微信机器人key
wechat_hook_key = os.getenv('ASHMETEOR_WECHAT_HOOK_KEY', '')

# 企业微信应用agentid
agent_id = 1000000

# 是否使用代理（debug时常用）
# proxy = {
#     'http': 'http://localhost:33210',
#     'https': 'http://localhost:33210',
# }

proxy = {}


# 声明可登录的用户
@dataclass
class User:
    id: int
    username: str


users = [
    User(i + 1, username.strip())
    for i, username in enumerate(
        os.getenv('ASHMETEOR_USERS', '猫妈').split(',')
    )
    if username.strip()
]
