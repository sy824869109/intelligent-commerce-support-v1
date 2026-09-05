.PHONY: help env-check structure-check

help:
	@echo "Available targets: env-check, structure-check"

env-check:
	@python --version
	@python -m pip --version

structure-check:
	@python scripts/verify_structure.py
