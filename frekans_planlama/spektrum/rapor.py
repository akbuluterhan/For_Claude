"""Excel raporları: mevcut durum analizi ve talep sonuçları."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .model import Ag
from .planlayici import Sonuc

ZONE_RENK = {"Z1": ("EDEDED", "8C8C8C"), "Z2": ("D6DCE5", "5B7195"),
             "Z3": ("FBE0D2", "D0703C"), "Z4": ("E2EFDA", "5E9A3E")}
CAKISMA = "E00000"
PLAN = "7030A0"
BASLIK = Font(bold=True, color="FFFFFF")
BASLIK_DOLGU = PatternFill("solid", fgColor="305496")


def _tablo(ws, df: pd.DataFrame, genislik: dict[str, int] | None = None):
    ws.append(list(df.columns))
    for c in ws[1]:
        c.font, c.fill = BASLIK, BASLIK_DOLGU
    for row in df.itertuples(index=False):
        ws.append([None if (isinstance(v, float) and pd.isna(v)) else v for v in row])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for i, col in enumerate(df.columns, 1):
        w = (genislik or {}).get(col) or min(60, max(10, len(str(col)) + 2,
                                                     *(len(str(v)) + 1 for v in df[col].head(200))))
        ws.column_dimensions[get_column_letter(i)].width = w


def link_tablosu(ag: Ag) -> pd.DataFrame:
    cfg = ag.cfg
    satir = []
    for lid, l in ag.linkler.items():
        d = dict(Link=lid, SiteA=l.site_a, SiteB=l.site_b, Tip="site içi" if l.site_ici else "siteler arası",
                 KanalSayisi=len({(k.servis, k.merkez) for k in ag.kanallar[lid]}))
        for z in cfg.zonelar:
            d[f"{z}_Kullanim_%"] = round(ag.zone_kullanim(lid, z) * 100, 1)
        for z in cfg.zonelar:
            enb, frag = ag.parcalanma(lid, z)
            d[f"{z}_EnBuyukBosBlok_GHz"] = enb
            d[f"{z}_Parcalanma"] = frag
        d["EsikAsanZonelar"] = ", ".join(z for z in cfg.zonelar
                                         if ag.zone_kullanim(lid, z) > cfg.esik + 1e-9)
        satir.append(d)
    df = pd.DataFrame(satir)
    return df.sort_values(["Tip", "SiteA", "SiteB"]).reset_index(drop=True)


def cakismalar(ag: Ag) -> pd.DataFrame:
    satir = {}
    for lid in ag.linkler:
        for s, ks in enumerate(ag.doluluk(lid)):
            uniq = {(k.servis, k.merkez, k.genislik) for k in ks}
            if len(uniq) > 1:
                key = (lid, tuple(sorted(uniq)))
                satir.setdefault(key, []).append(s)
    out = []
    for (lid, srv), slots in satir.items():
        out.append(dict(Link=lid,
                        Servisler=" | ".join(f"{s} @{m} THz/{g:g}GHz" for s, m, g in srv),
                        CakisanAralik_THz=f"{ag.cfg.thz(min(slots))} - {ag.cfg.thz(max(slots) + 1)}",
                        Cakisma_GHz=len(slots) * ag.cfg.adim))
    return pd.DataFrame(out, columns=["Link", "Servisler", "CakisanAralik_THz", "Cakisma_GHz"])


def spektrum_haritasi(ws, ag: Ag, linkler: list[str] | None = None, vurgula: dict | None = None):
    """Satır = link, sütun = 12.5 GHz slot. Dolu slot koyu zone rengi, çakışma kırmızı,
    planlanan mor, boş açık zone rengi."""
    cfg = ag.cfg
    linkler = linkler or sorted(ag.linkler, key=lambda x: (ag.linkler[x].site_ici, x))
    zone_slot = {}
    for kod, z in cfg.zonelar.items():
        for s in range(z.s0, z.s1):
            zone_slot[s] = kod
    s_ilk, s_son = cfg.s_min, cfg.slot_sayisi
    ws.cell(1, 1, "Link \\ Slot başlangıç (THz)").font = Font(bold=True)
    ws.cell(2, 1, "Zone").font = Font(bold=True)
    for j, s in enumerate(range(s_ilk, s_son), 2):
        c = ws.cell(1, j, cfg.thz(s))
        c.alignment = Alignment(text_rotation=90)
        c.font = Font(size=7)
        z = zone_slot.get(s)
        zc = ws.cell(2, j, z or "")
        zc.font = Font(size=7, bold=True)
        if z:
            zc.fill = PatternFill("solid", fgColor=ZONE_RENK.get(z, ("FFFFFF", "000000"))[1])
        ws.column_dimensions[get_column_letter(j)].width = 2.2
    ws.column_dimensions["A"].width = 70
    ws.row_dimensions[1].height = 48
    dolgular = {}

    def dolgu(renk):
        if renk not in dolgular:
            dolgular[renk] = PatternFill("solid", fgColor=renk)
        return dolgular[renk]

    for i, lid in enumerate(linkler, 3):
        ws.cell(i, 1, lid).font = Font(size=8)
        dol = ag.doluluk(lid)
        for j, s in enumerate(range(s_ilk, s_son), 2):
            ks = dol[s]
            z = zone_slot.get(s)
            acik, koyu = ZONE_RENK.get(z, ("FFFFFF", "404040"))
            if vurgula and lid in vurgula and vurgula[lid][0] <= s < vurgula[lid][1]:
                ws.cell(i, j).fill = dolgu("00B050")
                continue
            if not ks:
                ws.cell(i, j).fill = dolgu(acik)
                continue
            if len({(k.servis, k.merkez) for k in ks}) > 1:
                ws.cell(i, j).fill = dolgu(CAKISMA)
            elif any(k.kaynak == "PLAN" for k in ks):
                ws.cell(i, j).fill = dolgu(PLAN)
            else:
                ws.cell(i, j).fill = dolgu(koyu)
    ws.freeze_panes = "B3"
    r = len(linkler) + 4
    for metin, renk in [("Dolu (zone rengi koyu)", ZONE_RENK["Z2"][1]), ("Boş (zone rengi açık)", ZONE_RENK["Z2"][0]),
                        ("Çakışma", CAKISMA), ("Planlanan (henüz NMS'te yok)", PLAN), ("Yeni öneri", "00B050")]:
        ws.cell(r, 2).fill = dolgu(renk)
        ws.cell(r, 3, metin)
        r += 1


def analiz_raporu(ag: Ag, servisler: pd.DataFrame, uyarilar: list[str], yol: Path):
    cfg = ag.cfg
    wb = Workbook()
    ws = wb.active
    ws.title = "Ozet"
    lt = link_tablosu(ag)
    ozet = []
    for kod, z in cfg.zonelar.items():
        k = lt[f"{kod}_Kullanim_%"]
        ozet.append(dict(Zone=kod, Aralik_THz=f"{z.baslangic} - {z.bitis}", Toplam_GHz=z.toplam_ghz,
                         Kanal_GHz="/".join(map(str, z.genislikler)) or "ihtiyaca göre",
                         DolumYonu=z.dolum_yonu, Overflow=",".join(z.overflow) or "-",
                         OrtalamaLinkKullanimi_pct=round(k.mean(), 1), EnYuksekLinkKullanimi_pct=k.max(),
                         EsikAsanLinkSayisi=int((k > cfg.esik * 100 + 1e-9).sum())))
    _tablo(ws, pd.DataFrame(ozet))
    r = ws.max_row + 2
    bilgi = [("Link sayısı", len(ag.linkler)),
             ("  siteler arası", int((lt.Tip == "siteler arası").sum())),
             ("  site içi (master/slave arası)", int((lt.Tip == "site içi").sum())),
             ("ME sayısı", len(ag.me_listesi)),
             ("Servis (segment) sayısı", len(servisler)),
             ("Çakışma kaydı", len(cakismalar(ag))),
             ("Grid dışı kanal (ör. 200G ama 75 GHz gridinde değil)",
              int(servisler.GridUyumu.str.startswith("GRID").sum()) if len(servisler) else 0),
             ("Kural dışı zone'da duran kanal", int((servisler.Zone != servisler.BeklenenZone).sum()) if len(servisler) else 0),
             ("Kullanım eşiği", f"%{int(cfg.esik * 100)}")]
    for a, b in bilgi:
        ws.cell(r, 1, a).font = Font(bold=True)
        ws.cell(r, 2, b)
        r += 1

    _tablo(wb.create_sheet("Link_Kullanim"), lt, {"Link": 70})
    sv = servisler.copy()
    if len(sv):
        sv.insert(sv.columns.get_loc("BeklenenZone") + 1, "KuralUyumu",
                  (sv.Zone == sv.BeklenenZone).map({True: "uygun", False: "FARKLI ZONE"}))
    _tablo(wb.create_sheet("Servisler"), sv, {"Servis": 55, "A End": 50, "Z End": 50})
    _tablo(wb.create_sheet("Cakismalar"), cakismalar(ag), {"Link": 70, "Servisler": 120})
    spektrum_haritasi(wb.create_sheet("Spektrum_Haritasi"), ag)
    if uyarilar:
        _tablo(wb.create_sheet("Uyarilar"), pd.DataFrame({"Uyari": uyarilar}), {"Uyari": 120})
    wb.save(yol)


def sonuc_satiri(ag: Ag, s: Sonuc) -> dict:
    o = s.oneri
    return dict(Talep=s.talep, Hiz=s.hiz, Genislik_GHz=s.genislik, AnaZone=s.ana_zone, Durum=s.durum,
                OnerilenMerkez_THz=o.merkez if o else None,
                Aralik_THz=f"{o.alt} - {o.ust}" if o else None,
                AtananZone=o.zone if o else None,
                RotadakiMaxZoneKullanimi_pct=round(o.max_kullanim * 100, 1) if o else None,
                Aciklama=s.aciklama,
                Alternatifler=", ".join(f"{a.merkez} ({a.zone}, %{a.max_kullanim * 100:.0f})" for a in s.alternatifler),
                Darbogaz=" | ".join(s.darbogaz), Uyarilar=" | ".join(s.uyarilar),
                LinkSayisi=len(s.linkler))


def talep_raporu(ag: Ag, sonuclar: list[Sonuc], yol: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Sonuclar"
    _tablo(ws, pd.DataFrame([sonuc_satiri(ag, s) for s in sonuclar]),
           {"Aciklama": 60, "Alternatifler": 60, "Uyarilar": 60, "Darbogaz": 60})
    det = []
    for s in sonuclar:
        for lid in s.linkler:
            d = dict(Talep=s.talep, Link=lid)
            if s.oneri:
                d["AtananZoneKullanimi_pct (atama sonrası)"] = round(s.oneri.link_kullanim.get(lid, 0) * 100, 1)
            d["Darbogaz"] = "EVET" if lid in s.darbogaz else ""
            det.append(d)
    _tablo(wb.create_sheet("Rota_Linkleri"), pd.DataFrame(det), {"Link": 70})
    linkler, vurgu = [], {}
    for s in sonuclar:
        for lid in s.linkler:
            if lid not in linkler:
                linkler.append(lid)
    spektrum_haritasi(wb.create_sheet("Spektrum_Rota"), ag, linkler or None, vurgu)
    wb.save(yol)
