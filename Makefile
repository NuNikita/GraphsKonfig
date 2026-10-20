PYTHON ?= python3

.PHONY: run test build

run:
	$(PYTHON) src/main.py $(ARGS)

test:
	$(PYTHON) -m unittest discover -s tests -v

build:
	$(PYTHON) -m py_compile src/config.py src/main.py
