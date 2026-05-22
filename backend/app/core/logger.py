"""
统一日志配置。

使用 loguru，比标准 logging 更好用：
- 自动彩色输出
- 自动 rotation
- 异常自动带 traceback
"""

import sys
from pathlib import Path

from loguru import logger

from app.core.config import settings

LOG_DIR = Path("logs")


def _try_create_log_dir() -> bool:
    """尝试创建日志目录；容器环境无权限时降级到只输出 stdout。"""
    try:
        LOG_DIR.mkdir(exist_ok=True)
        return True
    except (PermissionError, OSError):
        return False


def setup_logger() -> None:
    """初始化日志：移除默认 handler，加自定义控制台 + 文件输出。"""
    logger.remove()

    logger.add(
        sys.stdout,
        level="DEBUG" if settings.app_debug else "INFO",
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # 文件日志可选：只在能创建目录时启用
    # （Docker 容器以非 root 运行时通常没权限写工作目录，此时只用 stdout，
    #  让容器编排系统/k8s 自己采集日志，更符合 12-factor app 规范）
    if _try_create_log_dir():
        logger.add(
            LOG_DIR / "app_{time:YYYY-MM-DD}.log",
            level="INFO",
            rotation="00:00",
            retention="30 days",
            compression="zip",
            encoding="utf-8",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        )


setup_logger()

__all__ = ["logger"]
