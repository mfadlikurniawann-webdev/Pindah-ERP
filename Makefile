# Jalan pintas. Semua perintah juga ditulis lengkap di docs/setup-lokal.md
# untuk yang tidak punya `make` (misalnya Windows tanpa WSL).
.PHONY: setup up down logs shell migrate dry-run reconcile test test-etl test-odoo lint

setup:        ## Siapkan database dari nol
	./scripts/setup.sh

up:           ## Nyalakan Odoo dan PostgreSQL
	docker compose up -d

down:         ## Matikan (data tetap ada di volume)
	docker compose down

logs:         ## Ikuti log Odoo
	docker compose logs -f odoo

dry-run:      ## Transform lalu uji coba muat tanpa menyimpan
	cd etl && python -m pindah_etl transform && python -m pindah_etl load --dry-run

migrate:      ## Transform, muat, lalu rekonsiliasi
	cd etl && python -m pindah_etl all

reconcile:    ## Bandingkan saldo Accurate dengan Odoo
	cd etl && python -m pindah_etl reconcile

test: test-etl test-odoo

test-etl:     ## Test ETL (tanpa Odoo)
	python -m pytest -q

test-odoo:    ## Test modul Odoo di database sementara
	docker compose run --rm odoo odoo -d pindah_test -i jembatan_reconcile \
		--test-tags /jembatan_migration,/jembatan_reconcile --stop-after-init --no-http

lint:
	ruff check . && ruff format --check .
