# -*- coding: utf-8 -*-
import os
import re


class SkillRunner:
    """
    Manages skill markdown files in the plugin's ``skills/`` directory.
    """

    def __init__(self, plugin_dir: str):
        self.skills_dir = os.path.join(plugin_dir, "skills")
        os.makedirs(self.skills_dir, exist_ok=True)

    # ------------------------------------------------------------------ #
    #  Saving                                                              #
    # ------------------------------------------------------------------ #

    def save_skill(self, name: str, steps: list, description: str = "") -> str:
        """
        Save a workflow as a markdown skill file.

        :param name: Human-readable skill name.
        :param steps: List of user_input strings (one per step).
        :param description: Optional summary.
        :return: Absolute path to the saved file.
        """
        safe_name = re.sub(r'[^\w\u4e00-\u9fff\s\-]', '', name).strip()
        safe_name = re.sub(r'\s+', '_', safe_name) or "untitled_skill"

        filepath = os.path.join(self.skills_dir, f"{safe_name}.md")
        steps_text = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))

        content = (
            f"# Skill: {name}\n\n"
            f"## 說明\n"
            f"{description or f'包含 {len(steps)} 個步驟的工作流程。'}\n\n"
            f"## 步驟\n"
            f"{steps_text}\n\n"
            f"## 觸發關鍵字\n"
            f"{name}\n"
        )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath

    # ------------------------------------------------------------------ #
    #  Listing                                                             #
    # ------------------------------------------------------------------ #

    def list_skills(self) -> list:
        """Return all available skill names (human-readable)."""
        return [
            os.path.splitext(f)[0].replace("_", " ")
            for f in os.listdir(self.skills_dir)
            if f.endswith(".md")
        ]

    # ------------------------------------------------------------------ #
    #  Finding & parsing                                                   #
    # ------------------------------------------------------------------ #

    def find_skill(self, query: str):
        """
        Find a skill by fuzzy name match.

        :return: (skill_name, steps_list) or (None, []) if not found.
        """
        query_norm = re.sub(r'[\s_]', '', query.lower())

        for filename in os.listdir(self.skills_dir):
            if not filename.endswith(".md"):
                continue
            skill_name = os.path.splitext(filename)[0]
            skill_norm = re.sub(r'[\s_]', '', skill_name.lower())
            if query_norm in skill_norm or skill_norm in query_norm:
                steps = self._parse_steps(os.path.join(self.skills_dir, filename))
                return skill_name.replace("_", " "), steps

        return None, []

    def _parse_steps(self, filepath: str) -> list:
        steps = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            in_steps = False
            for line in content.splitlines():
                stripped = line.strip()
                if stripped == "## 步驟":
                    in_steps = True
                    continue
                if in_steps:
                    if stripped.startswith("## "):
                        break
                    m = re.match(r'^\d+\.\s+(.+)', stripped)
                    if m:
                        steps.append(m.group(1))
        except Exception:
            pass
        return steps
