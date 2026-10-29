# Dijalankan lewat `odoo shell` SEBELUM modul akuntansi dipasang,
# supaya Odoo memilih bagan akun Indonesia (l10n_id) dan mata uang IDR.
# Lihat docs/setup-lokal.md langkah 3.
company = env.ref("base.main_company")
idr = env.ref("base.IDR")
idr.active = True
company.write(
    {
        "name": "PT Kopi Rimba Nusantara (fiktif)",
        "country_id": env.ref("base.id").id,
        "currency_id": idr.id,
        "city": "Bandar Lampung",
    }
)
env.cr.commit()
print(f"Perusahaan siap: {company.name}, {company.country_id.name}, {company.currency_id.name}")
