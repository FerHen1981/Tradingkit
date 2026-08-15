# Convenience targets for the web stack. Everything here also works as plain
# npm / python commands — see README.md.

.PHONY: help install dev-mex dev-ppt build test check-tokens check-glossary check clean

help:
	@echo "install       install site dependencies (npm workspaces)"
	@echo "dev-mex       run mex-traders.com locally, CMS at /keystatic"
	@echo "dev-ppt       run pipsandpalmtrees.com locally, CMS at /keystatic"
	@echo "build         build both static sites"
	@echo "test          run the portal test suite"
	@echo "check-tokens  fail if the portal's palette drifted from the brand tokens"
	@echo "check-glossary fail on a broken source id or a dead term reference"
	@echo "check         test + check-tokens + build"

install:
	npm install

dev-mex:
	npm run dev:mex

dev-ppt:
	npm run dev:ppt

build:
	npm run build

test:
	cd portal && python -m pytest tests -q

check-tokens:
	python3 scripts/check_tokens.py

check-glossary:
	python3 scripts/check_glossary.py

check: test check-tokens check-glossary build

clean:
	rm -rf sites/*/dist sites/*/.astro node_modules
