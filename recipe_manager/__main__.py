"""Run with: python -m recipe_manager [data_dir]"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from recipe_manager.storage import DEFAULT_DATA_DIR, RecipeRepository
from recipe_manager.ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATA_DIR
    window = MainWindow(RecipeRepository(data_dir))
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
