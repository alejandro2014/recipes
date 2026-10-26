"""PySide6 page to configure the pack size of the ingredients used in the recipes."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from recipe_manager.packs import PackSizes
from recipe_manager.shopping import ingredients, parse_size
from recipe_manager.storage import RecipeRepository

NAME, UNIT, SIZE = range(3)
UNIT_NAMES = {"g": "gramos", "ml": "mililitros", None: "unidades"}
INVALID_COLOR = QColor(255, 200, 200)


class PacksPage(QWidget):
    def __init__(self, repository: RecipeRepository, packs: PackSizes, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.packs = packs

        help_label = QLabel(
            "Indica el tamaño del envase en el que se vende cada ingrediente, p. ej. «1 kg» de harina, "
            "«1 l» de leche o «12» huevos. Si lo dejas vacío, se compra por unidades sueltas o al peso."
        )
        help_label.setWordWrap(True)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Ingrediente", "Se mide en", "Envase"])
        self.table.horizontalHeader().setSectionResizeMode(NAME, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.itemChanged.connect(self._size_changed)

        layout = QVBoxLayout(self)
        layout.addWidget(help_label)
        layout.addWidget(self.table)

        self.refresh()

    def refresh(self) -> None:
        """Reload the ingredients of all the saved recipes."""
        recipes = [self.repository.load(slug) for slug, _ in self.repository.list()]
        rows = ingredients(recipes)
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for row, (name, unit) in enumerate(rows):
            for column, text in ((NAME, name), (UNIT, UNIT_NAMES[unit])):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, item)
            size = QTableWidgetItem(self.packs.get(name))
            size.setData(Qt.ItemDataRole.UserRole, unit)
            self.table.setItem(row, SIZE, size)
            self._validate(size)
        self.table.blockSignals(False)

    def _validate(self, item: QTableWidgetItem) -> None:
        text = item.text().strip()
        valid = not text or parse_size(text, item.data(Qt.ItemDataRole.UserRole)) is not None
        item.setBackground(QBrush() if valid else QBrush(INVALID_COLOR))
        item.setToolTip("" if valid else "Tamaño no válido: escribe un número y, si quieres, g, kg, ml o l.")

    def _size_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != SIZE:
            return
        self.packs.set(self.table.item(item.row(), NAME).text(), item.text())
        self.table.blockSignals(True)
        self._validate(item)
        self.table.blockSignals(False)
