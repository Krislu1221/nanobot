---
name: chatdev
description: ChatDev 多智能体工作流集成 - 运行数据可视化、游戏开发、深度研究等任务
always: false
---

# ChatDev 多智能体集成

## 功能

通过 ChatDev 的 Python SDK 运行多智能体工作流，支持：
- 📈 **数据可视化** - 分析 CSV/Excel 数据并生成图表
- 🎮 **游戏开发** - 自动生成完整游戏代码
- 📚 **深度研究** - 多智能体协作研究复杂主题
- 🛠️ **3D 场景生成** - 创建 Blender 3D 模型
- 🎓 **教学视频** - 生成教学动画视频

## 使用方法

### 基本用法

```
帮我分析这个销售数据
```

### 带文件上传

```
分析这个 CSV 文件 + [上传文件]
```

### 指定工作流

```
用游戏开发工作流创建一个贪吃蛇游戏
```

## 可用工作流

### 📈 数据可视化
- `data_visualization_basic.yaml` - 基础数据分析
- `data_visualization_enhanced_v3.yaml` - 增强版数据可视化
- `police_data_visualization.yaml` - 警务数据可视化

### 🎮 游戏开发
- `GameDev_with_manager.yaml` - 带管理员的游戏开发
- `ChatDev_v1.yaml` - 经典 ChatDev 游戏开发

### 📚 深度研究
- `deep_research_v1.yaml` - 深度研究
- `deep_research_executor_sub.yaml` - 研究执行子流程

### 🛠️ 3D 建模 (需要 Blender)
- `blender_3d_builder_simple.yaml` - 简单 3D 建模
- `blender_3d_builder_hub.yaml` - 3D 建模中心
- `blender_scientific_illustration_image_gen.yaml` - 科学插图

### 🎓 教学视频 (需要 manim)
- `teach_video.yaml` - 教学视频生成

### 📝 内容创作
- `xiaohongshu_content_generation.yaml` - 小红书文案生成
- `general_problem_solving_team.yaml` - 通用问题解决团队

### 🔧 演示/测试
- `demo_*.yaml` - 各种功能演示
- `react.yaml` - ReAct 模式
- `reflexion_product.yaml` - Reflexion 反思模式

## 输出处理

- ✅ 飞书推送任务进度
- ✅ 完成后发送结果摘要
- ✅ 附上文件下载链接
- ✅ 产物保存在 `WareHouse/{任务名}_{时间戳}/`

## 注意事项

- ChatDev 后端需要运行在 `http://localhost:6400`
- 某些工作流需要额外依赖（如 Blender、manim）
- 复杂任务可能需要较长时间执行
