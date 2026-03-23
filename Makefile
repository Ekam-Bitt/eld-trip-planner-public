SHELL := /bin/bash

API_DIR := apps/api
WEB_DIR := apps/web

API_VENV := $(API_DIR)/.venv
API_PYTHON := $(API_VENV)/bin/python
API_PIP := $(API_VENV)/bin/pip
WEB_NPM := npm

HOST ?= 0.0.0.0
PORT ?= 8000
WEB_HOST ?= 127.0.0.1
WEB_PORT ?= 5173

.PHONY: help setup api-setup api-install api-check api-shell api web-install web test build clean-artifacts clean

help:
	@echo "Available targets:"
	@echo "  make setup           Install backend and frontend dependencies"
	@echo "  make api-setup       Create API venv and install backend dependencies"
	@echo "  make api-install     Install/refresh backend dependencies in existing venv"
	@echo "  make api-check       Run Django system checks"
	@echo "  make api-shell       Open a Django shell"
	@echo "  make api             Start Django dev server"
	@echo "  make web-install     Install frontend dependencies"
	@echo "  make web             Start frontend dev server"
	@echo "  make test            Run backend unit tests"
	@echo "  make build           Run backend compile checks + frontend production build"
	@echo "  make clean-artifacts Remove generated SVG/PDF artifacts"
	@echo "  make clean           Remove build output folders"

setup: api-setup web-install

api-setup:
	cd $(API_DIR) && python3 -m venv .venv
	$(API_PIP) install -r $(API_DIR)/requirements.txt

api-install:
	@if [ ! -x "$(API_PIP)" ]; then \
		echo "Missing $(API_PIP). Run 'make api-setup' first."; \
		exit 1; \
	fi
	$(API_PIP) install -r $(API_DIR)/requirements.txt

api-check:
	@if [ ! -x "$(API_PYTHON)" ]; then \
		echo "Missing $(API_PYTHON). Run 'make api-setup' first."; \
		exit 1; \
	fi
	cd $(API_DIR) && $(abspath $(API_PYTHON)) manage.py check

api-shell:
	@if [ ! -x "$(API_PYTHON)" ]; then \
		echo "Missing $(API_PYTHON). Run 'make api-setup' first."; \
		exit 1; \
	fi
	cd $(API_DIR) && $(abspath $(API_PYTHON)) manage.py shell

api:
	@if [ ! -x "$(API_PYTHON)" ]; then \
		echo "Missing $(API_PYTHON). Run 'make api-setup' first."; \
		exit 1; \
	fi
	cd $(API_DIR) && $(abspath $(API_PYTHON)) manage.py runserver $(HOST):$(PORT)

web-install:
	cd $(WEB_DIR) && $(WEB_NPM) install

web:
	cd $(WEB_DIR) && $(WEB_NPM) run dev -- --host $(WEB_HOST) --port $(WEB_PORT) --strictPort

test:
	@if [ ! -x "$(API_PYTHON)" ]; then \
		echo "Missing $(API_PYTHON). Run 'make api-setup' first."; \
		exit 1; \
	fi
	cd $(API_DIR) && $(abspath $(API_PYTHON)) -m unittest discover -s tests -v

build:
	python3 -m py_compile \
		$(API_DIR)/api_service.py \
		$(API_DIR)/persistence.py \
		$(API_DIR)/driver_log_renderer.py \
		$(API_DIR)/timeline_renderer.py \
		$(API_DIR)/hos_compliance.py \
		$(API_DIR)/trip_planner.py \
		$(API_DIR)/manage.py \
		$(API_DIR)/django_api/settings.py \
		$(API_DIR)/django_api/urls.py \
		$(API_DIR)/django_api/views.py \
		$(API_DIR)/django_api/wsgi.py
	cd $(WEB_DIR) && $(WEB_NPM) run build

clean-artifacts:
	rm -f artifacts/latest/*.svg artifacts/latest/*.pdf artifacts/reports/*.svg artifacts/reports/*.pdf

clean:
	rm -rf $(WEB_DIR)/dist $(WEB_DIR)/.vite
