import functools
import time
import random
from shared.logger import console

def retry(max_retries=3, delay=1.0, backoff=2.0, exceptions=(Exception,)):
    """
    通用重试装饰器。
    
    Args:
        max_retries: 最大重试次数
        delay: 初始等待时间（秒）
        backoff: 等待时间指数增长因子
        exceptions: 需要捕获并重试的异常类型元组
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tries = 0
            while tries < max_retries:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    tries += 1
                    if tries == max_retries:
                        raise e
                    
                    sleep_time = delay * (backoff ** (tries - 1)) + random.uniform(0, 0.1)
                    if hasattr(console, "print"):
                        console.print(f"[yellow]⚠️  {func.__name__} 失败 ({tries}/{max_retries}): {e}。{sleep_time:.1f}秒后重试...[/yellow]")
                    else:
                        print(f"⚠️  {func.__name__} 失败 ({tries}/{max_retries}): {e}。{sleep_time:.1f}秒后重试...")
                    
                    time.sleep(sleep_time)
        return wrapper
    return decorator
