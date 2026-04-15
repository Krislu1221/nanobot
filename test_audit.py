#!/usr/bin/env python3
"""测试审计系统"""

import sys
sys.path.insert(0, '/Users/krislu/nanobot')

from nanobot.agent.tools.audit import (
    check_command_safety,
    init_audit_system,
    get_statistics,
    INSTANCE_PORTS,
)

def test_audit():
    """测试审计功能"""
    print("🐱 猫王审计系统测试\n")
    
    # 初始化
    init_audit_system()
    print("✅ 审计系统初始化完成\n")
    
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
    
    for command, expected_safe, description in test_cases:
        is_safe, reason = check_command_safety(command, "猫王")
        status = "✅" if is_safe == expected_safe else "❌"
        result = "允许" if is_safe else "拦截"
        
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
    print(f"   总计：{len(test_cases)} 个\n")
    
    # 显示实例端口映射
    print("🔌 实例端口映射：")
    for instance, port in INSTANCE_PORTS.items():
        print(f"   {instance}: {port}")
    
    print("\n✨ 测试完成！")

if __name__ == "__main__":
    test_audit()
