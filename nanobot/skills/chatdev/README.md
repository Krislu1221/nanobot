# ChatDev 集成 - 使用指南

## ✅ 集成状态

ChatDev 已成功集成到 nanobot！

## 🎯 使用方法

### 方式一：直接在飞书中使用（推荐）

在飞书中对 nanobot 说：

```
帮我分析这个销售数据
```

```
创建一个贪吃蛇游戏
```

```
研究一下最新的 AI 技术
```

```
生成一个小红书文案
```

nanobot 会自动：
1. 识别任务类型
2. 选择合适的 ChatDev 工作流
3. 执行多智能体任务
4. 返回结果和生成的文件

### 方式二：使用 Python SDK

```python
from nanobot.skills.chatdev.chatdev_tools import execute_task_sync

# 执行任务
result = execute_task_sync("创建一个贪吃蛇游戏")
print(result)
```

### 方式三：指定工作流

```python
from nanobot.skills.chatdev.chatdev_tools import execute_task_sync

# 指定使用游戏开发工作流
result = execute_task_sync(
    task="做一个可以双人玩的游戏",
    workflow="游戏"
)
print(result)
```

## 📋 可用工作流

| 类型 | 关键词 | 工作流文件 |
|------|--------|-----------|
| 📈 数据可视化 | 数据、分析、图表、csv | data_visualization_basic.yaml |
| 🎮 游戏开发 | 游戏、贪吃蛇、坦克 | GameDev_with_manager.yaml |
| 📚 深度研究 | 研究、调研、报告 | deep_research_v1.yaml |
| 🛠️ 3D 建模 | 3D、建模、blender | blender_3d_builder_simple.yaml |
| 🎓 教学视频 | 视频、教学、动画 | teach_video.yaml |
| 📝 小红书文案 | 小红书、文案 | xiaohongshu_content_generation.yaml |

## 📁 输出位置

ChatDev 的产物保存在：
```
/tmp/chatdev_git/WareHouse/{会话名称}/
├── code/          # 生成的代码
├── assets/        # 图片/资源
├── logs/          # 执行日志
└── result.md      # 最终结果
```

## 🌐 Web 控制台

可以通过 Web 控制台查看完整结果：
```
http://localhost:5173
```

## ⚠️ 注意事项

1. **ChatDev 后端**：某些功能需要 ChatDev 后端运行
   ```bash
   cd /tmp/chatdev_git
   make dev
   ```

2. **额外依赖**：
   - 3D 建模需要安装 [Blender](https://www.blender.org/)
   - 教学视频需要安装 manim: `uv add manim`

3. **执行时间**：复杂任务可能需要较长时间（几分钟到几十分钟）

4. **Token 消耗**：多智能体协作会消耗较多 Token

## 🔧 故障排除

### 工作流文件不存在
```
错误：工作流文件不存在：xxx.yaml
```
解决：检查 `/tmp/chatdev_git/yaml_instance/` 目录

### 无法导入 ChatDev SDK
```
错误：无法导入 ChatDev SDK
```
解决：
```bash
cd /tmp/chatdev_git
uv sync
```

### API Key 错误
```
错误：API key 无效
```
解决：检查 `.env` 文件中的 `API_KEY` 配置

## 📝 示例

### 示例 1：数据分析
```
用户上传 sales.csv
用户：帮我分析这个销售数据
nanobot：→ 调用 data_visualization_basic.yaml
→ 返回分析结果和图表
```

### 示例 2：游戏开发
```
用户：创建一个贪吃蛇游戏
nanobot：→ 调用 GameDev_with_manager.yaml
→ 返回完整的游戏代码和说明
```

### 示例 3：深度研究
```
用户：研究一下量子计算的最新进展
nanobot：→ 调用 deep_research_v1.yaml
→ 返回研究报告和参考文献
```

## 🎉 完成！

ChatDev 已完全集成到 nanobot，可以直接在飞书中使用！🐱🚀
