# -*- coding: utf-8 -*-
"""
Dialog for downloading Ollama models with a dropdown selection and progress bar.
"""
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QProgressBar,
    QGroupBox, QMessageBox,
)
from .llm_client import pull_ollama_model


# Available models for download, grouped by category
AVAILABLE_MODELS = [
    # --- 輕量模型 (< 3GB) ---
    ("qwen2.5:1.5b", "Qwen 2.5 1.5B — 輕量、快速 (~1 GB)"),
    ("phi4-mini", "Phi-4 Mini — 微軟輕量模型 (~2.5 GB)"),
    ("llama3.2:1b", "Llama 3.2 1B — Meta 輕量模型 (~1.3 GB)"),
    ("gemma3:1b", "Gemma 3 1B — Google 輕量模型 (~1 GB)"),
    ("deepseek-r1:1.5b", "DeepSeek-R1 1.5B — 推理模型 (~1.1 GB)"),
    # --- 中型模型 (3-5GB) ---
    ("llama3.2", "Llama 3.2 3B — Meta 經典模型 (~2 GB)"),
    ("mistral", "Mistral 7B — 高效能開源模型 (~4.1 GB)"),
    ("qwen2.5:7b", "Qwen 2.5 7B — 多語言模型 (~4.7 GB)"),
    ("gemma3", "Gemma 3 4B — Google 中型模型 (~3.3 GB)"),
    ("deepseek-r1:7b", "DeepSeek-R1 7B — 推理模型 (~4.7 GB)"),
    # --- 大型模型 (> 5GB) ---
    ("llama3.3", "Llama 3.3 70B — Meta 旗艦模型 (~43 GB)"),
    ("qwen2.5:14b", "Qwen 2.5 14B — 高品質多語言 (~9 GB)"),
    ("deepseek-r1:14b", "DeepSeek-R1 14B — 進階推理 (~9 GB)"),
]


class _PullThread(QThread):
    """Background thread to pull an Ollama model."""
    progress = pyqtSignal(str, int)   # (status_text, percent)
    finished_ok = pyqtSignal()
    finished_err = pyqtSignal(str)

    def __init__(self, model_name: str, parent=None):
        super().__init__(parent)
        self.model_name = model_name

    def run(self):
        err = pull_ollama_model(
            self.model_name,
            progress_callback=lambda s, p: self.progress.emit(s, p),
        )
        if err:
            self.finished_err.emit(err)
        else:
            self.finished_ok.emit()


class OllamaDownloadDialog(QDialog):
    """Dialog that lets users select and download an Ollama model."""

    model_downloaded = pyqtSignal()  # emitted after a successful download

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("下載 Ollama 模型")
        self.setMinimumWidth(500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._thread = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()

        # --- Model selector ---
        select_group = QGroupBox("選擇模型")
        select_layout = QVBoxLayout()

        self.model_combo = QComboBox()
        for model_id, description in AVAILABLE_MODELS:
            self.model_combo.addItem(description, model_id)
        select_layout.addWidget(self.model_combo)

        self.download_btn = QPushButton("⬇️ 開始下載")
        self.download_btn.clicked.connect(self._start_download)
        select_layout.addWidget(self.download_btn)

        select_group.setLayout(select_layout)
        layout.addWidget(select_group)

        # --- Progress ---
        progress_group = QGroupBox("下載進度")
        progress_layout = QVBoxLayout()

        self.status_label = QLabel("請選擇模型後點擊下載")
        progress_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)

        # --- Close button ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.close_btn = QPushButton("關閉")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _start_download(self):
        model_name = self.model_combo.currentData()
        if not model_name:
            return

        # Disable controls during download
        self.download_btn.setEnabled(False)
        self.model_combo.setEnabled(False)
        self.close_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"正在下載 {model_name} ...")

        self._thread = _PullThread(model_name, self)
        self._thread.progress.connect(self._on_progress)
        self._thread.finished_ok.connect(self._on_success)
        self._thread.finished_err.connect(self._on_error)
        self._thread.start()

    def _on_progress(self, status: str, percent: int):
        self.status_label.setText(status)
        self.progress_bar.setValue(percent)

    def _on_success(self):
        model_name = self.model_combo.currentData()
        self.progress_bar.setValue(100)
        self.status_label.setText("✅ 下載完成！")
        self.download_btn.setEnabled(True)
        self.model_combo.setEnabled(True)
        self.close_btn.setEnabled(True)
        self.model_downloaded.emit()
        QMessageBox.information(self, "成功", f"模型 {model_name} 下載完成！")

    def _on_error(self, error_msg: str):
        self.status_label.setText(f"❌ {error_msg}")
        self.download_btn.setEnabled(True)
        self.model_combo.setEnabled(True)
        self.close_btn.setEnabled(True)
        QMessageBox.critical(self, "下載失敗", error_msg)

    def closeEvent(self, event):
        if self._thread and self._thread.isRunning():
            QMessageBox.warning(self, "警告", "模型正在下載中，請等待完成。")
            event.ignore()
        else:
            super().closeEvent(event)
