"""Token Updater 主入口 - 多 Profile 版"""
import asyncio
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from .api import app
from .browser import browser_manager
from .updater import token_syncer
from .database import profile_db
from .config import config
from .logger import logger


scheduler = AsyncIOScheduler()


async def scheduled_sync():
    """定时同步任务"""
    logger.info("=== 定时同步任务触发 ===")
    
    # 检查是否配置了 connection_token
    if not config.connection_token:
        logger.warning("未配置 CONNECTION_TOKEN，跳过本次同步")
        return
    
    # 检查是否有已登录的 profile
    profiles = await profile_db.get_logged_in_profiles()
    if not profiles:
        logger.warning("没有已登录的 Profile，跳过本次同步")
        return
    
    # 执行批量同步
    await token_syncer.sync_all_profiles()


async def startup():
    """启动时初始化"""
    logger.info("=" * 60)
    logger.info("Flow2API Token Updater v2.0 - 多 Profile 版")
    logger.info("=" * 60)
    
    # 初始化数据库
    await profile_db.init()
    logger.info("数据库初始化完成")
    
    # 启动浏览器管理器
    await browser_manager.start()
    
    # 配置定时任务
    scheduler.add_job(
        scheduled_sync,
        trigger=IntervalTrigger(minutes=config.refresh_interval),
        id="token_sync",
        replace_existing=True
    )
    scheduler.start()
    
    logger.info(f"定时任务已启动: 每 {config.refresh_interval} 分钟执行一次")
    logger.info(f"Flow2API URL: {config.flow2api_url}")
    logger.info(f"API 端口: {config.api_port}")
    logger.info("")
    logger.info("管理界面: http://localhost:8080")
    logger.info("VNC 界面: http://localhost:6080/vnc.html")
    logger.info("")


async def shutdown():
    """关闭时清理"""
    logger.info("正在关闭...")
    scheduler.shutdown()
    await browser_manager.stop()


@app.on_event("startup")
async def on_startup():
    await startup()


@app.on_event("shutdown")
async def on_shutdown():
    await shutdown()


def main():
    """主函数"""
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=config.api_port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
