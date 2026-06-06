# -*- coding: utf-8 -*-
import json
from ..llm_client import query_llm
from ..rag_retriever import RagRetriever


class ToolAgent:
    """
    Agent that uses RAG retrieval + LLM to select and parameterize
    QGIS Processing tools based on the user's natural language input.
    """

    def __init__(self, rag_retriever: RagRetriever):
        self.rag = rag_retriever
        self.system_prompt = """You are a QGIS Processing tool specialist. You will be given:
1. The user's request
2. A list of candidate QGIS Processing tools retrieved by semantic search
3. The current map layer context (all layers with their IDs)

Your task is to select the BEST matching tool from the candidates and determine what parameters are needed.

You MUST respond with a JSON object in the following format:
{
    "tool_id": "<the tool id, e.g. native:buffer>",
    "tool_name": "<the tool name>",
    "params": {
        "<PARAM_NAME>": "<value or description>"
    },
    "needs_user_input": true/false,
    "message": "<brief explanation of what this tool does and what inputs it needs from the user>"
}

Rules:
- IMPORTANT: Read the [Layer Context] section carefully. Choose the correct layer based on the user's request.
  - If the user mentions a layer by name, find its ID from the context and use that ID.
  - If the user says "topmost layer" or "first layer", use the ID of the [Topmost] layer.
  - If the user says "selected layer" or "active layer", use the ID from [Currently Selected Layer].
  - If only one layer exists, use that layer's ID.
  - Only use "ACTIVE_LAYER" as a fallback if no layer context is available.
- The 'INPUT' parameter value MUST be the layer ID string (e.g., 'my_shapefile_abc123').
- UNIT CONVERSION: QGIS Processing tools use the layer's CRS units (usually METERS).
  - If the user says "1 公里" or "1 km", set DISTANCE to 1000 (meters).
  - If the user says "500 公尺" or "500 m", set DISTANCE to 500.
  - If the user says "2 公里", set DISTANCE to 2000.
  - Always convert to meters unless the context clearly indicates otherwise.
- If specific parameter values are mentioned by the user (e.g., distance=100), include them.
- If the tool requires parameters the user didn't specify, set "needs_user_input" to true and explain what is needed in "message".
- If NONE of the candidate tools match the user's request, respond with:
  {"tool_id": null, "message": "Sorry, I could not find a matching QGIS tool for your request."}
"""

    def process(self, user_input: str, top_k: int = 5,
                provider: str = "openai", model: str = None,
                api_key: str = None, layer_context: str = "") -> str:
        """
        Process the user's input: retrieve candidate tools via RAG,
        then ask LLM to select the best tool and parameters.

        :param user_input: The user's original message.
        :param top_k: Number of candidate tools to retrieve.
        :param provider: LLM provider key.
        :param model: Model name.
        :param api_key: API key.
        :param layer_context: String describing current map layers.
        :return: A JSON string with the tool selection result.
        """
        # 1. Retrieve candidate tools via RAG
        candidates = self.rag.retrieve(user_input, top_k=top_k)

        # 2. Format candidates for the prompt
        candidates_text = "Candidate QGIS Processing tools:\n"
        for i, c in enumerate(candidates, 1):
            candidates_text += (
                f"{i}. ID: {c['id']}\n"
                f"   Name: {c['name']}\n"
                f"   Group: {c['group']}\n"
                f"   Description: {c['description']}\n"
                f"   Relevance Score: {c['score']:.4f}\n\n"
            )

        # 3. Combine user input, candidates, and layer context
        full_input = f"User request: {user_input}\n\n{candidates_text}"
        if layer_context:
            full_input += f"\n[Layer Context]\n{layer_context}\n"

        # 4. Ask LLM to select the tool
        response_str = query_llm(self.system_prompt, full_input,
                                 provider=provider, model=model, api_key=api_key)
        return response_str
