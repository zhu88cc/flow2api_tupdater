"""日志模块"""
import logging
import sys
import os

# 确保日志目录存在
log_dir = "/app/logs"
os.makedirs(log_dir, exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("token_updater")

# 添加文件 handler
try:
    file_handler = logging.FileHandler(os.path.join(log_dir, "token_updater.log"))
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(file_handler)
except Exception:
    pass  # 忽略文件日志错误
