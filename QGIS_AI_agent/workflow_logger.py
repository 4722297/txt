# -*- coding: utf-8 -*-
import os
import json
from datetime import datetime


class WorkflowLogger:
    """
    Logs successful user actions and detects repeated workflow patterns.
    """

    WINDOW_SIZE = 20   # recent actions to scan
    MIN_SEQ_LEN = 2    # minimum steps in a detectable sequence
    MAX_SEQ_LEN = 6    # maximum steps to check

    def __init__(self, plugin_dir: str):
        self.log_path = os.path.join(plugin_dir, "workflow_log.json")
        self._log = self._load()

    # ------------------------------------------------------------------ #
    #  Persistence                                                         #
    # ------------------------------------------------------------------ #

    def _load(self):
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save(self):
        try:
            with open(self.log_path, "w", encoding="utf-8") as f:
                json.dump(self._log, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  Logging                                                             #
    # ------------------------------------------------------------------ #

    def log_action(self, user_input: str, agent: str,
                   tool_id: str = None, operation: str = None,
                   params: dict = None):
        """Record a successful action."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input,
            "agent": agent,
        }
        if tool_id:
            entry["tool_id"] = tool_id
        if operation:
            entry["operation"] = operation
        if params:
            # Only keep JSON-serialisable values (skip QgsMapLayer objects)
            entry["params"] = {
                k: v for k, v in params.items()
                if isinstance(v, (str, int, float, bool, list, dict, type(None)))
            }
        self._log.append(entry)
        self._save()

    def mark_pattern_proposed(self):
        """Insert a sentinel so the same pattern isn't proposed again immediately."""
        self._log.append({
            "timestamp": datetime.now().isoformat(),
            "user_input": "__PATTERN_PROPOSED__",
            "agent": "__system__",
        })
        self._save()

    # ------------------------------------------------------------------ #
    #  Pattern detection                                                   #
    # ------------------------------------------------------------------ #

    def _action_key(self, entry: dict) -> str:
        """Stable identity key for an action (ignores timestamps/params)."""
        if entry.get("tool_id"):
            return f"tool:{entry['tool_id']}"
        if entry.get("operation"):
            return f"op:{entry['operation']}"
        return "__other__"

    def check_pattern(self) -> list:
        """
        Scan recent real actions for a repeated sequence.

        Returns the repeated entries (list) if found, else [].
        """
        # Filter out system sentinels and chat-only entries
        real = [
            e for e in self._log[-self.WINDOW_SIZE:]
            if e.get("agent") not in ("__system__", "chat", "skill_runner")
        ]

        if len(real) < self.MIN_SEQ_LEN * 2:
            return []

        keys = [self._action_key(e) for e in real]

        # Try longest sequence first; check if last N keys == previous N keys
        max_len = min(self.MAX_SEQ_LEN, len(keys) // 2)
        for seq_len in range(max_len, self.MIN_SEQ_LEN - 1, -1):
            last = keys[-seq_len:]
            prev = keys[-seq_len * 2: -seq_len]
            if last == prev and "__other__" not in last:
                return real[-seq_len:]

        return []

    def get_recent(self, n: int = 10) -> list:
        return self._log[-n:]
