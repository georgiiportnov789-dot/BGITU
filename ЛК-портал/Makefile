VENV ?= .venv
PY ?= $(VENV)/bin/python
PORT ?= 8010

.PHONY: venv install migrate seed run test check clean

venv:
	uv venv --python 3.11 $(VENV) || python3.11 -m venv $(VENV)

install: venv
	. $(VENV)/bin/activate && uv pip install -r requirements.txt

migrate:
	$(PY) manage.py migrate

seed:
	$(PY) manage.py seed_demo

run:
	$(PY) manage.py runserver 127.0.0.1:$(PORT)

test:
	$(PY) manage.py test

check:
	$(PY) manage.py check

clean:
	rm -f db.sqlite3
	rm -rf media staticfiles
