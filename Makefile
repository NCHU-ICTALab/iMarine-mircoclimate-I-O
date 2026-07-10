.PHONY: help install test coverage lint format clean

help:
	@echo "Available commands:"
	@echo "  make install   - install project dependencies"
	@echo "  make test      - run tests"
	@echo "  make coverage  - run tests with 80 percent coverage gate"
	@echo "  make lint      - run flake8 if installed"
	@echo "  make format    - run black if installed"
	@echo "  make clean     - remove local test caches"

install:
	python -m pip install --upgrade pip
	python -m pip install -r requirements.txt
	python -m pip install -r kaohsiung_microclimate_lstm/requirements.txt

test:
	python -m pytest -q

coverage:
	python -m pip install pytest-cov
	python -m pytest --cov=. --cov-report=term-missing --cov-fail-under=80

lint:
	python -m flake8 app kaohsiung_microclimate_lstm tests

format:
	python -m black app kaohsiung_microclimate_lstm tests

clean:
	python -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]; [shutil.rmtree(p, ignore_errors=True) for p in [pathlib.Path('.pytest_cache'), pathlib.Path('htmlcov')]]"
