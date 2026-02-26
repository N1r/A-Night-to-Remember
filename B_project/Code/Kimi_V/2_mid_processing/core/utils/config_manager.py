import os
import threading
from ruamel.yaml import YAML
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class ConfigManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ConfigManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        
        # 核心逻辑：根据环境变量 DOMAIN 决定加载哪个配置文件
        # 默认使用 'politics'，如果设置为 'general' 则加载 config.yaml
        self.domain = os.getenv('APP_DOMAIN', 'politics').lower()
        
        # 配置文件映射
        domain_config_map = {
            'politics': 'config.yaml',  # 目前默认是政治
            'bili_pro': 'config_bili_pro.yaml',
        }
        
        config_file = domain_config_map.get(self.domain, 'config.yaml')
        self.config_path = os.path.join(self.project_root, 'configs', config_file)
        
        self._load_config()
        self._initialized = True

    def _load_config(self):
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.data = self.yaml.load(f)

    def get(self, key, default=None):
        keys = key.split('.')
        value = self.data
        try:
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return value
        except Exception:
            return default

    def set(self, key, new_value):
        keys = key.split('.')
        current = self.data
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        current[keys[-1]] = new_value
        with open(self.config_path, 'w', encoding='utf-8') as f:
            self.yaml.dump(self.data, f)

# 导出单例快捷方法，保持与旧代码兼容性
_manager = ConfigManager()

def load_key(key):
    return _manager.get(key)

def update_key(key, value):
    return _manager.set(key, value)

def get_domain():
    return _manager.domain
