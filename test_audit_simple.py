#!/usr/bin/env python3
"""测试审计系统 - 独立版本（不依赖 nanobot）"""

import json
import re
from datetime import datetime
from pathlib import Path

# 实例端口映射
INSTANCE_PORTS = {
    "虾总": "18792",
    "虾软": "18703",
    "AutoClaw": "18789",
    "猫王": "18799",
    "QClaw": "28789",
}

# 危险命令模式（跨实例操作）
DANGEROUS_PATTERNS = {
    "launchctl_destroy": [
        r"launchctl\s+(bootout|remove|unload)",  # 卸载服务
    ],
    "kill_process": [
        r"kill\s+-9\s+\d+",  # 强制杀进程
        r"pkill\s+openclaw",  # 杀所有 openclaw
        r"killall\s+openclaw",  # 杀所有 openclaw
        r"pkill\s+-9",  # 强制杀所有匹配进程
    ],
    "port_operation": [
        r"lsof\s+-ti:\d+\s*\|\s*xargs\s+kill",  # 通过端口杀进程
    ],
}

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


def check_command_safety(command: str, current_instance: str = "猫王") -> tuple[bool, str]:
    """检查命令是否安全"""
    cmd_lower = command.lower()
    
    # 1. 检查是否命中危险模式
    for category, patterns in DANGEROUS_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, cmd_lower):
                # 特殊处理：如果是针对自身实例，允许执行
                if category == "port_operation":
                    # 提取命令中的端口号
                    port_match = re.search(r"lsof\s+-ti:(\d+)", cmd_lower)
                    if port_match:
                        port = port_match.group(1)
                        # 检查是否是自身实例的端口
                        if INSTANCE_PORTS.get(current_instance) == port:
                            return True, f"safe (针对自身实例端口 {port})"
                        else:
                            # 找到是哪个实例的端口
                            target_instance = next(
                                (name for name, p in INSTANCE_PORTS.items() if p == port),
                                f"未知实例 (端口{port})"
                            )
                            return False, f"危险命令：跨实例操作（目标：{target_instance}）"
                
                # 其他危险命令一律拦截
                return False, f"危险命令：{category}"
    
    # 2. 检查是否在安全模式中
    for pattern in SAFE_PATTERNS:
        if re.search(pattern, cmd_lower):
            return True, "safe (白名单命令)"
    
    # 3. 默认允许（不拦截普通命令）
    return True, "safe (默认允许)"


def test_audit():
    """测试审计功能"""
    print("🐱 猫王审计系统测试\n")
    
    # 测试用例
    test_cases = [
        # (命令，期望结果，说明)
        ("lsof -ti:18799 | xargs kill -9", True, "清理自身端口（猫王 18799）"),
        ("lsof -ti:18792 | xargs kill -9", False, "清理虾总端口（跨实例）"),
        ("lsof -ti:18703 | xargs kill -9", False, "清理虾软端口（跨实例）"),
        ("pkill openclaw-gateway", False, "杀所有 openclaw（危险）"),
        ("killall openclaw-gateway", False, "杀所有 openclaw（危险）"),
        ("launchctl list", True, "查询服务（安全）"),
        ("launchctl kickstart gui/501/ai.openclaw.xiazong", True, "重启服务（安全）"),
        ("launchctl bootout gui/501/ai.openclaw.xiazong", False, "卸载服务（危险）"),
        ("ps aux", True, "查询进程（安全）"),
        ("echo hello", True, "普通命令（安全）"),
    ]
    
    print("📋 命令安全检查测试：\n")
    blocked_count = 0
    allowed_count = 0
    passed = 0
    failed = 0
    
    for command, expected_safe, description in test_cases:
        is_safe, reason = check_command_safety(command, "猫王")
        status = "✅" if is_safe == expected_safe else "❌"
        result = "允许" if is_safe else "拦截"
        
        if is_safe == expected_safe:
            passed += 1
        else:
            failed += 1
        
        if is_safe:
            allowed_count += 1
        else:
            blocked_count += 1
        
        print(f"{status} {description}")
        print(f"   命令：{command}")
        print(f"   结果：{result} - {reason}\n")
    
    print(f"📊 测试统计：")
    print(f"   允许执行：{allowed_count} 个")
    print(f"   被拦截：{blocked_count} 个")
    print(f"   总计：{len(test_cases)} 个")
    print(f"   通过：{passed} 个 ✅")
    print(f"   失败：{failed} 个 ❌\n")
    
    # 显示实例端口映射
    print("🔌 实例端口映射：")
    for instance, port in INSTANCE_PORTS.items():
        print(f"   {instance}: {port}")
    
    print("\n✨ 测试完成！")
    
    return failed == 0


if __name__ == "__main__":
    success = test_audit()
    exit(0 if success else 1)
