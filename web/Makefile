# Convenience targets for the web stack. Everything here also works as plain
# npm / python commands — see README.md.

.PHONY: help install dev-mex dev-ppt build test check-glossary sync-fonts check clean

help:
	@echo "install       install site dependencies (npm workspaces)"
	@echo "dev-mex       run mex-traders.com locally, CMS at /keystatic"
	@echo "dev-ppt       run pipsandpalmtrees.com locally, CMS at /keystatic"
	@echo "build         build both static sites"
	@echo "test          draai de units/rolgrens-tests"
	@echo "check-glossary fail on a broken source id or a dead term reference"
	@echo "sync-fonts    copy the brand fonts into every directory that serves them"
	@echo "check         test + check-glossary + build + sync-fonts"

install:
	npm install

dev-mex:
	npm run dev:mex

dev-ppt:
	npm run dev:ppt

build: sync-fonts
	npm run build

test:
	cd .. && python3 -m pytest web/handover/mex_units/tests -q

check-glossary:
	python3 scripts/check_glossary.py

sync-fonts:
	python3 scripts/sync_fonts.py

check: test check-glossary build
	python3 scripts/sync_fonts.py --check

clean:
	rm -rf sites/*/dist sites/*/.astro node_modules
