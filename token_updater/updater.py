"""Token 同步服务 - 按需启动浏览器"""
import httpx
from datetime import datetime
from typing import Optional, Dict, Any
from .config import config
from .browser import browser_manager
from .database import profile_db
from .logger import logger


class TokenSyncer:
    """Token 同步器"""
    
    def __init__(self):
        self._total_sync_count = 0
        self._total_error_count = 0
        self._last_batch_time: Optional[datetime] = None
    
    async def sync_profile(self, profile_id: int) -> Dict[str, Any]:
        """同步单个 profile"""
        profile = await profile_db.get_profile(profile_id)
        if not profile:
            return {"success": False, "error": "Profile 不存在"}
        
        logger.info(f"[{profile['name']}] 开始同步...")
        
        # 提取 token (按需启动浏览器，用完即关)
        token = await browser_manager.extract_token(profile_id)
        
        if not token:
            await profile_db.update_profile(
                profile_id,
                last_sync_time=datetime.now().isoformat(),
                last_sync_result="failed: no token",
                error_count=profile.get("error_count", 0) + 1
            )
            self._total_error_count += 1
            return {"success": False, "error": "无法提取 Token，请先登录"}
        
        # 推送到 Flow2API
        result = await self._push_to_flow2api(token)
        
        if result["success"]:
            await profile_db.update_profile(
                profile_id,
                email=result.get("email", profile.get("email")),
                last_sync_time=datetime.now().isoformat(),
                last_sync_result=f"success: {result.get('action', 'synced')}",
                sync_count=profile.get("sync_count", 0) + 1
            )
            self._total_sync_count += 1
            logger.info(f"[{profile['name']}] 同步成功")
        else:
            await profile_db.update_profile(
                profile_id,
                last_sync_time=datetime.now().isoformat(),
                last_sync_result=f"failed: {result.get('error', 'unknown')}",
                error_count=profile.get("error_count", 0) + 1
            )
            self._total_error_count += 1
            logger.error(f"[{profile['name']}] 同步失败: {result.get('error')}")
        
        return result
    
    async def sync_all_profiles(self) -> Dict[str, Any]:
        """同步所有活跃 profile"""
        if not config.connection_token:
            return {"success": False, "error": "未配置 CONNECTION_TOKEN"}
        
        logger.info("=" * 40)
        logger.info("开始批量同步...")
        
        self._last_batch_time = datetime.now()
        profiles = await profile_db.get_active_profiles()
        
        results = []
        success_count = 0
        error_count = 0
        
        for profile in profiles:
            result = await self.sync_profile(profile["id"])
            results.append({
                "profile_id": profile["id"],
                "profile_name": profile["name"],
                **result
            })
            if result["success"]:
                success_count += 1
            else:
                error_count += 1
        
        logger.info(f"批量同步完成: 成功 {success_count}, 失败 {error_count}")
        
        return {
            "success": True,
            "total": len(profiles),
            "success_count": success_count,
            "error_count": error_count,
            "results": results
        }
    
    async def _push_to_flow2api(self, session_token: str) -> Dict[str, Any]:
        """推送到 Flow2API"""
        if not config.connection_token:
            return {"success": False, "error": "未配置 CONNECTION_TOKEN"}
        
        url = f"{config.flow2api_url}/api/plugin/update-token"
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    url,
                    json={"session_token": session_token},
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {config.connection_token}"
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    # 从 message 提取 email
                    email = None
                    msg = data.get("message", "")
                    if " for " in msg:
                        email = msg.split(" for ")[-1]
                    
                    return {
                        "success": True,
                        "action": data.get("action"),
                        "message": msg,
                        "email": email
                    }
                else:
                    return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "total_sync_count": self._total_sync_count,
            "total_error_count": self._total_error_count,
            "last_batch_time": self._last_batch_time.isoformat() if self._last_batch_time else None,
            "flow2api_url": config.flow2api_url,
            "has_connection_token": bool(config.connection_token),
            "refresh_interval_minutes": config.refresh_interval
        }


token_syncer = TokenSyncer()
