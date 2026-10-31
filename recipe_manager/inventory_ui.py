"""PySide6 page to keep track of the food already at home."""

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QCompleter,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from recipe_manager.inventory import Inventory
from recipe_manager.packs_ui import INVALID_COLOR
from recipe_manager.shopping import ingredients, parse_quantity
from recipe_manager.storage import RecipeRepository

NAME, KIND, QUANTITY, DESIRED = range(4)


class InventoryPage(QWidget):
    def __init__(self, repository: RecipeRepository, inventory: Inventory, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.inventory = inventory

        help_label = QLabel(
            "Apunta lo que ya tienes en casa, p. ej. «500 g» de harina o «10» de pollo, tipo pechuga, y se "
            "descontará de la lista de la compra. El tipo es opcional y distingue las formas de un alimento: "
            "pechuga o muslo, pieza o lata. Si dejas la cantidad vacía, se da por hecho que tienes suficiente. "
            "Usa el mismo nombre que en las recetas: «pechuga de pollo» descuenta solo ese tipo y «pollo», "
            "todos. Si el alimento y el tipo ya están, se actualiza su cantidad. Haz doble clic en una cantidad "
            "para cambiarla; con 0, el alimento se queda en la lista como agotado. Si indicas una cantidad "
            "deseada, cuando tengas menos se añadirá a la lista de la compra lo que falte hasta llegar a ella."
        )
        help_label.setWordWrap(True)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Alimento", "Tipo", "Cantidad", "Deseada"])
        self.table.horizontalHeader().setSectionResizeMode(NAME, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.itemChanged.connect(self._item_changed)

        self.suggestions = QStringListModel(self)
        completer = QCompleter(self.suggestions, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)

        self.name = QLineEdit()
        self.name.setPlaceholderText("Alimento")
        self.name.setCompleter(completer)
        self.name.returnPressed.connect(self._add)
        self.kind = QLineEdit()
        self.kind.setPlaceholderText("Tipo")
        self.kind.returnPressed.connect(self._add)
        self.quantity = QLineEdit()
        self.quantity.setPlaceholderText("Cantidad")
        self.quantity.returnPressed.connect(self._add)
        self.desired = QLineEdit()
        self.desired.setPlaceholderText("Cantidad deseada")
        self.desired.returnPressed.connect(self._add)
        add_button = QPushButton("Añadir")
        add_button.clicked.connect(self._add)
        remove_button = QPushButton("Quitar")
        remove_button.clicked.connect(self._remove)
        form = QHBoxLayout()
        form.addWidget(self.name, 1)
        form.addWidget(self.kind)
        form.addWidget(self.quantity)
        form.addWidget(self.desired)
        form.addWidget(add_button)
        form.addWidget(remove_button)

        layout = QVBoxLayout(self)
        layout.addWidget(help_label)
        layout.addWidget(self.table)
        layout.addLayout(form)

        self.refresh()

    def refresh(self) -> None:
        """Reload the inventory and the ingredients of all the saved recipes."""
        recipes = [self.repository.load(slug) for slug, _ in self.repository.list()]
        self.suggestions.setStringList([name for name, _ in ingredients(recipes)])
        rows = self.inventory.all()
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for row, (name, kind, quantity, desired) in enumerate(rows):
            for column, text in ((NAME, name), (KIND, kind)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, item)
            for column, text in ((QUANTITY, quantity), (DESIRED, desired)):
                item = QTableWidgetItem(text)
                self.table.setItem(row, column, item)
                self._validate(item)
        self.table.blockSignals(False)

    def _validate(self, item: QTableWidgetItem) -> None:
        text = item.text().strip()
        valid = not text or parse_quantity(text) is not None
        item.setBackground(QBrush() if valid else QBrush(INVALID_COLOR))
        item.setToolTip("" if valid else "Cantidad no válida: escribe un número y, si quieres, g, kg, ml o l.")

    def _item_changed(self, item: QTableWidgetItem) -> None:
        row = item.row()
        if item.column() not in (QUANTITY, DESIRED):
            return
        quantity, desired = self.table.item(row, QUANTITY).text(), self.table.item(row, DESIRED).text()
        self.inventory.set(self._name(row), self._kind(row), quantity, desired)
        self.table.blockSignals(True)
        self._validate(item)
        self.table.blockSignals(False)

    def _add(self) -> None:
        if not self.name.text().strip():
            return
        self.inventory.set(self.name.text(), self.kind.text(), self.quantity.text(), self.desired.text().strip() or None)
        self.name.clear()
        self.kind.clear()
        self.quantity.clear()
        self.desired.clear()
        self.name.setFocus()
        self.refresh()

    def _remove(self) -> None:
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        for row in rows:
            self.inventory.remove(self._name(row), self._kind(row))
        self.refresh()

    def _name(self, row: int) -> str:
        return self.table.item(row, NAME).text()

    def _kind(self, row: int) -> str:
        return self.table.item(row, KIND).text()
