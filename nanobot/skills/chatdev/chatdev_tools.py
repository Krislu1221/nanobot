"""ChatDev 多智能体工作流集成工具"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

# 添加 ChatDev 到 Python 路径
CHATDEV_PATH = Path("/tmp/chatdev_git")
if str(CHATDEV_PATH) not in sys.path:
    sys.path.insert(0, str(CHATDEV_PATH))

# 设置环境变量
os.environ.setdefault("API_KEY", "sk-sp-f5a1549b0ad343aa95bc149c118c0119")
os.environ.setdefault("BASE_URL", "https://coding.dashscope.aliyuncs.com/v1")

# 导入飞书卡片通知器
FEISHU_CARD_PATH = Path("/Users/krislu/.enhance-claw/instances/shared")
if str(FEISHU_CARD_PATH) not in sys.path:
    sys.path.insert(0, str(FEISHU_CARD_PATH))

try:
    from feishu_progress_card import FeishuProgressCard, should_send_card
    FEISHU_CARD_ENABLED = True
except ImportError as e:
    print(f"⚠️  飞书卡片模块导入失败：{e}，将禁用卡片通知功能")
    FEISHU_CARD_ENABLED = False


# 工作流映射 - 关键词到工作流文件
WORKFLOW_MAP = {
    # 数据可视化
    "数据可视化": "data_visualization_basic.yaml",
    "数据分析": "data_visualization_basic.yaml",
    "图表": "data_visualization_basic.yaml",
    "csv": "data_visualization_basic.yaml",
    "excel": "data_visualization_enhanced_v3.yaml",
    
    # 游戏开发
    "游戏": "GameDev_with_manager.yaml",
    "贪吃蛇": "GameDev_with_manager.yaml",
    "坦克": "GameDev_with_manager.yaml",
    "俄罗斯方块": "GameDev_with_manager.yaml",
    
    # 深度研究
    "研究": "deep_research_v1.yaml",
    "调研": "deep_research_v1.yaml",
    "分析": "deep_research_v1.yaml",
    "报告": "deep_research_v1.yaml",
    
    # 3D 建模
    "3d": "blender_3d_builder_simple.yaml",
    "3D": "blender_3d_builder_simple.yaml",
    "建模": "blender_3d_builder_simple.yaml",
    "blender": "blender_3d_builder_simple.yaml",
    
    # 教学视频
    "视频": "teach_video.yaml",
    "教学": "teach_video.yaml",
    "动画": "teach_video.yaml",
    "manim": "teach_video.yaml",
    
    # 内容创作
    "小红书": "xiaohongshu_content_generation.yaml",
    "文案": "xiaohongshu_content_generation.yaml",
    "内容": "xiaohongshu_content_generation.yaml",
    
    # 通用
    "问题": "general_problem_solving_team.yaml",
    "解决": "general_problem_solving_team.yaml",
}


def get_available_workflows() -> List[Dict[str, str]]:
    """获取可用工作流列表"""
    return [
        {"name": "数据可视化", "file": "data_visualization_basic.yaml", "desc": "分析 CSV/Excel 数据并生成图表"},
        {"name": "游戏开发", "file": "GameDev_with_manager.yaml", "desc": "开发完整游戏（贪吃蛇、坦克大战等）"},
        {"name": "深度研究", "file": "deep_research_v1.yaml", "desc": "多智能体协作研究复杂主题"},
        {"name": "3D 建模", "file": "blender_3d_builder_simple.yaml", "desc": "创建 3D 场景和模型（需要 Blender）"},
        {"name": "教学视频", "file": "teach_video.yaml", "desc": "生成教学动画视频（需要 manim）"},
        {"name": "小红书文案", "file": "xiaohongshu_content_generation.yaml", "desc": "自动生成小红书风格文案"},
        {"name": "问题解决", "file": "general_problem_solving_team.yaml", "desc": "通用问题解决团队"},
    ]


def detect_workflow(task: str) -> Optional[str]:
    """根据任务描述自动检测合适的工作流"""
    task_lower = task.lower()
    
    # 优先级匹配 - 更具体的关键词优先
    priority_keywords = ["小红书", "贪吃蛇", "坦克", "俄罗斯方块", "blender", "manim"]
    for keyword in priority_keywords:
        if keyword.lower() in task_lower and keyword in WORKFLOW_MAP:
            return WORKFLOW_MAP[keyword]
    
    # 普通匹配
    for keyword, workflow_file in WORKFLOW_MAP.items():
        if keyword.lower() in task_lower:
            return workflow_file
    
    # 默认返回数据可视化
    return "data_visualization_basic.yaml"


async def run_chatdev_workflow(
    workflow_file: str,
    task_prompt: str,
    attachments: Optional[List[str]] = None,
    session_name: Optional[str] = None,
    enable_feishu_card: bool = True,
) -> Dict[str, Any]:
    """
    运行 ChatDev 工作流
    
    Args:
        workflow_file: YAML 工作流文件名
        task_prompt: 任务描述
        attachments: 附件文件路径列表
        session_name: 会话名称
        enable_feishu_card: 是否启用飞书进度卡片
    
    Returns:
        包含执行结果的字典
    """
    # 初始化飞书卡片管理器
    card_manager = None
    if FEISHU_CARD_ENABLED and enable_feishu_card:
        # 判断是否应该发送卡片（长任务才发）
        if should_send_card("chatdev_workflow", estimated_duration=60):
            card_manager = FeishuProgressCard()
            print(f"📤 已启用飞书进度卡片通知")
    
    try:
        # 延迟导入以避免启动时阻塞
        from runtime.sdk import run_workflow
        from entity.enums import LogLevel
        
        # 解析 YAML 路径 - 优先 yaml_instance
        yaml_path = CHATDEV_PATH / "yaml_instance" / workflow_file
        if not yaml_path.exists():
            # 尝试 yaml_template 目录
            yaml_path = CHATDEV_PATH / "yaml_template" / workflow_file
        
        if not yaml_path.exists():
            return {
                "success": False,
                "error": f"工作流文件不存在：{workflow_file}",
                "searched_paths": [
                    str(CHATDEV_PATH / "yaml_instance" / workflow_file),
                    str(CHATDEV_PATH / "yaml_template" / workflow_file),
                ]
            }
        
        # 发送初始卡片
        if card_manager:
            # 从工作流文件名提取任务名称
            task_name = workflow_file.replace(".yaml", "").replace("_", " ").title()
            agents = ["产品经理", "架构师", "程序员", "测试员"]  # 默认 Agent 列表
            card_manager.start_task(task_name, agents)
        
        # 执行工作流
        result = run_workflow(
            yaml_file=str(yaml_path),
            task_prompt=task_prompt,
            attachments=attachments or [],
            session_name=session_name,
            variables={
                "API_KEY": os.environ.get("API_KEY"),
                "BASE_URL": os.environ.get("BASE_URL"),
            },
            log_level=LogLevel.INFO,
        )
        
        # 构建结果
        output = {
            "success": True,
            "session_name": result.meta_info.session_name,
            "log_id": result.meta_info.log_id,
            "output_dir": str(result.meta_info.output_dir),
            "token_usage": result.meta_info.token_usage,
            "workflow_file": workflow_file,
        }
        
        if result.final_message:
            output["final_message"] = result.final_message.text_content()
        
        # 收集输出文件
        if result.meta_info.output_dir.exists():
            output_files = []
            for ext in ["*.py", "*.md", "*.png", "*.jpg", "*.csv", "*.html", "*.mp4"]:
                output_files.extend(
                    str(f) for f in result.meta_info.output_dir.glob(f"**/{ext}")
                )
            output["output_files"] = sorted(output_files)[:20]  # 限制文件数量
        
        # 发送完成卡片
        if card_manager:
            card_manager.complete_task(
                output_dir=str(result.meta_info.output_dir),
                token_usage=result.meta_info.token_usage or {}
            )
            print(f"✅ 飞书进度卡片已发送")
        
        return output
        
    except ImportError as e:
        return {
            "success": False,
            "error": f"无法导入 ChatDev SDK: {str(e)}",
            "error_type": "ImportError",
            "hint": "请确保 ChatDev 已正确安装：cd /tmp/chatdev_git && uv sync",
        }
    except Exception as e:
        # 发送错误卡片
        if card_manager:
            print(f"❌ 任务执行失败，将发送错误通知")
        
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }


async def execute_task(
    task: str,
    attachments: Optional[List[str]] = None,
    workflow: Optional[str] = None,
) -> str:
    """
    执行 ChatDev 任务的主入口
    
    Args:
        task: 任务描述
        attachments: 附件文件路径
        workflow: 可选的工作流名称
    
    Returns:
        格式化结果字符串
    """
    # 自动检测工作流
    if workflow:
        workflow_file = WORKFLOW_MAP.get(workflow, detect_workflow(workflow))
    else:
        workflow_file = detect_workflow(task)
    
    # 执行工作流
    result = await run_chatdev_workflow(
        workflow_file=workflow_file,
        task_prompt=task,
        attachments=attachments,
    )
    
    # 格式化输出
    if result.get("success"):
        response = f"✅ ChatDev 任务执行完成！\n\n"
        response += f"📋 会话名称：`{result['session_name']}`\n"
        response += f"🔧 工作流：`{result['workflow_file']}`\n"
        response += f"📁 输出目录：`{result['output_dir']}`\n"
        
        if result.get("final_message"):
            msg = result['final_message']
            if len(msg) > 800:
                response += f"\n📝 结果摘要：\n{msg[:800]}...\n"
            else:
                response += f"\n📝 结果摘要：\n{msg}\n"
        
        if result.get("output_files"):
            response += f"\n📎 生成的文件 ({len(result['output_files'])} 个):\n"
            for f in result['output_files'][:5]:
                response += f"  - `{f}`\n"
            if len(result['output_files']) > 5:
                response += f"  ... 还有 {len(result['output_files']) - 5} 个文件\n"
        
        if result.get("token_usage"):
            response += f"\n💰 Token 使用：{result['token_usage']}\n"
        
        response += f"\n💡 提示：可以在 Web 控制台 http://localhost:5173 查看完整结果"
    else:
        response = f"❌ ChatDev 任务执行失败\n\n"
        response += f"错误类型：{result.get('error_type', 'Unknown')}\n"
        response += f"错误信息：{result.get('error', '未知错误')}\n"
        
        if result.get("hint"):
            response += f"\n💡 提示：{result['hint']}\n"
        
        if result.get("searched_paths"):
            response += f"\n搜索路径:\n"
            for p in result['searched_paths']:
                response += f"  - {p}\n"
    
    return response


# 同步包装器（用于非异步上下文）
def execute_task_sync(
    task: str,
    attachments: Optional[List[str]] = None,
    workflow: Optional[str] = None,
) -> str:
    """同步版本的 execute_task"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(
        execute_task(task=task, attachments=attachments, workflow=workflow)
    )


if __name__ == "__main__":
    # 测试
    print("🧪 测试 ChatDev 工作流检测...")
    test_tasks = [
        "帮我分析这个销售数据",
        "创建一个贪吃蛇游戏",
        "研究一下最新的 AI 技术",
        "做一个 3D 圣诞树",
        "写一个教学视频",
        "生成小红书文案",
    ]
    
    for task in test_tasks:
        workflow = detect_workflow(task)
        print(f"  '{task}' → {workflow}")
    
    print("\n✅ 测试完成！")
