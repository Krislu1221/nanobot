"""审计日志模块 - 记录危险命令执行"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

# 审计日志目录
AUDIT_DIR = Path.home() / ".nanobot" / "audit"
AUDIT_LOG_DIR = AUDIT_DIR / "logs"
AUDIT_CONFIG_DIR = AUDIT_DIR / "config"

# 危险命令模式（跨实例操作）- 已禁用（超级管理员模式）
DANGEROUS_PATTERNS = {}

# 安全命令模式（允许执行）
SAFE_PATTERNS = [
    r"launchctl\s+list",  # 查询服务
    r"launchctl\s+kickstart",  # 重启服务
    r"lsof\s+-ti:\d+",  # 查询端口（不带 kill）
    r"ps\s+aux",  # 查询进程
    r"pgrep\s+",  # 查询进程
    r"echo\s+",  # 输出
    r"cat\s+",  # 读取文件
    r"grep\s+",  # 搜索
    r"find\s+",  # 查找文件
]

# 实例端口映射
INSTANCE_PORTS = {
    "虾总": "18792",
    "虾软": "18703",
    "AutoClaw": "18789",
    "猫王": "18799",
    "QClaw": "28789",
}

# 飞书通知配置
FEISHU_NOTIFICATION_CONFIG = {
    "enabled": True,  # 是否启用飞书通知
    "user_id": "ou_7258a51d242120f48e1dddd389c0ca3e",  # 老板的飞书 ID
    "channel": "feishu",  # 渠道
}


def init_audit_system():
    """初始化审计系统"""
    AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    # 创建危险命令配置文件
    config_file = AUDIT_CONFIG_DIR / "dangerous_commands.json"
    if not config_file.exists():
        config = {
            "dangerous_patterns": DANGEROUS_PATTERNS,
            "safe_patterns": SAFE_PATTERNS,
            "instance_ports": INSTANCE_PORTS,
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
        }
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info(f"审计配置文件已创建：{config_file}")


def log_command(
    command: str,
    result: str,
    status: str,
    instance: str = "猫王",
    channel: str = "feishu",
    user_id: str = "ou_7258a51d242120f48e1dddd389c0ca3e",
    blocked: bool = False,
    block_reason: str = "",
):
    """
    记录命令执行日志
    
    Args:
        command: 执行的命令
        result: 执行结果（截断到 500 字符）
        status: 状态 (success/failed/blocked)
        instance: 实例名称
        channel: 渠道
        user_id: 用户 ID
        blocked: 是否被拦截
        block_reason: 拦截原因
    """
    try:
        log_file = AUDIT_LOG_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "instance": instance,
            "channel": channel,
            "user_id": user_id,
            "command": command,
            "result": result[:500] if result else "",
            "status": status,
            "blocked": blocked,
            "block_reason": block_reason,
        }
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        
        logger.debug(f"审计日志已记录：{command[:50]}... -> {status}")
    except Exception as e:
        logger.error(f"审计日志记录失败：{e}")


def check_command_safety(command: str, current_instance: str = "猫王") -> tuple[bool, str]:
    """
    检查命令是否安全 - 审计系统已禁用（超级管理员模式）
    
    Args:
        command: 要检查的命令
        current_instance: 当前实例名称
    
    Returns:
        (是否安全，原因)
    """
    # 审计系统已禁用 - 所有命令都安全
    return True, "safe (审计系统已禁用 - 超级管理员模式)"


def get_instance_by_port(port: str) -> str:
    """根据端口号获取实例名称"""
    for name, p in INSTANCE_PORTS.items():
        if p == port:
            return name
    return f"未知实例 (端口{port})"


def get_daily_log_path(date: str = None) -> Path:
    """获取指定日期的日志文件路径"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    return AUDIT_LOG_DIR / f"{date}.jsonl"


def read_daily_logs(date: str = None) -> list[dict[str, Any]]:
    """读取指定日期的所有日志"""
    log_file = get_daily_log_path(date)
    if not log_file.exists():
        return []
    
    logs = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                logs.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
    return logs


def get_blocked_commands(date: str = None) -> list[dict[str, Any]]:
    """获取指定日期被拦截的命令"""
    logs = read_daily_logs(date)
    return [log for log in logs if log.get("blocked", False)]


def get_statistics(date: str = None) -> dict[str, Any]:
    """获取指定日期的统计数据"""
    logs = read_daily_logs(date)
    
    total = len(logs)
    blocked = sum(1 for log in logs if log.get("blocked", False))
    success = sum(1 for log in logs if log.get("status") == "success")
    failed = sum(1 for log in logs if log.get("status") == "failed")
    
    # 按命令类型统计
    command_types = {}
    for log in logs:
        cmd = log.get("command", "")[:20]
        command_types[cmd] = command_types.get(cmd, 0) + 1
    
    return {
        "date": date or datetime.now().strftime("%Y-%m-%d"),
        "total_commands": total,
        "blocked_commands": blocked,
        "successful_commands": success,
        "failed_commands": failed,
        "block_rate": f"{blocked/total*100:.1f}%" if total > 0 else "0%",
        "top_commands": dict(sorted(command_types.items(), key=lambda x: x[1], reverse=True)[:10]),
    }


async def send_feishu_alert(
    command: str,
    block_reason: str,
    instance: str = "猫王",
    user_id: str = None,
):
    """
    发送飞书告警通知
    
    Args:
        command: 被拦截的命令
        block_reason: 拦截原因
        instance: 实例名称
        user_id: 接收通知的用户 ID
    """
    if not FEISHU_NOTIFICATION_CONFIG.get("enabled", True):
        logger.debug("飞书通知已禁用，跳过告警")
        return
    
    try:
        # 动态导入飞书渠道（避免循环依赖）
        from nanobot.channels.feishu import FeishuChannel
        
        # 获取单例实例
        # 注意：这里需要通道已经初始化，如果未初始化则跳过通知
        # 实际使用时，可以通过事件总线发送通知
        logger.warning(f"⚠️ 飞书告警：{instance} 拦截危险命令")
        logger.warning(f"   命令：{command}")
        logger.warning(f"   原因：{block_reason}")
        
        # TODO: 实际发送飞书消息需要通过消息总线或通道管理器
        # 这里记录日志，实际发送由通道层处理
        # 未来可以通过事件总线实现：
        # await message_bus.publish("audit.alert", {
        #     "type": "command_blocked",
        #     "instance": instance,
        #     "command": command,
        #     "reason": block_reason,
        #     "timestamp": datetime.now().isoformat(),
        # })
        
    except Exception as e:
        logger.error(f"发送飞书告警失败：{e}")
