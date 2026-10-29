#!/bin/bash
# Menjalankan skrip Python di dalam `odoo shell`, dari dalam kontainer Odoo.
# Pemakaian (dari host):
#   docker compose run --rm odoo bash /mnt/scripts/run_in_shell.sh /mnt/scripts/setup_company.py
# Cara ini tidak memakai redirect `<` di host, jadi jalan sama di Linux, macOS, dan PowerShell.
set -euo pipefail
SCRIPT="${1:?Sebutkan berkas skrip}"
DB="${2:-pindah}"
exec odoo shell -d "$DB" --db_host "$HOST" --db_user "$USER" --db_password "$PASSWORD" --no-http < "$SCRIPT"
