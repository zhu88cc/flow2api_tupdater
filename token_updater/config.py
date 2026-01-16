"""Token Updater 配置"""
import os
import secrets
from pydantic import BaseModel


class Config(BaseModel):
    """配置类"""
    # 管理员密码 (Web UI)
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")
    
    # 外部 API Key (供其他服务调用)
    api_key: str = os.getenv("API_KEY", "")
    
    # Flow2API 服务器配置
    flow2api_url: str = os.getenv("FLOW2API_URL", "http://host.docker.internal:8000")
    connection_token: str = os.getenv("CONNECTION_TOKEN", "")
    
    # 刷新间隔 (分钟)
    refresh_interval: int = int(os.getenv("REFRESH_INTERVAL", "60"))
    
    # 浏览器配置
    profiles_dir: str = "/app/profiles"  # 多 profile 目录
    headless: bool = False  # VNC 模式下必须为 False
    
    # Google Labs URL
    labs_url: str = "https://labs.google/fx/tools/flow"  # 提取 token 用
    login_url: str = "https://labs.google/fx/api/auth/signin/google"  # 登录用
    
    # Cookie 名称
    session_cookie_name: str = "__Secure-next-auth.session-token"
    
    # API 端口
    api_port: int = int(os.getenv("API_PORT", "8080"))
    
    # 数据库路径
    db_path: str = "/app/data/profiles.db"


config = Config()
