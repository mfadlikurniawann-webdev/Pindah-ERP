# Deploy

Dua cara menaruh Odoo di internet tanpa biaya. Keduanya memakai `docker-compose.yml`
yang sama dengan lokal.

| Cara | Cocok untuk | Kekurangan |
|---|---|---|
| A. Cloudflare Tunnel dari laptop | Demo singkat ke rekruter | Mati saat laptop mati |
| B. VPS gratis + Nginx + HTTPS | Demo yang selalu bisa dibuka | Pendaftaran butuh kartu kredit untuk verifikasi |

Untuk perusahaan sungguhan, pakai VPS berbayar dengan RAM minimal 4 GB dan cadangan
di luar server. Prosedurnya sama dengan cara B.

## A. Cloudflare Tunnel

1. Jalankan Odoo secara lokal sesuai [setup-lokal.md](setup-lokal.md).
2. Pasang `cloudflared` dari situs Cloudflare.
3. Jalankan:

   ```bash
   cloudflared tunnel --url http://localhost:8069
   ```

4. Bagikan alamat `https://....trycloudflare.com` yang muncul.

Alamatnya berganti setiap kali dijalankan. Untuk alamat tetap, buat tunnel bernama
dengan akun Cloudflare dan domain sendiri.

## B. VPS gratis

Contoh ini memakai Oracle Cloud Always Free dengan Ubuntu 24.04. Kuota tier gratisnya
pernah berubah; cek halaman resmi Oracle sebelum membuat instance. Odoo demo ini cukup
dengan 1 OCPU dan 6 GB RAM.

Instance Ampere berprosesor ARM. Pastikan image `odoo:19.0` tersedia untuk `arm64`
dengan `docker manifest inspect odoo:19.0`. Bila tidak, pakai instance AMD atau build
image sendiri dari source Odoo.

### 1. Siapkan server

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl git nginx certbot python3-certbot-nginx
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # keluar lalu masuk SSH lagi
```

Buka port 80 dan 443 di dua tempat: Security List di konsol cloud, dan firewall server.
Jangan buka port 8069 ke publik.

```bash
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save     # bila paketnya ada
```

### 2. Pasang aplikasi

```bash
git clone https://github.com/mfadlikurniawann-webdev/Pindah-ERP.git
cd Pindah-ERP
cp .env.example .env
cp config/odoo.conf.example config/odoo.conf
```

Di server, isi dengan nilai yang kuat dan unik:

| Berkas | Kunci | Nilai |
|---|---|---|
| `.env` | `DB_PASSWORD` | password acak panjang |
| `config/odoo.conf` | `admin_passwd` | password acak panjang, berbeda dari di atas |
| `config/odoo.conf` | `proxy_mode` | `True` |

Supaya Odoo hanya bisa dicapai lewat Nginx, ubah port di `docker-compose.yml` menjadi
`"127.0.0.1:${ODOO_PORT:-8069}:8069"`. Lalu jalankan `./scripts/setup.sh`.

### 3. Domain

Domain gratis bisa didapat dari layanan DNS dinamis, misalnya DuckDNS. Arahkan domain
ke IP publik server.

### 4. Nginx dan HTTPS

Simpan sebagai `/etc/nginx/sites-available/odoo`, ganti `odoo.contoh.id` dengan domainmu:

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 80;
    server_name odoo.contoh.id;
    client_max_body_size 50m;

    proxy_read_timeout 720s;
    proxy_connect_timeout 720s;
    proxy_send_timeout 720s;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;

    location /websocket {
        proxy_pass http://127.0.0.1:8069;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }

    location / {
        proxy_pass http://127.0.0.1:8069;
    }

    gzip on;
    gzip_types text/css text/plain application/json application/javascript;
}
```

```bash
sudo ln -s /etc/nginx/sites-available/odoo /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d odoo.contoh.id
```

Konfigurasi ini untuk Odoo tanpa worker terpisah (`workers = 0`, bawaan image). Bila
nanti `workers` dinaikkan, Odoo melayani websocket di port 8072. Arahkan
`location /websocket` ke port itu dan buka port 8072 di `docker-compose.yml`, hanya
untuk `127.0.0.1`.

### 5. Cadangan harian

Simpan sebagai `~/backup-odoo.sh`:

```bash
#!/bin/bash
set -euo pipefail
cd ~/Pindah-ERP
mkdir -p ~/backups
STAMP=$(date +%F)
docker compose exec -T db pg_dump -U odoo -Fc pindah > ~/backups/pindah-$STAMP.dump
docker compose run --rm -T --user root -v ~/backups:/backups odoo \
    tar czf /backups/filestore-$STAMP.tar.gz -C /var/lib/odoo filestore/pindah
find ~/backups -mtime +14 -delete
```

```bash
chmod +x ~/backup-odoo.sh
crontab -e
# tambahkan baris ini untuk jalan setiap pukul 01.00:
0 1 * * * /home/ubuntu/backup-odoo.sh >> /home/ubuntu/backup.log 2>&1
```

Cadangan di server yang sama tidak melindungi dari server hilang. Salin berkasnya ke
tempat lain secara berkala.

Memulihkan:

```bash
docker compose stop odoo
docker compose exec -T db dropdb -U odoo pindah
docker compose exec -T db createdb -U odoo pindah
docker compose exec -T db pg_restore -U odoo -d pindah < ~/backups/pindah-YYYY-MM-DD.dump
docker compose start odoo
```

### 6. Memperbarui aplikasi

```bash
cd ~/Pindah-ERP
~/backup-odoo.sh
git pull
docker compose pull
docker compose run --rm odoo odoo -d pindah -u jembatan_migration,jembatan_reconcile --stop-after-init
docker compose up -d
```

## Daftar periksa sebelum dibuka ke publik

1. Password `admin` sudah diganti.
2. `admin_passwd` dan `DB_PASSWORD` acak dan unik.
3. `list_db = False` dan `dbfilter` terisi, supaya halaman pengelola database tertutup.
4. Port 8069 tidak terbuka ke internet.
5. HTTPS aktif dan `proxy_mode = True`.
6. Cadangan harian berjalan dan sudah pernah dicoba dipulihkan.
