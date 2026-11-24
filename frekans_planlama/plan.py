#!/usr/bin/env python3
"""DWDM frekans planlama aracı.

Kullanım:
  python plan.py analiz                         # mevcut durumu raporla -> cikti/analiz.xlsx
  python plan.py ata -s 200G -r "ILKADIM_MASTER > SITE_MASTER > ATAKUM_MASTER" [-t TALEP1] [--kaydet]
  python plan.py ata -g 150 -r "..."            # hız tanımlı değilse genişlik doğrudan
  python plan.py toplu talepler.xlsx [--kaydet]  # Excel/CSV'deki tüm talepleri sırayla planla
  python plan.py yeniden                        # kurala uymayan mevcut servisler için yeni frekans + taşıma sırası
  python plan.py sablon                          # talep şablonu üret
  python plan.py ara FATSA                       # ME/link adlarında ara (rota yazarken yardımcı)
  python plan.py planlananlar [--sil TALEP]      # kaydedilmiş (NMS'e henüz girmemiş) planlar

Veri dosyaları varsayılan olarak veri/ServiceInfo.xlsx ve veri/ServiceRoute.xlsx'tir.
--kaydet ile yapılan atamalar veri/planlanan.csv'ye yazılır ve sonraki taleplerde dolu sayılır.
NMS'ten yeni export alındığında, NMS'te artık görünen talepler bu dosyadan otomatik düşülür.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from spektrum.model import Config, Kanal
from spektrum.nms import ag_kur, rota_dosyasindan_linkler
from spektrum.planlayici import Planlayici, Sonuc
from spektrum.rapor import analiz_raporu, talep_raporu
from spektrum.rota import RotaCozucu, RotaHatasi

KOK = Path(__file__).resolve().parent
PLANLANAN_SUTUN = ["Talep", "Merkez_THz", "Genislik_GHz", "Zone", "Linkler", "Tarih"]


def yukle(a):
    cfg = Config.yukle(a.config)
    ag, servisler, uyarilar = ag_kur(cfg, Path(a.info) if a.info else None, Path(a.route))
    pl = Path(a.planlanan)
    if pl.exists():
        df = pd.read_csv(pl, dtype={"Talep": str})
        nms_de = set(servisler["Servis"]) if len(servisler) else set()
        dus = df[df.Talep.isin(nms_de)]
        if len(dus):
            print(f"Bilgi: {len(dus)} planlanan talep artık NMS'te görünüyor, planlanan listesinden düşüldü: "
                  + ", ".join(dus.Talep))
            df = df[~df.Talep.isin(nms_de)]
            df.to_csv(pl, index=False)
        for r in df.itertuples(index=False):
            for lid in str(r.Linkler).split(" ;; "):
                if lid not in ag.linkler:
                    uyarilar.append(f"Planlanan {r.Talep}: link artık topolojide yok: {lid}")
                    continue
                ag.kanal_ekle(lid, Kanal(r.Talep, float(r.Merkez_THz), float(r.Genislik_GHz), "Working", "PLAN"))
    return cfg, ag, servisler, uyarilar


def kaydet(a, sonuclar: list[Sonuc]):
    pl = Path(a.planlanan)
    eski = pd.read_csv(pl, dtype={"Talep": str}) if pl.exists() else pd.DataFrame(columns=PLANLANAN_SUTUN)
    yeni = [dict(Talep=s.talep, Merkez_THz=s.oneri.merkez, Genislik_GHz=s.genislik, Zone=s.oneri.zone,
                 Linkler=" ;; ".join(s.linkler), Tarih=datetime.now().strftime("%Y-%m-%d %H:%M"))
            for s in sonuclar if s.oneri]
    if yeni:
        pd.concat([eski, pd.DataFrame(yeni)], ignore_index=True).to_csv(pl, index=False)
        print(f"{len(yeni)} atama {pl} dosyasına kaydedildi.")


def yazdir(s: Sonuc, ag):
    print("=" * 78)
    h = f"{s.hiz}, " if s.hiz else ""
    print(f"Talep      : {s.talep}   ({h}{s.genislik} GHz -> ana zone {s.ana_zone})")
    print(f"Rota       : {len(s.linkler)} link")
    for lid in s.linkler:
        k = f"  %{s.oneri.link_kullanim.get(lid, 0) * 100:5.1f}" if s.oneri else ""
        d = "  <-- DARBOĞAZ" if lid in s.darbogaz else ""
        print(f"   - {lid}{k}{d}")
    print(f"Durum      : {s.durum}")
    if s.oneri:
        o = s.oneri
        print(f"ÖNERİ      : {o.merkez:.5f} THz  ({o.alt:.5f} - {o.ust:.5f}), zone {o.zone}, "
              f"rotadaki en yüksek zone kullanımı (atama sonrası) %{o.max_kullanim * 100:.1f}")
    print(f"Açıklama   : {s.aciklama}")
    if s.alternatifler:
        print("Alternatif : " + ", ".join(f"{x.merkez:.5f} ({x.zone})" for x in s.alternatifler))
    for u in s.uyarilar:
        print(f"UYARI      : {u}")


def cmd_analiz(a):
    cfg, ag, sv, uy = yukle(a)
    out = Path(a.cikti or KOK / "cikti" / "analiz.xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)
    analiz_raporu(ag, sv, uy, out)
    print(f"{len(ag.linkler)} link, {len(ag.me_listesi)} ME, {len(sv)} servis segmenti okundu.")
    print(f"Rapor: {out}")


def cmd_yeniden(a):
    import copy
    from spektrum.rapor import yeniden_planlama_raporu
    from spektrum.yeniden import yeniden_planla
    cfg, ag, sv, uy = yukle(a)
    once = copy.deepcopy(ag)
    satirlar, bs = yeniden_planla(ag)
    out = Path(a.cikti or KOK / "cikti" / "yeniden_planlama.xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)
    yeniden_planlama_raporu(once, ag, satirlar, bs, out)
    from collections import Counter
    print(f"{len(bs)} kanal incelendi, {len(satirlar)} kanal yeniden planlandı.")
    print("Durum:", dict(Counter(t.durum for t in satirlar)))
    print("Adım :", dict(Counter(t.adim or "geçici/-" for t in satirlar)))
    print(f"Rapor: {out}")


def _linkler(a, ag, cozucu, rota: str | None, rota_dosyasi: str | None, talep: str):
    if rota_dosyasi:
        d = rota_dosyasindan_linkler(ag, Path(rota_dosyasi), None)
        if talep in d:
            return d[talep], []
        if len(d) == 1:
            return next(iter(d.values())), []
        raise RotaHatasi(f"Rota dosyasında '{talep}' bulunamadı (mevcut: {', '.join(d)})")
    return cozucu.coz(rota)


def cmd_ata(a):
    cfg, ag, sv, uy = yukle(a)
    p = Planlayici(ag)
    cozucu = RotaCozucu(ag)
    talep = a.talep or f"YENI-{datetime.now():%Y%m%d-%H%M%S}"
    try:
        linkler, uyari = _linkler(a, ag, cozucu, a.rota, a.rota_dosyasi, talep)
    except RotaHatasi as e:
        sys.exit(f"Rota hatası: {e}")
    try:
        g = cfg.genislik_coz(a.hiz, a.genislik)
    except ValueError as e:
        sys.exit(f"Hata: {e}")
    s = p.ata(talep, g, linkler, a.zone, a.alternatif)
    s.hiz = (a.hiz or cfg.hiz_tahmini(g)).upper()
    s.uyarilar = uyari + s.uyarilar
    yazdir(s, ag)
    if a.kaydet and s.oneri:
        kaydet(a, [s])
    if a.cikti:
        p.isle(s)
        talep_raporu(ag, [s], Path(a.cikti))
        print(f"Rapor: {a.cikti}")


def cmd_toplu(a):
    cfg, ag, sv, uy = yukle(a)
    p = Planlayici(ag)
    cozucu = RotaCozucu(ag)
    yol = Path(a.dosya)
    df = (pd.read_csv(yol, dtype=str) if yol.suffix.lower() == ".csv" else pd.read_excel(yol, dtype=str)).fillna("")
    df.columns = [c.strip() for c in df.columns]
    sonuclar = []
    for i, r in df.iterrows():
        talep = r.get("Talep") or f"SATIR-{i + 2}"
        hiz = str(r.get("Hiz", "")).strip()
        try:
            g = cfg.genislik_coz(hiz, r.get("Genislik_GHz", ""))
        except ValueError as e:
            s = Sonuc(talep, 0, "-", [], None, [], "GIRDI_HATASI", str(e), hiz=hiz)
            sonuclar.append(s)
            yazdir(s, ag)
            continue
        hiz = (hiz or cfg.hiz_tahmini(g)).upper()
        try:
            linkler, uyari = _linkler(a, ag, cozucu, r.get("Rota") or None, r.get("RotaDosyasi") or None, talep)
        except RotaHatasi as e:
            s = Sonuc(talep, g, "-", [], None, [], "ROTA_HATASI", str(e), hiz=hiz)
            sonuclar.append(s)
            yazdir(s, ag)
            continue
        s = p.ata(talep, g, linkler, r.get("Zone") or None, a.alternatif)
        s.hiz = hiz
        s.uyarilar = uyari + s.uyarilar
        p.isle(s)  # sonraki talepler bu atamayı dolu görür
        sonuclar.append(s)
        yazdir(s, ag)
    out = Path(a.cikti or KOK / "cikti" / f"talep_sonuclari_{datetime.now():%Y%m%d_%H%M}.xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)
    talep_raporu(ag, sonuclar, out)
    print(f"\nRapor: {out}")
    if a.kaydet:
        kaydet(a, sonuclar)


def cmd_sablon(a):
    out = Path(a.cikti or KOK / "talep_sablonu.xlsx")
    pd.DataFrame([
        dict(Talep="ORNEK-1", Hiz="100G", Genislik_GHz="", Zone="",
             Rota="055_ILKADIM_MASTER_5001 > 055_SITE_MASTER_5002 > 055_ATAKUM_MASTER_ILKADIM/SITE YONU_5064",
             RotaDosyasi="", Not="Hiz verilirse genişlik otomatik: 100G=50 GHz, 200G=75 GHz"),
        dict(Talep="ORNEK-2", Hiz="200G", Genislik_GHz="", Zone="", Rota="RIZE > KALKANDERE > IKIZDERE > ISPIR",
             RotaDosyasi="", Not="Site adları da kullanılabilir"),
        dict(Talep="ORNEK-3", Hiz="", Genislik_GHz=150, Zone="", Rota="FATSA > ORDU", RotaDosyasi="",
             Not="Hız tanımlı değilse genişlik doğrudan yazılır; Zone boşsa genişlikten belirlenir"),
    ]).to_excel(out, index=False)
    print(f"Şablon: {out}")


def cmd_ara(a):
    cfg, ag, sv, uy = yukle(a)
    from spektrum.model import _norm
    t = _norm(a.ifade)
    mes = sorted(m for m in ag.me_listesi if t in _norm(m))
    print(f"ME ({len(mes)}):")
    for m in mes:
        print("  ", m)
    lks = sorted(l for l in ag.linkler if t in _norm(l))
    print(f"Link ({len(lks)}):")
    for l in lks:
        print("  ", l)


def cmd_planlananlar(a):
    pl = Path(a.planlanan)
    if not pl.exists():
        print("Kayıtlı plan yok.")
        return
    df = pd.read_csv(pl, dtype={"Talep": str})
    if a.sil:
        df = df[df.Talep != a.sil]
        df.to_csv(pl, index=False)
        print(f"{a.sil} silindi.")
    print(df.drop(columns=["Linkler"]).to_string(index=False))


def main():
    ap = argparse.ArgumentParser(description="DWDM frekans planlama", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument("--config", default=str(KOK / "config.yaml"))
    ap.add_argument("--info", default=str(KOK / "veri" / "ServiceInfo.xlsx"))
    ap.add_argument("--route", default=str(KOK / "veri" / "ServiceRoute.xlsx"))
    ap.add_argument("--planlanan", default=str(KOK / "veri" / "planlanan.csv"))
    sub = ap.add_subparsers(dest="komut", required=True)

    s = sub.add_parser("analiz", help="mevcut durum raporu")
    s.add_argument("-o", "--cikti")
    s.set_defaults(f=cmd_analiz)

    s = sub.add_parser("ata", help="tek talep için frekans öner")
    s.add_argument("-s", "--hiz", help="servis hızı: 100G (-> 50 GHz) / 200G (-> 75 GHz)")
    s.add_argument("-g", "--genislik", type=int, help="kanal genişliği GHz (hız yerine; 100/150/... için)")
    s.add_argument("-r", "--rota", help="'A > B > C' (ME veya site adları)")
    s.add_argument("--rota-dosyasi", help="NMS Service Route formatında rota dosyası")
    s.add_argument("-t", "--talep", help="talep/servis adı")
    s.add_argument("-z", "--zone", help="zone'u elle zorla (Z1..Z4)")
    s.add_argument("-a", "--alternatif", type=int, default=5)
    s.add_argument("--kaydet", action="store_true", help="atamayı planlanan.csv'ye kaydet")
    s.add_argument("-o", "--cikti", help="Excel rapor yolu")
    s.set_defaults(f=cmd_ata)

    s = sub.add_parser("toplu", help="Excel/CSV'deki talepleri sırayla planla")
    s.add_argument("dosya")
    s.add_argument("-a", "--alternatif", type=int, default=5)
    s.add_argument("--kaydet", action="store_true")
    s.add_argument("--rota-dosyasi", dest="rota_dosyasi_genel", help=argparse.SUPPRESS)
    s.add_argument("-o", "--cikti")
    s.set_defaults(f=cmd_toplu)

    s = sub.add_parser("yeniden", help="kurala uymayan mevcut servisleri yeniden planla")
    s.add_argument("-o", "--cikti")
    s.set_defaults(f=cmd_yeniden)

    s = sub.add_parser("sablon", help="talep şablonu üret")
    s.add_argument("-o", "--cikti")
    s.set_defaults(f=cmd_sablon)

    s = sub.add_parser("ara", help="ME / link ara")
    s.add_argument("ifade")
    s.set_defaults(f=cmd_ara)

    s = sub.add_parser("planlananlar", help="kayıtlı planları listele / sil")
    s.add_argument("--sil")
    s.set_defaults(f=cmd_planlananlar)

    a = ap.parse_args()
    if a.komut == "ata" and not (a.rota or a.rota_dosyasi):
        ap.error("ata: --rota veya --rota-dosyasi gerekli")
    if a.komut == "ata" and not (a.hiz or a.genislik):
        ap.error("ata: --hiz (100G/200G) veya --genislik gerekli")
    a.f(a)


if __name__ == "__main__":
    main()
