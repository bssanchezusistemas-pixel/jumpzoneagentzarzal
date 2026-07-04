#!/usr/bin/env python3
"""Smoke test post-deploy — Jumping Fit producción."""

import os
import sys
import httpx

BASE = os.environ.get("PROD_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


def check(name: str, ok: bool, detail: str = ""):
    status = "OK" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> int:
    ok_all = True
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        r = client.get(f"{BASE}/health")
        ok_all &= check("GET /health", r.status_code == 200, r.text[:80])

        r = client.get(f"{BASE}/web/index.html")
        ok_all &= check("GET /web/index.html", r.status_code == 200)

        r = client.get(f"{BASE}/api/planes")
        data = r.json() if r.status_code == 200 else {}
        planes = data if isinstance(data, list) else data.get("planes", [])
        ok_all &= check("GET /api/planes", r.status_code == 200 and isinstance(planes, list))

        r = client.get(f"{BASE}/api/slots")
        ok_all &= check("GET /api/slots", r.status_code == 200)

        if ADMIN_PASSWORD:
            r = client.post(
                f"{BASE}/api/auth/login",
                json={"usuario": ADMIN_USER, "password": ADMIN_PASSWORD},
            )
            token = r.json().get("token") if r.status_code == 200 else None
            ok_all &= check("POST /api/auth/login", bool(token))
            if token:
                r = client.get(
                    f"{BASE}/api/admin/pendientes",
                    headers={"Authorization": f"Bearer {token}"},
                )
                ok_all &= check("GET /api/admin/pendientes", r.status_code == 200)
        else:
            print("[SKIP] POST /api/auth/login — ADMIN_PASSWORD no definido")

        verify = os.environ.get("META_VERIFY_TOKEN", "")
        provider = os.environ.get("WHATSAPP_PROVIDER", "").lower()
        if verify and provider == "meta":
            r = client.get(
                f"{BASE}/webhook",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": verify,
                    "hub.challenge": "999888",
                },
            )
            ok_all &= check(
                "GET /webhook (Meta verify)",
                r.status_code == 200 and r.text.strip() == "999888",
                r.text[:40],
            )
        else:
            print("[SKIP] GET /webhook Meta — requiere WHATSAPP_PROVIDER=meta y META_VERIFY_TOKEN")

    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
