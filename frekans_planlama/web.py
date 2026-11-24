#!/usr/bin/env python3
"""Tarayıcı arayüzü.

  python web.py                 # http://127.0.0.1:8080 adresinde açılır
  python web.py --port 9000 --host 0.0.0.0   # ekipten erişim için (ağınızda güvenli olduğundan emin olun)
  python web.py --statik cikti/web           # sunucusuz anlık görünüm (index.html + veri.json) üretir

Ek bağımlılık yok (Python standart kütüphanesi). Veri dosyaları plan.py ile aynıdır.
"""
from __future__ import annotations

import argparse
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from plan import KOK, PLANLANAN_SUTUN, yukle
from spektrum.planlayici import Planlayici
from spektrum.rota import RotaCozucu, RotaHatasi
from spektrum.webveri import sonuc_json, tum_veri

ARAYUZ = KOK / "web" / "index.html"
ISKELET = ('<!doctype html><html lang="tr"><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
           '<style>body{margin:0}[hidden]{display:none!important}</style></head><body>')


class Durum:
    def __init__(self, args):
        self.args = args
        self.kilit = threading.Lock()
        self.yenile()

    def yenile(self):
        with self.kilit:
            self.cfg, self.ag, sv, uy = yukle(self.args)
            self.veri = json.dumps(tum_veri(self.ag, sv, uy), ensure_ascii=False).encode()
            self.cozucu = RotaCozucu(self.ag)

    def ata(self, istek: dict) -> dict:
        with self.kilit:
            try:
                g = self.cfg.genislik_coz(istek.get("hiz") or None, istek.get("genislik") or None)
                linkler, uyari = self.cozucu.coz(istek.get("rota", ""))
            except (ValueError, RotaHatasi) as e:
                return dict(hata=str(e))
            talep = (istek.get("talep") or "").strip() or f"YENI-{datetime.now():%Y%m%d-%H%M%S}"
            s = Planlayici(self.ag).ata(talep, g, linkler, istek.get("zone") or None)
            s.hiz = (istek.get("hiz") or self.cfg.hiz_tahmini(g)).upper()
            s.uyarilar = uyari + s.uyarilar
            return sonuc_json(self.ag, s)

    def kaydet(self, istek: dict) -> dict:
        pl = Path(self.args.planlanan)
        eski = pd.read_csv(pl, dtype={"Talep": str}) if pl.exists() else pd.DataFrame(columns=PLANLANAN_SUTUN)
        if istek["talep"] in set(eski.Talep):
            return dict(hata=f"'{istek['talep']}' adıyla kayıtlı bir plan zaten var")
        yeni = dict(Talep=istek["talep"], Merkez_THz=istek["merkez"], Genislik_GHz=istek["genislik"],
                    Zone=istek["zone"], Linkler=" ;; ".join(istek["linkler"]),
                    Tarih=datetime.now().strftime("%Y-%m-%d %H:%M"))
        pd.concat([eski, pd.DataFrame([yeni])], ignore_index=True).to_csv(pl, index=False)
        self.yenile()
        return dict(tamam=True)


def handler_sinifi(durum: Durum):
    class H(BaseHTTPRequestHandler):
        def _yanit(self, kod, govde: bytes, tip="application/json; charset=utf-8"):
            self.send_response(kod)
            self.send_header("Content-Type", tip)
            self.send_header("Content-Length", str(len(govde)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(govde)

        def _json(self, obj, kod=200):
            self._yanit(kod, json.dumps(obj, ensure_ascii=False).encode())

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                html = ISKELET + ARAYUZ.read_text(encoding="utf-8").replace("__MOD__", "sunucu") + "</body></html>"
                self._yanit(200, html.encode(), "text/html; charset=utf-8")
            elif self.path == "/api/veri":
                self._yanit(200, durum.veri)
            else:
                self._json(dict(hata="bulunamadı"), 404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                istek = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self._json(dict(hata="geçersiz istek"), 400)
            if self.path == "/api/ata":
                self._json(durum.ata(istek))
            elif self.path == "/api/kaydet":
                self._json(durum.kaydet(istek))
            elif self.path == "/api/yenile":
                durum.yenile()
                self._json(dict(tamam=True))
            else:
                self._json(dict(hata="bulunamadı"), 404)

        def log_message(self, fmt, *a):
            pass

    return H


def main():
    ap = argparse.ArgumentParser(description="Frekans planlama web arayüzü")
    ap.add_argument("--config", default=str(KOK / "config.yaml"))
    ap.add_argument("--info", default=str(KOK / "veri" / "ServiceInfo.xlsx"))
    ap.add_argument("--route", default=str(KOK / "veri" / "ServiceRoute.xlsx"))
    ap.add_argument("--planlanan", default=str(KOK / "veri" / "planlanan.csv"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--statik", help="sunucusuz görünümü bu klasöre yaz")
    a = ap.parse_args()
    args = SimpleNamespace(config=a.config, info=a.info, route=a.route, planlanan=a.planlanan)

    if a.statik:
        cfg, ag, sv, uy = yukle(args)
        out = Path(a.statik)
        out.mkdir(parents=True, exist_ok=True)
        (out / "veri.json").write_text(json.dumps(tum_veri(ag, sv, uy), ensure_ascii=False), encoding="utf-8")
        (out / "index.html").write_text(ARAYUZ.read_text(encoding="utf-8").replace("__MOD__", "statik"),
                                        encoding="utf-8")
        print(f"Statik görünüm: {out / 'index.html'} (veri.json ile aynı klasörde sunulmalı)")
        return

    print("Veri yükleniyor...")
    durum = Durum(args)
    srv = ThreadingHTTPServer((a.host, a.port), handler_sinifi(durum))
    print(f"Hazır: http://{a.host}:{a.port}  (durdurmak için Ctrl+C)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
