#!/usr/bin/env python3
"""测试 ChatDev 集成"""

import sys
import os
from pathlib import Path

# 添加 ChatDev 路径
CHATDEV_PATH = Path("/tmp/chatdev_git")
sys.path.insert(0, str(CHATDEV_PATH))

# 设置环境变量
os.environ["API_KEY"] = "sk-sp-f5a1549b0ad343aa95bc149c118c0119"
os.environ["BASE_URL"] = "https://coding.dashscope.aliyuncs.com/v1"

print("🔍 测试 ChatDev 集成...")
print(f"📁 ChatDev 路径：{CHATDEV_PATH}")
print(f"📁 yaml_instance 存在：{(CHATDEV_PATH / 'yaml_instance').exists()}")
print(f"📁 yaml_template 存在：{(CHATDEV_PATH / 'yaml_template').exists()}")

# 列出可用的工作流
yaml_dirs = ["yaml_instance", "yaml_template"]
for dir_name in yaml_dirs:
    yaml_dir = CHATDEV_PATH / dir_name
    if yaml_dir.exists():
        print(f"\n📂 {dir_name}/ 中的工作流:")
        for yaml_file in sorted(yaml_dir.glob("*.yaml")):
            print(f"  - {yaml_file.name}")

print("\n✅ 环境检查完成！")
