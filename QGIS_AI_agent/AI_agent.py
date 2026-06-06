# -*- coding: utf-8 -*-
import os.path
import json
import re

from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt, QUrl
from qgis.PyQt.QtGui import QIcon, QTextCursor
from qgis.PyQt.QtWidgets import (QAction, QDockWidget, QWidget, QVBoxLayout,
                                  QHBoxLayout, QTextBrowser, QLineEdit,
                                  QPushButton, QApplication, QInputDialog)
from qgis.core import QgsApplication, QgsTask, QgsMessageLog, Qgis

from .router import Router
from .rag_retriever import RagRetriever
from .agents.tool_agent import ToolAgent
from .tools import QgisAssistant
from .settings_dialog import SettingsDialog
from .workflow_logger import WorkflowLogger
from .skill_runner import SkillRunner
from .resources import *


# ============================================================ #
#  Background Task                                              #
# ============================================================ #

class OrchestrationTask(QgsTask):
    """Runs the full multi-agent pipeline in a background thread."""

    def __init__(self, description, user_input, router, tool_agent,
                 qgis_assistant, parent_plugin, llm_settings,
                 layer_context="", skill_runner=None):
        super().__init__(description, QgsTask.CanCancel)
        self.user_input = user_input
        self.router = router
        self.tool_agent = tool_agent
        self.qgis_assistant = qgis_assistant
        self.parent_plugin = parent_plugin
        self.llm_settings = llm_settings
        self.layer_context = layer_context
        self.skill_runner = skill_runner

        self.final_response = None
        self.exception = None
        self.action_info = {}   # passed back for logging / pattern detection

    # ------------------------------------------------------------------ #
    #  QgsTask interface                                                   #
    # ------------------------------------------------------------------ #

    def run(self):
        try:
            provider = self.llm_settings["provider"]
            model    = self.llm_settings["model"]
            api_key  = self.llm_settings["api_key"]

            agent_name = self.router.route(
                self.user_input, provider=provider, model=model, api_key=api_key)

            if agent_name == "skill_runner":
                self.final_response, self.action_info = \
                    self._handle_skill(provider, model, api_key)
            else:
                self.final_response, self.action_info = \
                    self._execute_agent(self.user_input, agent_name,
                                        provider, model, api_key)
            return True
        except Exception as e:
            self.exception = e
            self.final_response = f"An unexpected error occurred: {e}"
            return False

    def finished(self, result):
        self.parent_plugin.process_task_result(
            result, self.final_response, self.exception, self.action_info)

    # ------------------------------------------------------------------ #
    #  Agent execution helper                                              #
    # ------------------------------------------------------------------ #

    def _execute_agent(self, user_input: str, agent_name: str,
                       provider: str, model: str, api_key: str):
        """
        Execute one agent step.
        Returns (response_html: str, action_info: dict).
        """
        action_info = {"agent": agent_name, "user_input": user_input}

        # ---------- tool_control ----------
        if agent_name == "tool_control":
            tool_command_str = self.tool_agent.process(
                user_input, provider=provider, model=model,
                api_key=api_key, layer_context=self.layer_context)
            try:
                json_str = self._extract_json(tool_command_str)
                tool_command = json.loads(json_str)

                if tool_command.get("tool_id") is None:
                    response = tool_command.get(
                        "message", "Could not find a matching tool.")
                else:
                    tool_id   = tool_command["tool_id"]
                    tool_name = tool_command.get("tool_name", tool_id)
                    params     = tool_command.get("params", {})
                    needs_input = tool_command.get("needs_user_input", False)
                    message    = tool_command.get("message", "")

                    if needs_input:
                        response = (
                            f"🔧 Found tool: <b>{tool_name}</b> ({tool_id})<br>"
                            f"{message}<br><br>"
                            f"Please provide the required parameters and try again."
                        )
                    else:
                        info_msg = f"🔧 Using tool: <b>{tool_name}</b> ({tool_id})<br>"
                        if message:
                            info_msg += f"{message}<br>"
                        result = self.qgis_assistant.run_processing_tool(tool_id, params)
                        response = info_msg + result
                        action_info["tool_id"]  = tool_id
                        action_info["params"]   = params

            except (json.JSONDecodeError, ValueError):
                response = (
                    f"Error: Tool Agent did not return valid JSON.<br>"
                    f"Response: {tool_command_str}"
                )
            return response, action_info

        # ---------- layer_control ----------
        elif agent_name == "layer_control":
            layer_prompt = f"""You are a QGIS layer manager. Analyze the user's request and respond with a JSON object.

Available operations:
- "remove_layer": Remove a layer. Params: {{"layer_name": "<name>"}}
- "rename_layer": Rename a layer. Params: {{"layer_name": "<current>", "new_name": "<new>"}}
- "toggle_layer_visibility": Show/hide a layer. Params: {{"layer_name": "<name>", "visible": true/false}}
- "set_layer_color": Change a vector layer color. Params: {{"layer_name": "<name>", "color": "<color>"}}
- "add_layer_from_file": Load a layer from file. Params: {{"file_path": "<path>", "layer_name": "<optional>"}}
- "save_project": Save the current project. Params: {{}}
- "zoom_active_layer": Zoom to the active layer. Params: {{}}
- "open_attribute_table": Open the attribute table for a vector layer. Params: {{"layer_name": "<name>"}}

[Layer Context]
{self.layer_context}

Respond ONLY with JSON: {{"operation": "<op>", "params": {{...}}, "message": "<brief description>"}}
"""
            from .llm_client import query_llm
            layer_resp = query_llm(layer_prompt, user_input,
                                   provider=provider, model=model, api_key=api_key)
            try:
                json_str = self._extract_json(layer_resp)
                cmd      = json.loads(json_str)
                op       = cmd.get("operation", "")
                params   = cmd.get("params", {})
                msg      = cmd.get("message", "")

                op_map = {
                    "remove_layer":          lambda: self.qgis_assistant.remove_layer(params.get("layer_name", "")),
                    "rename_layer":          lambda: self.qgis_assistant.rename_layer(params.get("layer_name", ""), params.get("new_name", "")),
                    "toggle_layer_visibility": lambda: self.qgis_assistant.toggle_layer_visibility(params.get("layer_name", ""), params.get("visible")),
                    "set_layer_color":       lambda: self.qgis_assistant.set_layer_color(params.get("layer_name", ""), params.get("color", "")),
                    "add_layer_from_file":   lambda: self.qgis_assistant.add_layer_from_file(params.get("file_path", ""), params.get("layer_name")),
                    "save_project":          lambda: self.qgis_assistant.save_project(),
                    "zoom_active_layer":     lambda: self.qgis_assistant.zoom_active_layer(),
                    "open_attribute_table":  lambda: self.qgis_assistant.open_attribute_table(params.get("layer_name", "")),
                }
                result   = op_map[op]() if op in op_map else f"Unknown layer operation: {op}"
                response = f"{msg}<br>{result}" if msg else result
                action_info["operation"] = op
                action_info["params"]    = params

            except (json.JSONDecodeError, ValueError):
                response = f"Error parsing layer command.<br>Response: {layer_resp}"
            return response, action_info

        # ---------- chat ----------
        elif agent_name == "chat":
            response = self.qgis_assistant.chat(
                user_input, provider=provider, model=model,
                api_key=api_key, layer_context=self.layer_context)
            return response, action_info

        else:
            return f"Error: Unknown agent '{agent_name}'", action_info

    # ------------------------------------------------------------------ #
    #  Skill execution                                                     #
    # ------------------------------------------------------------------ #

    def _handle_skill(self, provider: str, model: str, api_key: str):
        action_info = {"agent": "skill_runner"}

        # Strip trigger words to get the skill name
        skill_query = re.sub(
            r'^(執行|跑|run|execute|使用|啟動|start)\s*', '',
            self.user_input, flags=re.IGNORECASE).strip()

        skill_name, steps = self.skill_runner.find_skill(skill_query)

        if not steps:
            available = self.skill_runner.list_skills()
            if available:
                response = (f"❌ 找不到 Skill「{skill_query}」。<br>"
                            f"可用的 Skill：<br>" +
                            "<br>".join(f"• {s}" for s in available))
            else:
                response = ("❌ 尚未儲存任何 Skill。<br>"
                            "完成幾次工作後，AI 會自動偵測並建議你儲存。")
            return response, action_info

        action_info["skill_name"] = skill_name
        response = (f"▶️ 執行 Skill：<b>{skill_name}</b>"
                    f"（共 {len(steps)} 步驟）<br><br>")

        for i, step in enumerate(steps):
            response += f"<b>步驟 {i + 1}：</b>{step}<br>"
            step_agent = self.router.route(
                step, provider=provider, model=model, api_key=api_key)
            step_result, _ = self._execute_agent(
                step, step_agent, provider, model, api_key)
            response += step_result + "<br><br>"

        return response, action_info

    # ------------------------------------------------------------------ #
    #  Utility                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_json(text: str) -> str:
        text = text.strip()
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            return match.group(0)
        raise ValueError("No JSON object found in response")


# ============================================================ #
#  Plugin main class                                            #
# ============================================================ #

class AI:
    """QGIS Plugin Implementation – Main Orchestrator."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

        self.rag_retriever   = RagRetriever()
        self.router          = Router()
        self.tool_agent      = ToolAgent(self.rag_retriever)
        self.qgis_assistant  = QgisAssistant(self.iface)
        self.workflow_logger = WorkflowLogger(self.plugin_dir)
        self.skill_runner    = SkillRunner(self.plugin_dir)

        self.task_manager   = QgsApplication.instance().taskManager()

        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(self.plugin_dir, 'i18n', f'AI_{locale}.qm')
        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions       = []
        self.menu          = self.tr(u'&AI')
        self.dockwidget    = None
        self._pending_pattern = None   # stores pattern entries while waiting for user

    def tr(self, message):
        return QCoreApplication.translate('AI', message)

    def add_action(self, icon_path, text, callback, parent=None):
        icon   = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        self.iface.addToolBarIcon(action)
        self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)
        return action

    def initGui(self):
        self.add_action(
            ':/plugins/ai_agent/icon.png',
            text=self.tr(u'AI QGIS 助手'),
            callback=self.run,
            parent=self.iface.mainWindow())

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.tr(u'&AI'), action)
            self.iface.removeToolBarIcon(action)
        if self.dockwidget:
            self.iface.removeDockWidget(self.dockwidget)

    # ------------------------------------------------------------------ #
    #  UI                                                                  #
    # ------------------------------------------------------------------ #

    def open_settings(self):
        SettingsDialog(self.iface.mainWindow()).exec_()

    def run(self):
        if not self.dockwidget:
            self.dockwidget = QDockWidget(self.tr('AI QGIS 助手'), self.iface.mainWindow())
            self.dockwidget.setObjectName('AIQGISAssistantDockWidget')
            self.dockwidget.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

            main_widget = QWidget()
            layout      = QVBoxLayout()

            self.chat_display = QTextBrowser()
            self.chat_display.setReadOnly(True)
            self.chat_display.setOpenLinks(False)              # handle links manually
            self.chat_display.anchorClicked.connect(self._on_link_clicked)
            layout.addWidget(self.chat_display)

            self.user_input = QLineEdit()
            self.user_input.setPlaceholderText("請在這裡輸入指令...")
            layout.addWidget(self.user_input)

            button_layout = QHBoxLayout()
            self.send_button     = QPushButton("發送")
            self.settings_button = QPushButton("⚙️ 設定")
            self.settings_button.setFixedWidth(80)
            button_layout.addWidget(self.send_button)
            button_layout.addWidget(self.settings_button)
            layout.addLayout(button_layout)

            main_widget.setLayout(layout)
            self.dockwidget.setWidget(main_widget)

            self.send_button.clicked.connect(self.send_message)
            self.user_input.returnPressed.connect(self.send_message)
            self.settings_button.clicked.connect(self.open_settings)

            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)

        self.dockwidget.show()

        if not SettingsDialog.is_configured():
            self.chat_display.append(
                "<i>歡迎使用 AI QGIS 助手！請先設定您的語言模型。</i>")
            self.open_settings()

    # ------------------------------------------------------------------ #
    #  Skill proposal link handler                                         #
    # ------------------------------------------------------------------ #

    def _on_link_clicked(self, url: QUrl):
        scheme = url.scheme()
        host   = url.host()

        if scheme == "skill":
            if host == "save" and self._pending_pattern:
                self._save_skill_dialog()
            elif host == "dismiss" and self._pending_pattern:
                self.workflow_logger.mark_pattern_proposed()
                self._pending_pattern = None
                self.chat_display.append("<i>已略過此次工作流程建議。</i>")

    def _save_skill_dialog(self):
        name, ok = QInputDialog.getText(
            self.iface.mainWindow(),
            "儲存 Skill",
            "請為這個工作流程命名：")
        if ok and name.strip() and self._pending_pattern:
            steps    = [e["user_input"] for e in self._pending_pattern]
            filepath = self.skill_runner.save_skill(name.strip(), steps)
            self.workflow_logger.mark_pattern_proposed()
            self._pending_pattern = None
            self.chat_display.append(
                f"✅ Skill「<b>{name}</b>」已儲存！<br>"
                f"<small>{filepath}</small><br>"
                f"下次可以直接說：「執行 {name}」")

    def _show_skill_proposal(self, pattern: list):
        """Append a clickable skill proposal card to the chat."""
        self._pending_pattern = pattern
        steps_html = "".join(
            f"<li>{e['user_input']}</li>" for e in pattern)
        self.chat_display.append(
            "<hr>"
            "<span style='color:#4CAF50;'>🔍 <b>偵測到工作流程！</b></span><br>"
            "以下操作序列重複出現，是否儲存為 Skill？"
            f"<ol>{steps_html}</ol>"
            "<a href='skill://save'><b>[💾 儲存為 Skill]</b></a>&nbsp;&nbsp;"
            "<a href='skill://dismiss'>[略過]</a>"
            "<hr>")

    # ------------------------------------------------------------------ #
    #  Send message                                                        #
    # ------------------------------------------------------------------ #

    def send_message(self):
        user_text = self.user_input.text().strip()
        if not user_text:
            return

        if not SettingsDialog.is_configured():
            self.chat_display.append(
                "<span style='color:orange;'>⚠️ 請先點擊「⚙️ 設定」設定您的 API Key。</span>")
            return

        llm_settings  = SettingsDialog.get_settings()
        layer_context = self.qgis_assistant.get_layer_context()

        self.chat_display.append(f"<b>使用者:</b> {user_text}")
        self.user_input.clear()
        self.chat_display.append("<b>AI:</b> 思考中...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.send_button.setEnabled(False)

        task = OrchestrationTask(
            f"Orchestrating AI for: {user_text}",
            user_text,
            self.router,
            self.tool_agent,
            self.qgis_assistant,
            self,
            llm_settings,
            layer_context,
            skill_runner=self.skill_runner,
        )
        self.task_manager.addTask(task)

    # ------------------------------------------------------------------ #
    #  Task result                                                         #
    # ------------------------------------------------------------------ #

    def process_task_result(self, result, response, exception, action_info=None):
        QApplication.restoreOverrideCursor()
        self.send_button.setEnabled(True)

        if result:
            response_text = response

            # Log meaningful (non-chat, non-skill) actions and check for patterns
            if action_info:
                agent = action_info.get("agent", "")
                if agent in ("tool_control", "layer_control"):
                    self.workflow_logger.log_action(
                        user_input=action_info.get("user_input", ""),
                        agent=agent,
                        tool_id=action_info.get("tool_id"),
                        operation=action_info.get("operation"),
                        params=action_info.get("params"),
                    )
                    pattern = self.workflow_logger.check_pattern()
                    if pattern:
                        self._show_skill_proposal(pattern)
        else:
            if exception:
                response_text = f"<span style='color:red;'>錯誤: {exception}</span>"
                QgsMessageLog.logMessage(
                    f"Orchestration task failed: {exception}", "AI_Agent", Qgis.Critical)
            else:
                response_text = f"<span style='color:red;'>{response or '任務已取消或失敗。'}</span>"
                QgsMessageLog.logMessage(
                    "Orchestration task was cancelled or failed.", "AI_Agent", Qgis.Warning)

        # Replace the "思考中..." placeholder
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.select(QTextCursor.BlockUnderCursor)
        cursor.removeSelectedText()
        cursor.insertBlock()
        if response_text:
            cursor.insertHtml(
                f"<b>AI:</b> {response_text.replace(os.linesep, '<br>')}")

        self.chat_display.ensureCursorVisible()
