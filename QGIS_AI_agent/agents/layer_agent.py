# -*- coding: utf-8 -*-
import json
from ..llm_client import query_ollama

class LayerAgent:
    """
    Agent specializing in QGIS layer control tasks.
    """
    def __init__(self):
        self.system_prompt = """You are a QGIS layer control specialist. Your task is to analyze the user's request and translate it into a specific tool call in JSON format.

You can ONLY use the following tools:
- "list_layers": Lists all available layers in the project. Does not require parameters.
- "zoom_active_layer": Zooms the map view to the currently selected layer. Does not require parameters.

You MUST respond with a JSON object containing "tool" and "params". If no parameters are needed, "params" should be an empty object {}.

User: Show me all the layers I have.
AI: {"tool": "list_layers", "params": {}}

User: zoom to the selected layer
AI: {"tool": "zoom_active_layer", "params": {}}
"""

    def process(self, user_input: str) -> str:
        """
        Processes the user input to generate a tool call command.

        :param user_input: The user's original message.
        :return: A JSON string representing the tool call.
        """
        response_str = query_ollama(self.system_prompt, user_input)
        return response_str # Return the raw JSON string for the orchestrator to parse
