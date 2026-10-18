# Atajos de desarrollo.  Uso: make test | lint | typecheck | format | check
PY ?= python3
export QT_QPA_PLATFORM ?= offscreen

.PHONY: test lint typecheck format check run i18n

test:        ## corre los tests (sin pantalla)
	$(PY) -m pytest -q

lint:        ## ruff (errores, imports, bugs probables)
	$(PY) -m ruff check .

typecheck:   ## mypy (estricto en model/ y config)
	$(PY) -m mypy ff4_editor

format:      ## formatea con ruff
	$(PY) -m ruff format .

check: lint typecheck test   ## todo lo anterior (lo mismo que corre el CI)

run:         ## abre el editor (make run FILE=/ruta/ff4-es-data.json)
	QT_QPA_PLATFORM= $(PY) main.py $(FILE)

i18n:        ## extrae los textos (tr) y compila las traducciones a ff4_*.qm
	pyside6-lupdate main.py ff4_editor/*.py ff4_editor/*/*.py -ts ff4_editor/translations/ff4_en.ts
	pyside6-lrelease ff4_editor/translations/ff4_en.ts -qm ff4_editor/translations/ff4_en.qm
