from __future__ import annotations

import sys
import json
from pathlib import Path

SETTINGS_FILE = "settings.json"

import fitz
from PIL import Image
from pypdf import PdfReader, PdfWriter
from PySide6.QtCore import QThread, Signal, Qt

from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QProgressBar,
    QComboBox,
)


class PdfDropLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = Path(url.toLocalFile())

            if file_path.exists() and file_path.suffix.lower() == ".pdf":
                self.setText(str(file_path))
                event.acceptProposedAction()
                return


class PdfDropListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

        self.setDragEnabled(False)
        self.setDropIndicatorShown(True)

        self.setSelectionMode(QListWidget.ExtendedSelection)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()

        existing = {self.item(i).text() for i in range(self.count())}

        for url in urls:
            path = Path(url.toLocalFile())

            if path.exists() and path.is_file() and path.suffix.lower() == ".pdf":
                text = str(path)

                if text not in existing:
                    self.addItem(text)
                    existing.add(text)

        event.accept()


def parse_ranges(range_text: str, page_count: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []

    for part in range_text.split(","):
        part = part.strip()
        if not part:
            continue

        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text) if start_text else 1
            end = int(end_text) if end_text else page_count
        else:
            start = end = int(part)

        if start < 1 or end < start or end > page_count:
            raise ValueError(
                f"Invalid range '{part}'. Use pages between 1 and {page_count}."
            )

        ranges.append((start, end))

    if not ranges:
        raise ValueError("No page ranges were specified.")

    return ranges


def write_pdf(
    reader: PdfReader, output_path: Path, start_page: int, end_page: int
) -> None:
    writer = PdfWriter()

    for page_index in range(start_page - 1, end_page):
        writer.add_page(reader.pages[page_index])

    with output_path.open("wb") as output_file:
        writer.write(output_file)


def split_pdf(
    input_path: Path,
    output_dir: Path,
    chunk_size: int = 1,
    range_text: str | None = None,
    progress_callback=None,
) -> list[Path]:
    if chunk_size < 1:
        raise ValueError("Chunk size must be 1 or greater.")

    reader = PdfReader(input_path)
    page_count = len(reader.pages)
    output_dir.mkdir(parents=True, exist_ok=True)

    if range_text:
        page_ranges = parse_ranges(range_text, page_count)
    else:
        page_ranges = [
            (start, min(start + chunk_size - 1, page_count))
            for start in range(1, page_count + 1, chunk_size)
        ]

    output_paths: list[Path] = []
    stem = input_path.stem

    total_files = len(page_ranges)
    completed_files = 0

    for start, end in page_ranges:
        suffix = f"p{start:03d}" if start == end else f"p{start:03d}-{end:03d}"
        output_path = output_dir / f"{stem}_{suffix}.pdf"
        write_pdf(reader, output_path, start, end)
        output_paths.append(output_path)
        completed_files += 1

        if progress_callback:
            progress = int(completed_files * 100 / total_files)
            progress_callback(progress)

    return output_paths


def convert_pdfs_to_images(
    input_paths: list[Path],
    output_dir: Path,
    image_format: str,
    dpi: int = 200,
    quality: int = 90,
    progress_callback=None,
) -> list[Path]:
    if not input_paths:
        raise ValueError("No PDF files were selected.")
    if dpi < 72:
        raise ValueError("DPI must be 72 or greater.")
    if quality < 1 or quality > 100:
        raise ValueError("Quality must be between 1 and 100.")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths: list[Path] = []
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    format_map = {
        "JPG": ("JPEG", ".jpg"),
        "PNG": ("PNG", ".png"),
        "WebP": ("WEBP", ".webp"),
    }

    pil_format, extension = format_map[image_format]
    total_pages = 0

    for input_path in input_paths:
        with fitz.open(input_path) as document:
            total_pages += document.page_count

    completed_pages = 0

    for input_path in input_paths:
        with fitz.open(input_path) as document:
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                image = Image.frombytes(
                    "RGB",
                    (pixmap.width, pixmap.height),
                    pixmap.samples,
                )
                if document.page_count == 1:
                    filename = f"{input_path.stem}{extension}"
                else:
                    filename = (
                        f"{input_path.stem}_p{page_index + 1:03d}"
                        f"{extension}"
                )

                output_path = output_dir / filename
                
                if pil_format in ("JPEG", "WEBP"):
                    image.save(
                        output_path,
                        pil_format,
                        quality=quality,
                    )
                else:
                    image.save(
                        output_path,
                        pil_format,
                    )
                output_paths.append(output_path)
                completed_pages += 1

                if progress_callback:
                    progress = int(completed_pages * 100 / total_pages)
                    progress_callback(progress)

    return output_paths


def save_settings(data: dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def load_settings() -> dict:
    try:
        if not Path(SETTINGS_FILE).exists():
            return {}

        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return {}


class SplitWorker(QThread):
    progress = Signal(int)
    finished_successfully = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        input_path: Path,
        output_dir: Path,
        chunk_size: int,
        range_text: str | None,
    ) -> None:
        super().__init__()
        self.input_path = input_path
        self.output_dir = output_dir
        self.chunk_size = chunk_size
        self.range_text = range_text

    def run(self) -> None:
        try:
            output_paths = split_pdf(
                input_path=self.input_path,
                output_dir=self.output_dir,
                chunk_size=self.chunk_size,
                range_text=self.range_text,
                progress_callback=self.progress.emit,
            )
        except Exception as error:
            self.failed.emit(str(error))
            return

        self.finished_successfully.emit([str(path) for path in output_paths])


class ConvertWorker(QThread):
    progress = Signal(int)
    finished_successfully = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        input_paths: list[Path],
        output_dir: Path,
        image_format: str,
        dpi: int,
        quality: int,
    ) -> None:
        super().__init__()
        self.input_paths = input_paths
        self.output_dir = output_dir
        self.image_format = image_format
        self.dpi = dpi
        self.quality = quality

    def run(self) -> None:
        try:
            output_paths = convert_pdfs_to_images(
                input_paths=self.input_paths,
                output_dir=self.output_dir,
                image_format=self.image_format,
                dpi=self.dpi,
                quality=self.quality,
                progress_callback=self.progress.emit,
            )
        except Exception as error:
            self.failed.emit(str(error))
            return

        self.finished_successfully.emit([str(path) for path in output_paths])


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.split_worker: SplitWorker | None = None
        self.convert_worker: ConvertWorker | None = None

        self.setWindowTitle("PDFTools")
        self.resize(760, 620)

        self.setup_split_widgets()
        self.split_progress = QProgressBar()
        self.split_progress.setRange(0, 100)
        self.split_progress.setValue(0)
        self.setup_convert_widgets()
        self.convert_progress = QProgressBar()
        self.convert_progress.setRange(0, 100)
        self.convert_progress.setValue(0)
        self.setup_ui()
        self.connect_signals()
        self.update_split_mode()
        self.load_settings_to_ui()
        self.update_format_options()

    def setup_split_widgets(self) -> None:
        self.split_input_edit = PdfDropLineEdit()
        self.split_output_edit = QLineEdit()
        self.chunk_spin = QSpinBox()
        self.range_edit = QLineEdit()
        self.split_status_label = QLabel("PDFを選択してください。")
        self.split_log_edit = QTextEdit()
        self.split_run_button = QPushButton("実行")

        self.every_page_radio = QRadioButton("1ページずつ分割")
        self.chunk_radio = QRadioButton("指定ページ数ごとに分割")
        self.range_radio = QRadioButton("指定範囲を抽出")

    def setup_convert_widgets(self) -> None:
        self.convert_file_list = PdfDropListWidget()
        self.convert_output_edit = QLineEdit()
        self.dpi_spin = QSpinBox()
        self.quality_spin = QSpinBox()
        self.format_combo = QComboBox()
        self.format_combo.addItems(["JPG", "PNG", "WebP"])
        self.convert_status_label = QLabel("PDFを選択してください。")
        self.convert_log_edit = QTextEdit()
        self.convert_run_button = QPushButton("画像に変換")

    def setup_ui(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self.build_split_tab(), "PDF分割")
        tabs.addTab(self.build_convert_tab(), "PDF→画像")
        self.setCentralWidget(tabs)

    def build_split_tab(self) -> QWidget:
        tab = QWidget()
        root_layout = QVBoxLayout(tab)

        file_group = QGroupBox("ファイル")
        file_layout = QFormLayout(file_group)

        input_row = QHBoxLayout()
        input_row.addWidget(self.split_input_edit)
        input_button = QPushButton("選択")
        input_button.clicked.connect(self.select_split_input_file)
        input_row.addWidget(input_button)
        file_layout.addRow("PDF", input_row)

        output_row = QHBoxLayout()
        output_row.addWidget(self.split_output_edit)
        output_button = QPushButton("選択")
        output_button.clicked.connect(self.select_split_output_dir)
        output_row.addWidget(output_button)
        file_layout.addRow("出力先", output_row)
        root_layout.addWidget(file_group)

        mode_group = QGroupBox("分割方法")
        mode_layout = QVBoxLayout(mode_group)
        mode_buttons = QButtonGroup(mode_group)
        for radio in (self.every_page_radio, self.chunk_radio, self.range_radio):
            mode_buttons.addButton(radio)
            mode_layout.addWidget(radio)

        self.every_page_radio.setChecked(True)

        option_layout = QFormLayout()
        self.chunk_spin.setRange(1, 9999)
        self.chunk_spin.setValue(2)
        self.range_edit.setPlaceholderText("例: 1-3,5,8-")
        option_layout.addRow("ページ数", self.chunk_spin)
        option_layout.addRow("範囲", self.range_edit)
        mode_layout.addLayout(option_layout)
        root_layout.addWidget(mode_group)

        action_row = QHBoxLayout()
        action_row.addWidget(self.split_status_label)
        action_row.addStretch()
        self.split_run_button.setMinimumWidth(120)
        action_row.addWidget(self.split_run_button)
        root_layout.addLayout(action_row)
        root_layout.addWidget(self.split_progress)
        self.split_log_edit.setReadOnly(True)
        self.split_log_edit.setPlaceholderText("実行結果がここに表示されます。")
        root_layout.addWidget(self.split_log_edit, stretch=1)
        return tab

    def build_convert_tab(self) -> QWidget:
        tab = QWidget()
        root_layout = QVBoxLayout(tab)

        file_group = QGroupBox("PDFファイル")

        file_layout = QVBoxLayout(file_group)
        info_label = QLabel(
            "PDFを選択するか、この一覧へドラッグ＆ドロップしてください。"
        )
        file_layout.addWidget(info_label)
        button_row = QHBoxLayout()
        add_button = QPushButton("PDFを選択")
        add_button.clicked.connect(self.select_convert_input_files)
        clear_button = QPushButton("クリア")
        clear_button.clicked.connect(self.convert_file_list.clear)
        button_row.addWidget(add_button)
        button_row.addWidget(clear_button)
        button_row.addStretch()
        file_layout.addLayout(button_row)

        self.convert_file_list.setMinimumHeight(150)
        self.convert_file_list.setToolTip("ここへPDFをドラッグ＆ドロップできます")
        file_layout.addWidget(self.convert_file_list)
        root_layout.addWidget(file_group)

        output_group = QGroupBox("変換設定")
        output_layout = QFormLayout(output_group)

        output_row = QHBoxLayout()
        output_row.addWidget(self.convert_output_edit)
        output_button = QPushButton("選択")
        output_button.clicked.connect(self.select_convert_output_dir)
        output_row.addWidget(output_button)
        output_layout.addRow("出力先", output_row)

        self.dpi_spin.setRange(72, 600)
        self.dpi_spin.setValue(200)
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(90)
        output_layout.addRow("DPI", self.dpi_spin)
        output_layout.addRow("Format", self.format_combo)
        output_layout.addRow("品質", self.quality_spin)
        root_layout.addWidget(output_group)

        action_row = QHBoxLayout()
        action_row.addWidget(self.convert_status_label)
        action_row.addStretch()
        self.convert_run_button.setMinimumWidth(140)
        action_row.addWidget(self.convert_run_button)
        root_layout.addLayout(action_row)
        root_layout.addWidget(self.convert_progress)
        self.convert_log_edit.setReadOnly(True)
        self.convert_log_edit.setPlaceholderText(
            "変換した画像ファイルがここに表示されます。"
        )
        root_layout.addWidget(self.convert_log_edit, stretch=1)
        return tab

    def connect_signals(self) -> None:
        self.split_input_edit.textChanged.connect(self.update_default_split_output_dir)
        self.split_run_button.clicked.connect(self.run_split)
        self.every_page_radio.toggled.connect(self.update_split_mode)
        self.chunk_radio.toggled.connect(self.update_split_mode)
        self.range_radio.toggled.connect(self.update_split_mode)
        self.convert_run_button.clicked.connect(self.run_convert)
        self.format_combo.currentTextChanged.connect(self.update_format_options)

    def select_split_input_file(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "PDFを選択",
            "",
            "PDF files (*.pdf)",
        )
        if file_name:
            self.split_input_edit.setText(file_name)

    def select_split_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "出力先を選択")
        if directory:
            self.split_output_edit.setText(directory)

    def select_convert_input_files(self) -> None:
        file_names, _ = QFileDialog.getOpenFileNames(
            self,
            "画像に変換するPDFを選択",
            "",
            "PDF files (*.pdf)",
        )
        existing = {
            self.convert_file_list.item(index).text()
            for index in range(self.convert_file_list.count())
        }
        for file_name in file_names:
            if file_name not in existing:
                self.convert_file_list.addItem(file_name)
                existing.add(file_name)

        if file_names and not self.convert_output_edit.text().strip():
            first_path = Path(file_names[0])
            self.convert_output_edit.setText(str(first_path.with_name("webp_output")))

    def select_convert_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "出力先を選択")
        if directory:
            self.convert_output_edit.setText(directory)

    def update_default_split_output_dir(self) -> None:
        input_path = Path(self.split_input_edit.text())
        if (
            input_path.suffix.lower() == ".pdf"
            and not self.split_output_edit.text().strip()
        ):
            self.split_output_edit.setText(
                str(input_path.with_name(f"{input_path.stem}_split"))
            )

    def update_split_mode(self) -> None:
        self.chunk_spin.setEnabled(self.chunk_radio.isChecked())
        self.range_edit.setEnabled(self.range_radio.isChecked())

    def update_format_options(self) -> None:
        image_format = self.format_combo.currentText()

        self.quality_spin.setEnabled(image_format in ("JPG", "WebP"))

    def load_settings_to_ui(self) -> None:
        settings = load_settings()

        self.split_output_edit.setText(settings.get("split_output", ""))

        self.convert_output_edit.setText(settings.get("convert_output", ""))

        self.dpi_spin.setValue(settings.get("dpi", 200))

        self.quality_spin.setValue(settings.get("quality", 90))

    def run_split(self) -> None:
        input_path = Path(self.split_input_edit.text().strip())
        output_text = self.split_output_edit.text().strip()

        if not input_path.exists() or input_path.suffix.lower() != ".pdf":
            QMessageBox.warning(self, "確認", "PDFファイルを選択してください。")
            return

        if not output_text:
            QMessageBox.warning(self, "確認", "出力先フォルダを選択してください。")
            return

        chunk_size = 1
        range_text = None
        if self.chunk_radio.isChecked():
            chunk_size = self.chunk_spin.value()
        elif self.range_radio.isChecked():
            range_text = self.range_edit.text().strip()
            if not range_text:
                QMessageBox.warning(
                    self, "確認", "分割するページ範囲を入力してください。"
                )
                return

        self.set_split_running(True)
        self.split_log_edit.clear()
        self.split_progress.setValue(0)
        self.split_status_label.setText("分割しています...")

        self.split_worker = SplitWorker(
            input_path=input_path,
            output_dir=Path(output_text),
            chunk_size=chunk_size,
            range_text=range_text,
        )
        self.split_worker.finished_successfully.connect(self.on_split_finished)
        self.split_worker.failed.connect(self.on_split_failed)
        self.split_worker.progress.connect(self.update_split_progress)
        self.split_worker.start()

    def run_convert(self) -> None:
        input_paths = [
            Path(self.convert_file_list.item(index).text())
            for index in range(self.convert_file_list.count())
        ]
        output_text = self.convert_output_edit.text().strip()

        if not input_paths:
            QMessageBox.warning(self, "確認", "変換するPDFファイルを選択してください。")
            return

        invalid_paths = [
            str(path)
            for path in input_paths
            if not path.exists() or path.suffix.lower() != ".pdf"
        ]
        if invalid_paths:
            QMessageBox.warning(self, "確認", "存在しないPDFファイルが含まれています。")
            self.convert_log_edit.setPlainText("\n".join(invalid_paths))
            return

        if not output_text:
            QMessageBox.warning(self, "確認", "出力先フォルダを選択してください。")
            return

        self.set_convert_running(True)
        self.convert_log_edit.clear()
        self.convert_progress.setValue(0)
        self.convert_status_label.setText("画像に変換しています...")

        self.convert_worker = ConvertWorker(
            input_paths=input_paths,
            output_dir=Path(output_text),
            image_format=self.format_combo.currentText(),
            dpi=self.dpi_spin.value(),
            quality=self.quality_spin.value(),
        )
        self.convert_worker.finished_successfully.connect(self.on_convert_finished)
        self.convert_worker.failed.connect(self.on_convert_failed)
        self.convert_worker.progress.connect(self.update_convert_progress)
        self.convert_worker.start()

    def set_split_running(self, running: bool) -> None:
        self.split_run_button.setEnabled(not running)
        self.split_input_edit.setEnabled(not running)
        self.split_output_edit.setEnabled(not running)
        self.every_page_radio.setEnabled(not running)
        self.chunk_radio.setEnabled(not running)
        self.range_radio.setEnabled(not running)
        if running:
            self.chunk_spin.setEnabled(False)
            self.range_edit.setEnabled(False)
        else:
            self.update_split_mode()

    def set_convert_running(self, running: bool) -> None:
        self.convert_run_button.setEnabled(not running)
        self.convert_file_list.setEnabled(not running)
        self.convert_output_edit.setEnabled(not running)
        self.dpi_spin.setEnabled(not running)
        self.quality_spin.setEnabled(not running)

    def update_split_progress(self, value: int) -> None:
        self.split_progress.setValue(value)

    def update_convert_progress(self, value: int) -> None:
        self.convert_progress.setValue(value)

    def on_split_finished(self, output_paths: list[str]) -> None:
        self.set_split_running(False)
        self.split_status_label.setText(
            f"完了: {len(output_paths)}個のPDFを作成しました。"
        )
        self.split_log_edit.setPlainText("\n".join(output_paths))
        self.split_worker = None

    def on_split_failed(self, message: str) -> None:
        self.set_split_running(False)
        self.split_status_label.setText("エラーが発生しました。")
        self.split_log_edit.setPlainText(message)
        QMessageBox.critical(self, "エラー", message)
        self.split_worker = None

    def on_convert_finished(self, output_paths: list[str]) -> None:
        self.set_convert_running(False)
        self.convert_status_label.setText(
            f"完了: {len(output_paths)}個のWebPを作成しました。"
        )
        self.convert_log_edit.setPlainText("\n".join(output_paths))
        self.convert_worker = None

    def on_convert_failed(self, message: str) -> None:
        self.set_convert_running(False)
        self.convert_status_label.setText("エラーが発生しました。")
        self.convert_log_edit.setPlainText(message)
        QMessageBox.critical(self, "エラー", message)
        self.convert_worker = None

    def closeEvent(self, event) -> None:
        save_settings(
            {
                "split_output": self.split_output_edit.text(),
                "convert_output": self.convert_output_edit.text(),
                "dpi": self.dpi_spin.value(),
                "quality": self.quality_spin.value(),
            }
        )

        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
