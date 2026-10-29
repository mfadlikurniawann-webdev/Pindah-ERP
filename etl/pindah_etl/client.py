"""Klien kecil untuk JSON-2 API Odoo 19, hanya memakai pustaka standar.

Setiap panggilan adalah ``POST /json/2/<model>/<metode>`` dengan argumen bernama
di badan JSON dan API key di header ``Authorization: bearer``.
"""

import json
import urllib.error
import urllib.request


class OdooError(RuntimeError):
    pass


class OdooClient:
    def __init__(self, url: str, database: str, api_key: str, timeout: int = 600):
        self.url = url.rstrip("/")
        self.database = database
        self.api_key = api_key
        self.timeout = timeout

    def call(self, model: str, method: str, **kwargs):
        request = urllib.request.Request(
            f"{self.url}/json/2/{model}/{method}",
            data=json.dumps(kwargs).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"bearer {self.api_key}",
                "X-Odoo-Database": self.database,
                "User-Agent": "pindah-etl",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            try:
                message = json.loads(body).get("message", body)
            except ValueError:
                message = body
            raise OdooError(f"{model}.{method} gagal ({exc.code}): {message}") from exc
        except urllib.error.URLError as exc:
            raise OdooError(f"Tidak bisa menghubungi Odoo di {self.url}: {exc.reason}") from exc
