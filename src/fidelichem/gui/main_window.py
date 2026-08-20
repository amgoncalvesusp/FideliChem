from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QWidget


class MainWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("FideliChem")
        self.resize(960, 640)

        empty_state = QLabel("No project is open.", self)
        empty_state.setObjectName("emptyStateLabel")
        empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(empty_state)
