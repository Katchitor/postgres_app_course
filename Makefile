.PHONY: all black pylint mypy

black:
	black .

pylint:
	pylint src

mypy:
	mypy .

all: black pylint mypy