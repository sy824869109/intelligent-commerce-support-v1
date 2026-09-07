.PHONY: help check ci env-check governance-check structure-check infra-images infra-config infra-up infra-health infra-stop infra-restart-test infra-upgrade

help:
	@echo "Available targets: check, ci, infra-images, infra-config, infra-up, infra-health, infra-stop, infra-restart-test, infra-upgrade"

check: env-check structure-check governance-check

ci:
	@python scripts/ci.py

env-check:
	@python --version
	@python -m pip --version

structure-check:
	@python scripts/verify_structure.py

governance-check:
	@python scripts/verify_governance.py

infra-images:
	@python scripts/infra_images.py verify

infra-config:
	@python scripts/local_infra.py config

infra-up:
	@python scripts/local_infra.py up

infra-health:
	@python scripts/local_infra.py health

infra-stop:
	@python scripts/local_infra.py stop

infra-restart-test:
	@python scripts/local_infra.py restart-test

infra-upgrade:
	@python scripts/local_infra.py upgrade
