"""多 Profile 浏览器管理 - 完全隔离，按需启动"""
import asyncio
import os
import shutil
from datetime import datetime
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, BrowserContext, Playwright
from .config import config
from .database import profile_db
from .proxy_utils import parse_proxy, format_proxy_for_playwright
from .logger import logger


class BrowserManager:
    """浏览器管理器 - 每个 Profile 完全隔离"""
    
    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._active_context: Optional[BrowserContext] = None
        self._active_profile_id: Optional[int] = None
    
    async def start(self):
        """启动 Playwright"""
        logger.info("启动 Playwright...")
        self._playwright = await async_playwright().start()
        os.makedirs(config.profiles_dir, exist_ok=True)
        logger.info("Playwright 已启动")
    
    async def stop(self):
        """停止 Playwright"""
        await self._close_active()
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("Playwright 已关闭")
    
    async def _close_active(self):
        """关闭当前活动的浏览器"""
        if self._active_context:
            try:
                await self._active_context.close()
            except:
                pass
            self._active_context = None
            self._active_profile_id = None
            logger.info("浏览器已关闭")
    
    def _get_profile_dir(self, profile_name: str) -> str:
        """获取 Profile 独立目录 (确保隔离)"""
        # 每个 profile 有独立的用户数据目录
        # 包含: cookies, localStorage, sessionStorage, IndexedDB 等
        return os.path.join(config.profiles_dir, profile_name)
    
    async def _launch_context(self, profile: Dict[str, Any]) -> BrowserContext:
        """启动完全隔离的浏览器上下文"""
        profile_dir = self._get_profile_dir(profile["name"])
        os.makedirs(profile_dir, exist_ok=True)
        
        # 解析代理配置
        proxy = None
        if profile.get("proxy_enabled") and profile.get("proxy_url"):
            proxy_config = parse_proxy(profile["proxy_url"])
            if proxy_config:
                proxy = format_proxy_for_playwright(proxy_config)
                logger.info(f"[{profile['name']}] 使用代理: {proxy['server']}")
        
        # 启动持久化上下文 - 每个 profile 完全独立
        # user_data_dir 确保 cookies/storage 隔离
        context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,  # 独立数据目录 = 完全隔离
            headless=config.headless,
            viewport={"width": 1280, "height": 720},
            locale="en-US",
            timezone_id="America/New_York",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            proxy=proxy,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1280,720",
            ],
            ignore_default_args=["--enable-automation"],
        )
        
        logger.info(f"[{profile['name']}] 浏览器已启动 (隔离目录: {profile_dir})")
        return context
    
    async def launch_for_login(self, profile_id: int) -> bool:
        """启动浏览器用于登录"""
        await self._close_active()
        
        profile = await profile_db.get_profile(profile_id)
        if not profile:
            logger.error(f"Profile {profile_id} 不存在")
            return False
        
        try:
            self._active_context = await self._launch_context(profile)
            self._active_profile_id = profile_id
            
            page = self._active_context.pages[0] if self._active_context.pages else await self._active_context.new_page()
            await page.goto(config.login_url, wait_until="networkidle")
            
            logger.info(f"[{profile['name']}] 请通过 VNC 登录")
            return True
        except Exception as e:
            logger.error(f"[{profile['name']}] 启动失败: {e}")
            return False
    
    async def close_browser(self, profile_id: int):
        """关闭浏览器 (关闭前检查登录状态)"""
        if self._active_profile_id == profile_id and self._active_context:
            # 关闭前检查登录状态
            try:
                cookies = await self._active_context.cookies("https://labs.google")
                is_logged_in = any(c["name"] == config.session_cookie_name for c in cookies)
                await profile_db.update_profile(profile_id, is_logged_in=int(is_logged_in))
                if is_logged_in:
                    logger.info(f"Profile {profile_id} 登录状态已保存")
            except:
                pass
            
            await self._close_active()
    
    async def extract_token(self, profile_id: int) -> Optional[str]:
        """提取 token (优先使用当前运行的浏览器)"""
        profile = await profile_db.get_profile(profile_id)
        if not profile:
            return None
        
        # 如果当前 profile 的浏览器正在运行，直接从中提取
        if self._active_profile_id == profile_id and self._active_context:
            logger.info(f"[{profile['name']}] 从运行中的浏览器提取 Token...")
            try:
                # 确保页面已加载
                page = self._active_context.pages[0] if self._active_context.pages else await self._active_context.new_page()
                current_url = page.url
                
                # 如果不在 labs.google 域名下，先导航过去
                if "labs.google" not in current_url:
                    await page.goto(config.labs_url, wait_until="networkidle")
                    await asyncio.sleep(2)
                
                cookies = await self._active_context.cookies("https://labs.google")
                token = None
                for cookie in cookies:
                    if cookie["name"] == config.session_cookie_name:
                        token = cookie["value"]
                        break
                
                if token:
                    logger.info(f"[{profile['name']}] Token 提取成功 (从运行中浏览器)")
                    await profile_db.update_profile(
                        profile_id,
                        is_logged_in=1,
                        last_token=token[:50] + "...",
                        last_token_time=datetime.now().isoformat()
                    )
                else:
                    logger.warning(f"[{profile['name']}] 未找到 Token (运行中浏览器)")
                    await profile_db.update_profile(profile_id, is_logged_in=0)
                
                return token
            except Exception as e:
                logger.error(f"[{profile['name']}] 从运行中浏览器提取失败: {e}")
                # 继续尝试启动新浏览器
        
        # 否则启动新浏览器提取
        context = None
        try:
            logger.info(f"[{profile['name']}] 启动浏览器提取 Token...")
            context = await self._launch_context(profile)
            
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(config.labs_url, wait_until="networkidle")
            await asyncio.sleep(3)
            
            # 只获取该 context 的 cookies (隔离)
            cookies = await context.cookies("https://labs.google")
            token = None
            for cookie in cookies:
                if cookie["name"] == config.session_cookie_name:
                    token = cookie["value"]
                    break
            
            if token:
                logger.info(f"[{profile['name']}] Token 提取成功")
                await profile_db.update_profile(
                    profile_id,
                    is_logged_in=1,
                    last_token=token[:50] + "...",
                    last_token_time=datetime.now().isoformat()
                )
            else:
                logger.warning(f"[{profile['name']}] 未找到 Token")
                await profile_db.update_profile(profile_id, is_logged_in=0)
            
            return token
            
        except Exception as e:
            logger.error(f"[{profile['name']}] 提取失败: {e}")
            return None
        finally:
            if context:
                await context.close()
                logger.info(f"[{profile['name']}] 浏览器已关闭")
    
    async def verify_isolation(self, profile_id: int) -> Dict[str, Any]:
        """验证 Profile 隔离性"""
        profile = await profile_db.get_profile(profile_id)
        if not profile:
            return {"success": False, "error": "Profile 不存在"}
        
        profile_dir = self._get_profile_dir(profile["name"])
        
        # 检查目录是否独立存在
        dir_exists = os.path.exists(profile_dir)
        
        # 检查是否有其他 profile 共享目录
        all_profiles = await profile_db.get_all_profiles()
        shared_with = []
        for p in all_profiles:
            if p["id"] != profile_id:
                other_dir = self._get_profile_dir(p["name"])
                if other_dir == profile_dir:
                    shared_with.append(p["name"])
        
        is_isolated = dir_exists and len(shared_with) == 0
        
        return {
            "success": True,
            "profile_name": profile["name"],
            "profile_dir": profile_dir,
            "dir_exists": dir_exists,
            "is_isolated": is_isolated,
            "shared_with": shared_with
        }
    
    async def delete_profile_data(self, profile_id: int):
        """删除 profile 数据目录"""
        profile = await profile_db.get_profile(profile_id)
        if profile:
            profile_dir = self._get_profile_dir(profile["name"])
            if os.path.exists(profile_dir):
                shutil.rmtree(profile_dir)
                logger.info(f"已删除: {profile_dir}")
    
    def get_active_profile_id(self) -> Optional[int]:
        return self._active_profile_id
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "is_running": self._playwright is not None,
            "active_profile_id": self._active_profile_id,
            "has_active_browser": self._active_context is not None,
            "profiles_dir": config.profiles_dir
        }


browser_manager = BrowserManager()
