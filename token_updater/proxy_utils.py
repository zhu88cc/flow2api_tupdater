"""代理格式解析工具 - 支持多种格式"""
import re
from typing import Optional, Dict
from urllib.parse import urlparse, quote


def parse_proxy(proxy_str: str) -> Optional[Dict]:
    """
    解析代理字符串，支持多种格式：
    
    HTTP/HTTPS:
    - http://host:port
    - http://user:pass@host:port
    - https://host:port
    
    SOCKS5:
    - socks5://host:port
    - socks5://user:pass@host:port
    - socks5h://host:port (DNS 通过代理解析)
    - socks5h://user:pass@host:port
    
    简写格式 (自动识别):
    - host:port (默认 http)
    - user:pass@host:port (默认 http)
    
    Returns:
        {"server": "protocol://host:port", "username": "...", "password": "..."}
        或 None (无效格式)
    """
    if not proxy_str or not proxy_str.strip():
        return None
    
    proxy_str = proxy_str.strip()
    
    # 如果没有协议前缀，尝试智能识别
    if "://" not in proxy_str:
        # 检查是否有认证信息
        if "@" in proxy_str:
            proxy_str = f"http://{proxy_str}"
        else:
            proxy_str = f"http://{proxy_str}"
    
    try:
        parsed = urlparse(proxy_str)
        
        # 验证协议
        valid_schemes = ["http", "https", "socks5", "socks5h"]
        if parsed.scheme not in valid_schemes:
            return None
        
        # 验证 host 和 port
        if not parsed.hostname or not parsed.port:
            return None
        
        result = {
            "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
        }
        
        # 提取认证信息
        if parsed.username:
            result["username"] = parsed.username
        if parsed.password:
            result["password"] = parsed.password
        
        return result
        
    except Exception:
        return None


def format_proxy_for_playwright(proxy_config: Dict) -> Dict:
    """
    将解析后的代理配置转换为 Playwright 格式
    
    Playwright proxy 格式:
    {
        "server": "http://host:port" 或 "socks5://host:port",
        "username": "...",  # 可选
        "password": "..."   # 可选
    }
    """
    if not proxy_config:
        return None
    
    result = {"server": proxy_config["server"]}
    
    if "username" in proxy_config:
        result["username"] = proxy_config["username"]
    if "password" in proxy_config:
        result["password"] = proxy_config["password"]
    
    return result


def validate_proxy_format(proxy_str: str) -> tuple[bool, str]:
    """
    验证代理格式
    
    Returns:
        (is_valid, message)
    """
    if not proxy_str or not proxy_str.strip():
        return True, "无代理"
    
    result = parse_proxy(proxy_str)
    
    if result is None:
        return False, "无效的代理格式"
    
    # 构建描述
    server = result["server"]
    has_auth = "username" in result
    
    if "socks5h" in server:
        proto = "SOCKS5H (远程DNS)"
    elif "socks5" in server:
        proto = "SOCKS5"
    elif "https" in server:
        proto = "HTTPS"
    else:
        proto = "HTTP"
    
    auth_str = "带认证" if has_auth else "无认证"
    
    return True, f"{proto} {auth_str}"


# 测试用例
if __name__ == "__main__":
    test_cases = [
        "127.0.0.1:1080",
        "user:pass@127.0.0.1:1080",
        "http://127.0.0.1:8080",
        "http://user:pass@127.0.0.1:8080",
        "socks5://127.0.0.1:1080",
        "socks5://user:pass@127.0.0.1:1080",
        "socks5h://127.0.0.1:1080",
        "socks5h://user:p@ss:word@127.0.0.1:1080",
        "",
        "invalid",
    ]
    
    for tc in test_cases:
        valid, msg = validate_proxy_format(tc)
        parsed = parse_proxy(tc)
        print(f"{tc!r:45} -> valid={valid}, msg={msg}, parsed={parsed}")
