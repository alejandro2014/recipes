VENV := .venv
PYTHON := $(VENV)/bin/python
DATA ?= data

.PHONY: help venv install run test html clean

help:
	@echo "make install  Create the virtualenv and install dependencies"
	@echo "make run      Launch the recipe manager (DATA=dir to override data dir)"
	@echo "make test     Run the test suite"
	@echo "make html     Generate HTML pages from the recipes (needs pandoc)"
	@echo "make clean    Remove generated HTML and caches"

$(PYTHON):
	python3 -m venv $(VENV)

venv: $(PYTHON)

install: $(PYTHON)
	$(PYTHON) -m pip install -r requirements.txt

run: $(PYTHON)
	$(PYTHON) -m recipe_manager $(DATA)

test: $(PYTHON)
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m unittest discover -s tests -t . -v

html:
	./generate

clean:
	rm -rf html
	find . -path ./$(VENV) -prune -o -name __pycache__ -type d -exec rm -rf {} +
