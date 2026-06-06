# -*- coding: utf-8 -*-
"""
Multi-provider LLM client supporting OpenAI, Google Gemini, and Anthropic Claude.
"""


# Provider configurations: provider_key -> (display_name, [models])
PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
        "default_model": "gpt-4o-mini",
    },
    "gemini": {
        "name": "Google Gemini",
        "models": ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash"],
        "default_model": "gemini-2.0-flash",
    },
    "claude": {
        "name": "Anthropic Claude",
        "models": ["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-haiku-20240307"],
        "default_model": "claude-sonnet-4-20250514",
    },
    "ollama": {
        "name": "Ollama (本機)",
        "models": [],  # populated dynamically via get_ollama_models()
        "default_model": "",
        "requires_api_key": False,
    },
}


def query_llm(system_prompt: str, user_input: str,
              provider: str = "openai", model: str = None, api_key: str = None) -> str:
    """
    Unified LLM query function that dispatches to the correct provider.

    :param system_prompt: The system prompt to guide the model.
    :param user_input: The user's input.
    :param provider: LLM provider key: 'openai', 'gemini', or 'claude'.
    :param model: The model name. If None, uses the provider's default.
    :param api_key: The API key. Required for all providers.
    :return: The text content of the AI's response or an error JSON string.
    """
    requires_key = PROVIDERS.get(provider, {}).get("requires_api_key", True)
    if requires_key and not api_key:
        return '{"error": "API key is not configured. Please open Settings to set your API key."}'

    provider_config = PROVIDERS.get(provider)
    if not provider_config:
        return f'{{"error": "Unknown provider: {provider}"}}'

    if model is None:
        model = provider_config["default_model"]

    if provider == "openai":
        return _query_openai(system_prompt, user_input, model, api_key)
    elif provider == "gemini":
        return _query_gemini(system_prompt, user_input, model, api_key)
    elif provider == "ollama":
        return _query_ollama(system_prompt, user_input, model)
    elif provider == "claude":
        return _query_claude(system_prompt, user_input, model, api_key)
    else:
        return f'{{"error": "Provider {provider} is not implemented."}}'


def _query_openai(system_prompt: str, user_input: str, model: str, api_key: str) -> str:
    """Query OpenAI GPT API."""
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
        )

        content = response.choices[0].message.content
        return _clean_response(content) if content else '{"error": "No message content in API response."}'

    except Exception as e:
        return f'{{"error": "OpenAI API Error: {str(e)}"}}'


def _query_gemini(system_prompt: str, user_input: str, model: str, api_key: str) -> str:
    """Query Google Gemini API."""
    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        full_prompt = f"{system_prompt}\n\nUser: {user_input}"

        response = client.models.generate_content(
            model=model,
            contents=full_prompt,
        )

        content = response.text
        return _clean_response(content) if content else '{"error": "No message content in API response."}'

    except Exception as e:
        return f'{{"error": "Gemini API Error: {str(e)}"}}'


def _query_claude(system_prompt: str, user_input: str, model: str, api_key: str) -> str:
    """Query Anthropic Claude API."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)

        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_input}
            ],
        )

        content = response.content[0].text if response.content else None
        return _clean_response(content) if content else '{"error": "No message content in API response."}'

    except Exception as e:
        return f'{{"error": "Claude API Error: {str(e)}"}}'


def _query_ollama(system_prompt: str, user_input: str, model: str) -> str:
    """Query local Ollama API."""
    try:
        import requests

        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
                "stream": False,
            },
            timeout=120,
        )
        response.raise_for_status()

        data = response.json()
        content = data.get("message", {}).get("content", "")
        return _clean_response(content) if content else '{"error": "No message content in Ollama response."}'

    except Exception as e:
        return f'{{"error": "Ollama Error: {str(e)}. Is Ollama running? (ollama serve)"}}'


def get_ollama_models() -> list:
    """
    Query Ollama for locally installed models.

    :return: List of model name strings, e.g. ['qwen2.5:7b', 'llama3:latest'].
             Returns an empty list if Ollama is not running.
    """
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def pull_ollama_model(model_name: str, progress_callback=None) -> str:
    """
    Pull (download) an Ollama model with streaming progress.

    :param model_name: Model to pull, e.g. 'llama3.2' or 'qwen2.5:3b'.
    :param progress_callback: Optional callable(status_str, percent_int).
    :return: Empty string on success, error message on failure.
    """
    try:
        import requests
        import json as _json

        resp = requests.post(
            "http://localhost:11434/api/pull",
            json={"model": model_name, "stream": True},
            stream=True,
            timeout=600,
        )
        resp.raise_for_status()

        for line in resp.iter_lines():
            if not line:
                continue
            data = _json.loads(line)
            status = data.get("status", "")
            total = data.get("total", 0)
            completed = data.get("completed", 0)
            percent = int(completed / total * 100) if total > 0 else 0
            if progress_callback:
                progress_callback(status, percent)

        return ""
    except Exception as e:
        return f"下載失敗: {str(e)}"


def _clean_response(text: str) -> str:
    """Clean up potential markdown code blocks around JSON responses."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    return cleaned
