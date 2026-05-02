import time
from functools import wraps

def get_list_dimension(lst):
    '''
    获取list的维数
    '''
    if not isinstance(lst, list):
        return 0
    elif not lst:
        return 1
    else:
        return 1 + max(get_list_dimension(item) for item in lst)


def get_parameter_dimension(para_list):
    '''
    获取策略单个参数组合的参数个数。
    例如 [10, 20] 和 [[10], [20]] 都是单参数遍历，[[10, 2], [20, 3]] 是双参数遍历。
    '''
    if not para_list:
        return 0
    first_para = para_list[0]
    if isinstance(first_para, (list, tuple)):
        return len(first_para)
    return 1
    

# 计时器，计算函数运行时间
def timing_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()  # 记录开始时间
        result = func(*args, **kwargs)  # 执行函数
        end_time = time.time()  # 记录结束时间
        duration = end_time - start_time  # 计算运行时间
        print(f"函数'{func.__name__}'花费了{duration:.4f}秒完成.")
        return result
    return wrapper
