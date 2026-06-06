# -*- coding: utf-8 -*-
"""
Settings dialog for the AI QGIS Assistant plugin.
Allows users to select their LLM provider, model, and enter their API key.
"""
from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QLineEdit, QPushButton, QGroupBox,
    QMessageBox
)
from .llm_client import PROVIDERS, get_ollama_models
from .ollama_download_dialog import OllamaDownloadDialog


SETTINGS_KEY = "AI_Agent"


class SettingsDialog(QDialog):
    """Settings dialog for configuring the LLM provider, model, and API key."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI QGIS 助手 — 設定")
        self.setMinimumWidth(450)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        """Build the dialog UI."""
        layout = QVBoxLayout()

        # --- LLM Provider Group ---
        llm_group = QGroupBox("語言模型設定 (LLM Settings)")
        form_layout = QFormLayout()

        # Provider selector
        self.provider_combo = QComboBox()
        for key, config in PROVIDERS.items():
            self.provider_combo.addItem(config["name"], key)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form_layout.addRow("模型供應商:", self.provider_combo)

        # Model selector
        self.model_combo = QComboBox()
        model_row = QHBoxLayout()
        model_row.addWidget(self.model_combo)

        # Download button (shown only for Ollama)
        self.download_btn = QPushButton("🔽 下載模型")
        self.download_btn.setFixedWidth(100)
        self.download_btn.clicked.connect(self._open_download_dialog)
        self.download_btn.setVisible(False)
        model_row.addWidget(self.download_btn)

        # Refresh button (shown only for Ollama)
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setFixedWidth(32)
        self.refresh_btn.setToolTip("重新整理本機模型列表")
        self.refresh_btn.clicked.connect(self._refresh_ollama_models)
        self.refresh_btn.setVisible(False)
        model_row.addWidget(self.refresh_btn)

        form_layout.addRow("模型:", model_row)

        # API Key input
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("請輸入 API Key...")

        # Show/hide toggle for API key
        api_key_layout = QHBoxLayout()
        api_key_layout.addWidget(self.api_key_input)
        self.toggle_visibility_btn = QPushButton("👁")
        self.toggle_visibility_btn.setFixedWidth(32)
        self.toggle_visibility_btn.setCheckable(True)
        self.toggle_visibility_btn.toggled.connect(self._toggle_api_key_visibility)
        api_key_layout.addWidget(self.toggle_visibility_btn)

        # Store references for the API Key row label and widget
        self.api_key_label = QLabel("API Key:")
        form_layout.addRow(self.api_key_label, api_key_layout)
        self.api_key_widget = api_key_layout

        llm_group.setLayout(form_layout)
        layout.addWidget(llm_group)

        # --- Buttons ---
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.save_btn = QPushButton("儲存")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._save_and_close)
        button_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        # Initialize model list for the default provider
        self._on_provider_changed()

    def _on_provider_changed(self):
        """Update model list and toggle API key visibility when provider changes."""
        provider_key = self.provider_combo.currentData()
        if not provider_key:
            return

        config = PROVIDERS.get(provider_key, {})
        default_model = config.get("default_model", "")
        is_ollama = (provider_key == "ollama")

        self.model_combo.clear()

        if is_ollama:
            # Fetch models dynamically from Ollama
            models = get_ollama_models()
            if not models:
                self.model_combo.addItem("(Ollama 未啟動或無模型)")
        else:
            models = config.get("models", [])

        for m in models:
            self.model_combo.addItem(m)

        # Select default model
        default_idx = self.model_combo.findText(default_model)
        if default_idx >= 0:
            self.model_combo.setCurrentIndex(default_idx)

        # Show/hide API key field based on provider
        requires_key = config.get("requires_api_key", True)
        self.api_key_label.setVisible(requires_key)
        self.api_key_input.setVisible(requires_key)
        self.toggle_visibility_btn.setVisible(requires_key)

        # Show/hide Ollama-specific buttons
        self.download_btn.setVisible(is_ollama)
        self.refresh_btn.setVisible(is_ollama)

    def _toggle_api_key_visibility(self, checked):
        """Toggle API key field between password and plain text mode."""
        if checked:
            self.api_key_input.setEchoMode(QLineEdit.Normal)
            self.toggle_visibility_btn.setText("🔒")
        else:
            self.api_key_input.setEchoMode(QLineEdit.Password)
            self.toggle_visibility_btn.setText("👁")

    def _open_download_dialog(self):
        """Open the Ollama model download dialog."""
        dlg = OllamaDownloadDialog(self)
        dlg.model_downloaded.connect(self._refresh_ollama_models)
        dlg.exec_()

    def _refresh_ollama_models(self):
        """Refresh the model dropdown with currently installed Ollama models."""
        current = self.model_combo.currentText()
        self.model_combo.clear()
        models = get_ollama_models()
        if models:
            for m in models:
                self.model_combo.addItem(m)
            # Restore previous selection if still available
            idx = self.model_combo.findText(current)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.addItem("(Ollama 未啟動或無模型)")


    def _load_settings(self):
        """Load saved settings from QSettings."""
        settings = QSettings(SETTINGS_KEY, "Settings")

        # Provider
        saved_provider = settings.value("provider", "openai")
        idx = self.provider_combo.findData(saved_provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)

        # Model (load after provider is set so model list is populated)
        saved_model = settings.value("model", "")
        if saved_model:
            model_idx = self.model_combo.findText(saved_model)
            if model_idx >= 0:
                self.model_combo.setCurrentIndex(model_idx)

        # API Key
        saved_key = settings.value("api_key", "")
        self.api_key_input.setText(saved_key)

    def _save_and_close(self):
        """Validate, save settings, and close the dialog."""
        provider_key = self.provider_combo.currentData()
        config = PROVIDERS.get(provider_key, {})
        requires_key = config.get("requires_api_key", True)

        api_key = self.api_key_input.text().strip()
        if requires_key and not api_key:
            QMessageBox.warning(self, "警告", "請輸入 API Key。")
            return

        settings = QSettings(SETTINGS_KEY, "Settings")
        settings.setValue("provider", provider_key)
        settings.setValue("model", self.model_combo.currentText())
        settings.setValue("api_key", api_key)

        self.accept()

    @staticmethod
    def get_settings() -> dict:
        """
        Retrieve the saved LLM settings.

        :return: Dict with keys: provider, model, api_key.
        """
        settings = QSettings(SETTINGS_KEY, "Settings")
        return {
            "provider": settings.value("provider", "openai"),
            "model": settings.value("model", "gpt-4o-mini"),
            "api_key": settings.value("api_key", ""),
        }

    @staticmethod
    def is_configured() -> bool:
        """Check if the plugin has been configured (API key or local provider)."""
        settings = QSettings(SETTINGS_KEY, "Settings")
        provider = settings.value("provider", "openai")
        config = PROVIDERS.get(provider, {})
        if not config.get("requires_api_key", True):
            return True
        return bool(settings.value("api_key", ""))
