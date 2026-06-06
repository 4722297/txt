# -*- coding: utf-8 -*-
import json
from .llm_client import query_llm


class Router:
    """
    Decides which agent should handle the user's request.
    Uses the configured LLM for intent classification.
    """

    def __init__(self):
        self.system_prompt = """You are a task dispatcher for a QGIS AI assistant. Your only job is to determine which agent should handle the user's request.
You must respond in JSON format with a single key 'agent'.

The available agents are:
- 'tool_control': Use ONLY for requests that require executing a QGIS Processing tool (e.g., buffer, clip, dissolve, intersection, raster analysis, coordinate transformations, file conversion, etc.).
- 'layer_control': Use for requests that manage layers directly: deleting/removing layers, zooming to a layer, renaming layers, toggling layer visibility, changing layer color/style, loading/adding layers from files, or saving the project.
- 'skill_runner': Use when the user wants to execute, run, or trigger a saved skill/workflow by name.
- 'chat': Use for general conversation, greetings, questions about QGIS concepts, listing/describing layers, listing available skills, or any request that does NOT require executing a tool.

Examples:

User: 幫我做buffer分析
AI: {"agent": "tool_control"}

User: 列出所有圖層
AI: {"agent": "chat"}

User: 什麼是GIS？
AI: {"agent": "chat"}

User: 你好
AI: {"agent": "chat"}

User: 幫我裁切這個柵格圖層
AI: {"agent": "tool_control"}

User: 我有哪些圖層？
AI: {"agent": "chat"}

User: 刪除output圖層
AI: {"agent": "layer_control"}

User: 移除最上面的圖層
AI: {"agent": "layer_control"}

User: 縮放到選取的圖層
AI: {"agent": "layer_control"}

User: 幫我做空間交集分析
AI: {"agent": "tool_control"}

User: 把圖層改名為rivers
AI: {"agent": "layer_control"}

User: 把riverpoly改成紅色
AI: {"agent": "layer_control"}

User: 隱藏output圖層
AI: {"agent": "layer_control"}

User: 載入 /data/roads.shp
AI: {"agent": "layer_control"}

User: 儲存專案
AI: {"agent": "layer_control"}

User: 執行 河流緩衝分析
AI: {"agent": "skill_runner"}

User: 跑 buffer流程
AI: {"agent": "skill_runner"}

User: 使用 道路分析 skill
AI: {"agent": "skill_runner"}

User: 有哪些skill可以用？
AI: {"agent": "chat"}

User: 列出我的工作流程
AI: {"agent": "chat"}
"""

    def route(self, user_input: str, provider: str = "openai",
              model: str = None, api_key: str = None) -> str:
        """
        Determines the correct agent for the user's input.

        :return: Agent name string ('tool_control', 'layer_control',
                 'skill_runner', or 'chat').
        """
        response_str = query_llm(self.system_prompt, user_input,
                                 provider=provider, model=model, api_key=api_key)
        try:
            response_json = json.loads(response_str)
            return response_json.get("agent", "chat")
        except json.JSONDecodeError:
            return "chat"