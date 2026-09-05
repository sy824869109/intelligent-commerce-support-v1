.PHONY: help check env-check governance-check structure-check

help:
	@echo "Available targets: check, env-check, governance-check, structure-check"

check: env-check structure-check governance-check

env-check:
	@python --version
	@python -m pip --version

structure-check:
	@python scripts/verify_structure.py

governance-check:
	@python scripts/verify_governance.py
