"""Token Updater API - 含外部 API"""
import secrets
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional
from .browser import browser_manager
from .updater import token_syncer
from .database import profile_db
from .proxy_utils import validate_proxy_format
from .config import config
from .logger import logger

app = FastAPI(title="Flow2API Token Updater", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_sessions = set()


# ========== Models ==========

class LoginRequest(BaseModel):
    password: str

class CreateProfileRequest(BaseModel):
    name: str
    remark: Optional[str] = ""
    proxy_url: Optional[str] = ""

class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    remark: Optional[str] = None
    is_active: Optional[bool] = None
    proxy_url: Optional[str] = None
    proxy_enabled: Optional[bool] = None

class UpdateConfigRequest(BaseModel):
    flow2api_url: Optional[str] = None
    connection_token: Optional[str] = None
    refresh_interval: Optional[int] = None


# ========== Auth ==========

async def verify_session(authorization: str = Header(None)):
    """验证 Web UI session"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization[7:]
    if token not in active_sessions:
        raise HTTPException(status_code=401, detail="登录已过期")
    return token


async def verify_api_key(x_api_key: str = Header(None)):
    """验证外部 API Key"""
    if not config.api_key:
        raise HTTPException(status_code=500, detail="未配置 API_KEY")
    if x_api_key != config.api_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return x_api_key


@app.post("/api/login")
async def login(request: LoginRequest):
    if not config.admin_password:
        raise HTTPException(status_code=500, detail="未设置 ADMIN_PASSWORD")
    if request.password != config.admin_password:
        raise HTTPException(status_code=401, detail="密码错误")
    
    session_token = secrets.token_urlsafe(32)
    active_sessions.add(session_token)
    return {"success": True, "token": session_token}


@app.post("/api/logout")
async def logout(token: str = Depends(verify_session)):
    active_sessions.discard(token)
    return {"success": True}


@app.get("/api/auth/check")
async def check_auth():
    return {"need_password": bool(config.admin_password)}


# ========== Static ==========

@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse("/app/token_updater/static/index.html")


# ========== Status ==========

@app.get("/api/status")
async def get_status(token: str = Depends(verify_session)):
    profiles = await profile_db.get_all_profiles()
    return {
        "browser": browser_manager.get_status(),
        "syncer": token_syncer.get_status(),
        "profiles": {
            "total": len(profiles),
            "logged_in": sum(1 for p in profiles if p.get("is_logged_in")),
            "active": sum(1 for p in profiles if p.get("is_active"))
        },
        "config": {
            "flow2api_url": config.flow2api_url,
            "refresh_interval": config.refresh_interval,
            "has_connection_token": bool(config.connection_token),
            "has_api_key": bool(config.api_key)
        }
    }


# ========== Profiles ==========

@app.get("/api/profiles")
async def get_profiles(token: str = Depends(verify_session)):
    profiles = await profile_db.get_all_profiles()
    active_id = browser_manager.get_active_profile_id()
    
    for p in profiles:
        p["is_browser_active"] = (p["id"] == active_id)
        
        # 如果浏览器正在运行，实时检测登录状态
        if p["id"] == active_id and browser_manager._active_context:
            try:
                cookies = await browser_manager._active_context.cookies("https://labs.google")
                is_logged_in = any(c["name"] == config.session_cookie_name for c in cookies)
                if is_logged_in != bool(p.get("is_logged_in")):
                    await profile_db.update_profile(p["id"], is_logged_in=int(is_logged_in))
                    p["is_logged_in"] = int(is_logged_in)
            except:
                pass
        
        # 验证代理格式
        if p.get("proxy_url"):
            valid, msg = validate_proxy_format(p["proxy_url"])
            p["proxy_status"] = msg
    
    return profiles


@app.post("/api/profiles")
async def create_profile(request: CreateProfileRequest, token: str = Depends(verify_session)):
    if await profile_db.get_profile_by_name(request.name):
        raise HTTPException(status_code=400, detail="名称已存在")
    
    # 验证代理格式
    if request.proxy_url:
        valid, msg = validate_proxy_format(request.proxy_url)
        if not valid:
            raise HTTPException(status_code=400, detail=f"代理格式错误: {msg}")
    
    profile_id = await profile_db.add_profile(request.name, request.remark, request.proxy_url)
    return {"success": True, "profile_id": profile_id}


@app.get("/api/profiles/{profile_id}")
async def get_profile(profile_id: int, token: str = Depends(verify_session)):
    profile = await profile_db.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="不存在")
    profile["is_browser_active"] = (profile_id == browser_manager.get_active_profile_id())
    return profile


@app.put("/api/profiles/{profile_id}")
async def update_profile(profile_id: int, request: UpdateProfileRequest, token: str = Depends(verify_session)):
    profile = await profile_db.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="不存在")
    
    # 验证代理格式
    if request.proxy_url:
        valid, msg = validate_proxy_format(request.proxy_url)
        if not valid:
            raise HTTPException(status_code=400, detail=f"代理格式错误: {msg}")
    
    update_data = {}
    if request.name is not None:
        update_data["name"] = request.name
    if request.remark is not None:
        update_data["remark"] = request.remark
    if request.is_active is not None:
        update_data["is_active"] = int(request.is_active)
    if request.proxy_url is not None:
        update_data["proxy_url"] = request.proxy_url
    if request.proxy_enabled is not None:
        update_data["proxy_enabled"] = int(request.proxy_enabled)
    
    if update_data:
        await profile_db.update_profile(profile_id, **update_data)
    return {"success": True}


@app.delete("/api/profiles/{profile_id}")
async def delete_profile(profile_id: int, token: str = Depends(verify_session)):
    profile = await profile_db.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="不存在")
    
    await browser_manager.close_browser(profile_id)
    await browser_manager.delete_profile_data(profile_id)
    await profile_db.delete_profile(profile_id)
    return {"success": True}


@app.post("/api/profiles/{profile_id}/enable")
async def enable_profile(profile_id: int, token: str = Depends(verify_session)):
    await profile_db.update_profile(profile_id, is_active=1)
    return {"success": True}


@app.post("/api/profiles/{profile_id}/disable")
async def disable_profile(profile_id: int, token: str = Depends(verify_session)):
    await profile_db.update_profile(profile_id, is_active=0)
    return {"success": True}


@app.get("/api/profiles/{profile_id}/isolation")
async def check_isolation(profile_id: int, token: str = Depends(verify_session)):
    """检查 Profile 隔离状态"""
    return await browser_manager.verify_isolation(profile_id)


# ========== Browser ==========

@app.post("/api/profiles/{profile_id}/launch")
async def launch_browser(profile_id: int, token: str = Depends(verify_session)):
    success = await browser_manager.launch_for_login(profile_id)
    if not success:
        raise HTTPException(status_code=500, detail="启动失败")
    return {"success": True, "message": "请通过 VNC 登录"}


@app.post("/api/profiles/{profile_id}/close")
async def close_browser(profile_id: int, token: str = Depends(verify_session)):
    await browser_manager.close_browser(profile_id)
    return {"success": True}


@app.post("/api/profiles/{profile_id}/check-login")
async def check_login_status(profile_id: int, token: str = Depends(verify_session)):
    """检查并更新登录状态"""
    profile = await profile_db.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="不存在")
    
    # 如果浏览器正在运行，从当前 context 检查
    if browser_manager.get_active_profile_id() == profile_id and browser_manager._active_context:
        try:
            cookies = await browser_manager._active_context.cookies("https://labs.google")
            is_logged_in = any(c["name"] == config.session_cookie_name for c in cookies)
            await profile_db.update_profile(profile_id, is_logged_in=int(is_logged_in))
            return {"success": True, "is_logged_in": is_logged_in, "source": "active_browser"}
        except:
            pass
    
    # 否则启动浏览器快速检查
    token_found = await browser_manager.extract_token(profile_id)
    is_logged_in = token_found is not None
    
    return {"success": True, "is_logged_in": is_logged_in, "source": "extracted"}


@app.post("/api/profiles/{profile_id}/login")
async def open_login_page(profile_id: int, token: str = Depends(verify_session)):
    success = await browser_manager.launch_for_login(profile_id)
    if not success:
        raise HTTPException(status_code=500, detail="启动失败")
    return {"success": True, "message": "请通过 VNC 登录"}


# ========== Token (Web UI) ==========

@app.post("/api/profiles/{profile_id}/extract")
async def extract_token(profile_id: int, token: str = Depends(verify_session)):
    extracted = await browser_manager.extract_token(profile_id)
    if extracted:
        return {"success": True, "token_length": len(extracted)}
    return {"success": False, "message": "未找到 Token"}


@app.post("/api/profiles/{profile_id}/sync")
async def sync_profile(profile_id: int, token: str = Depends(verify_session)):
    return await token_syncer.sync_profile(profile_id)


@app.post("/api/sync-all")
async def sync_all_profiles(token: str = Depends(verify_session)):
    return await token_syncer.sync_all_profiles()


# ========== Config ==========

@app.get("/api/config")
async def get_config(token: str = Depends(verify_session)):
    return {
        "flow2api_url": config.flow2api_url,
        "refresh_interval": config.refresh_interval,
        "has_connection_token": bool(config.connection_token),
        "connection_token_preview": f"{config.connection_token[:10]}..." if config.connection_token else "",
        "has_api_key": bool(config.api_key),
        "api_key_preview": f"{config.api_key[:10]}..." if config.api_key else ""
    }


@app.post("/api/config")
async def update_config(request: UpdateConfigRequest, token: str = Depends(verify_session)):
    if request.flow2api_url:
        config.flow2api_url = request.flow2api_url
    if request.connection_token:
        config.connection_token = request.connection_token
    if request.refresh_interval:
        config.refresh_interval = request.refresh_interval
    return {"success": True}


# ========== 外部 API (需要 API Key) ==========

@app.get("/v1/profiles")
async def ext_list_profiles(api_key: str = Depends(verify_api_key)):
    """外部 API: 列出所有 Profile"""
    profiles = await profile_db.get_all_profiles()
    return {
        "profiles": [
            {
                "id": p["id"],
                "name": p["name"],
                "email": p.get("email"),
                "is_logged_in": bool(p.get("is_logged_in")),
                "is_active": bool(p.get("is_active"))
            }
            for p in profiles
        ]
    }


@app.get("/v1/profiles/{profile_id}/token")
async def ext_get_token(profile_id: int, api_key: str = Depends(verify_api_key)):
    """
    外部 API: 获取指定 Profile 的 Session Token
    
    会启动浏览器提取最新 token，然后返回
    """
    profile = await profile_db.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    if not profile.get("is_active"):
        raise HTTPException(status_code=400, detail="Profile is disabled")
    
    logger.info(f"[API] 请求 Profile {profile['name']} 的 Token")
    
    # 提取 token
    token = await browser_manager.extract_token(profile_id)
    
    if not token:
        raise HTTPException(status_code=400, detail="Failed to extract token, please login first")
    
    return {
        "success": True,
        "profile_id": profile_id,
        "profile_name": profile["name"],
        "email": profile.get("email"),
        "session_token": token
    }


@app.post("/v1/profiles/{profile_id}/sync")
async def ext_sync_profile(profile_id: int, api_key: str = Depends(verify_api_key)):
    """外部 API: 同步指定 Profile 到 Flow2API"""
    profile = await profile_db.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    logger.info(f"[API] 同步 Profile {profile['name']}")
    return await token_syncer.sync_profile(profile_id)


@app.get("/v1/profiles/by-name/{name}/token")
async def ext_get_token_by_name(name: str, api_key: str = Depends(verify_api_key)):
    """外部 API: 通过名称获取 Token"""
    profile = await profile_db.get_profile_by_name(name)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return await ext_get_token(profile["id"], api_key)


@app.get("/v1/profiles/by-email/{email}/token")
async def ext_get_token_by_email(email: str, api_key: str = Depends(verify_api_key)):
    """外部 API: 通过邮箱获取 Token"""
    profiles = await profile_db.get_all_profiles()
    profile = next((p for p in profiles if p.get("email") == email), None)
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return await ext_get_token(profile["id"], api_key)


# ========== Health ==========

@app.get("/health")
async def health():
    return {"status": "ok"}
