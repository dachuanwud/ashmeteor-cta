import os
from cta_api.cta_core import *

if __name__=='__main__':
    for rule_type in rule_type_list:
        print('开始计算基准数据')
        multiple_process = False  # 设置是否并行，True为并行，False为串行
        para_curve_df = base_data(symbol_list,rule_type,multiple_process)

        # === 保存回测后的结果
        result_path = root_path + '/data/output/para/'
        if os.path.exists(result_path) == False:
            os.makedirs(result_path)
        para_curve_df.to_csv(os.path.join(result_path,f'基准&{leverage_rate}&{rule_type}.csv'), index=False, encoding='gbk')  # 以GBK编码并且删除index保存csv文件

        print('开始计算策略数据')
        # === 开始进行回测
        stg_date(symbol_list,rule_type,multiple_process)



