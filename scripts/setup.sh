#!/usr/bin/env bash
# Menyiapkan database Odoo lokal dari nol dalam satu perintah.
# Jalankan dari akar repo:  ./scripts/setup.sh
# Langkah manualnya (termasuk untuk PowerShell) ada di docs/setup-lokal.md.
set -euo pipefail

cd "$(dirname "$0")/.."
DB_NAME="pindah"

step() { printf '\n==> %s\n' "$1"; }

[ -f .env ] || { cp .env.example .env; echo "Dibuat .env dari .env.example. Ganti DB_PASSWORD bila perlu."; }
[ -f config/odoo.conf ] || {
    cp config/odoo.conf.example config/odoo.conf
    echo "Dibuat config/odoo.conf. GANTI admin_passwd sebelum dipakai di luar laptop sendiri."
}

step "1/6 Menyalakan PostgreSQL"
docker compose up -d db

step "2/6 Membuat database '$DB_NAME' (modul base)"
docker compose run --rm odoo odoo -d "$DB_NAME" -i base --stop-after-init

step "3/6 Mengatur perusahaan: Indonesia, IDR"
docker compose run --rm odoo bash /mnt/scripts/run_in_shell.sh /mnt/scripts/setup_company.py "$DB_NAME"

step "4/6 Memasang modul Jembatan (ikut memasang Accounting, Inventory, MRP, Sales, Purchase, l10n_id)"
docker compose run --rm odoo odoo -d "$DB_NAME" -i jembatan_reconcile --stop-after-init

step "5/6 Membuat API key untuk ETL"
KEY_LINE=$(docker compose run --rm -T odoo bash /mnt/scripts/run_in_shell.sh /mnt/scripts/create_api_key.py "$DB_NAME" \
    | grep '^ODOO_API_KEY=' | tr -d '\r')
if [ -z "$KEY_LINE" ]; then
    echo "Gagal membuat API key. Buat manual: Preferensi user > Keamanan Akun > API Keys."
    exit 1
fi
if grep -q '^ODOO_API_KEY=' .env; then
    # Tulis ulang baris ODOO_API_KEY tanpa sed -i, supaya sama di Linux dan macOS.
    grep -v '^ODOO_API_KEY=' .env > .env.tmp && echo "$KEY_LINE" >> .env.tmp && mv .env.tmp .env
else
    echo "$KEY_LINE" >> .env
fi
echo "API key disimpan di .env"

step "6/6 Menyalakan Odoo"
docker compose up -d odoo

cat << EOF

Selesai. Buka http://localhost:8069 (atau port ODOO_PORT di .env)
  login: admin   password: admin   (segera ganti lewat Preferensi)

Langkah berikutnya, migrasi data contoh:
  cd etl
  python -m pindah_etl transform
  python -m pindah_etl load --dry-run
  python -m pindah_etl load
  python -m pindah_etl reconcile
EOF
