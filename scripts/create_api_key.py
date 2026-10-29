# Dijalankan lewat `odoo shell` SESUDAH modul dipasang.
# Membuat API key untuk user admin, dipakai ETL memanggil JSON-2 API.
# Kunci hanya tampil sekali; salin ke ODOO_API_KEY di berkas .env.
from datetime import timedelta

from odoo import fields

admin = env.ref("base.user_admin")
expiration = fields.Datetime.now() + timedelta(days=90)
key = env["res.users.apikeys"].with_user(admin).sudo()._generate(None, "pindah-etl", expiration)
env.cr.commit()
print("ODOO_API_KEY=" + key)
print(f"Berlaku sampai {expiration:%Y-%m-%d}. Simpan di .env, jangan di-commit.")
