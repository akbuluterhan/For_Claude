"""Web arayüzü için JSON veri üretimi."""
from __future__ import annotations

import copy
from datetime import datetime

from .model import Ag
from .planlayici import Sonuc
from .rapor import link_tablosu
from .yeniden import yeniden_planla


def _kanallar(ag: Ag, lid: str) -> list[list]:
    """[servis, merkez, genişlik, rota tipleri, kaynak] — aynı servis+merkez tek satır."""
    tek: dict[tuple, list] = {}
    for k in ag.kanallar.get(lid, []):
        key = (k.servis, round(k.merkez, 6))
        if key in tek:
            if k.rota_tipi not in tek[key][3]:
                tek[key][3] += "," + k.rota_tipi
        else:
            tek[key] = [k.servis, round(k.merkez, 6), k.genislik, k.rota_tipi, k.kaynak]
    return sorted(tek.values(), key=lambda r: r[1])


def meta(ag: Ag) -> dict:
    cfg = ag.cfg
    return dict(
        olusturma=datetime.now().strftime("%Y-%m-%d %H:%M"),
        esik=cfg.esik, adim=cfg.adim, ref=cfg.ref, s_min=cfg.s_min, s_max=cfg.slot_sayisi,
        hiz_genislik=cfg.hiz_genislik,
        zonelar=[dict(kod=k, ad=z.ad, baslangic=z.baslangic, bitis=z.bitis, s0=z.s0, s1=z.s1,
                      genislikler=z.genislikler, yon=z.dolum_yonu, overflow=z.overflow,
                      toplam=z.toplam_ghz) for k, z in cfg.zonelar.items()])


def link_listesi(ag: Ag) -> list[dict]:
    lt = link_tablosu(ag).set_index("Link")
    out = []
    for lid, l in ag.linkler.items():
        r = lt.loc[lid]
        out.append(dict(id=lid, a=l.a, b=l.b, siteA=l.site_a, siteB=l.site_b,
                        tip="ic" if l.site_ici else "dis",
                        kul={z: float(r[f"{z}_Kullanim_%"]) for z in ag.cfg.zonelar},
                        frag={z: float(r[f"{z}_Parcalanma"]) for z in ag.cfg.zonelar},
                        kanallar=_kanallar(ag, lid)))
    out.sort(key=lambda d: (d["tip"] == "ic", d["siteA"], d["siteB"], d["id"]))
    return out


def tum_veri(ag: Ag, servisler, uyarilar: list[str]) -> dict:
    cfg = ag.cfg
    once = copy.deepcopy(ag)
    sonra = copy.deepcopy(ag)
    satirlar, bs = yeniden_planla(sonra)
    yeniden = []
    for t in satirlar:
        b = t.birim
        yeniden.append(dict(
            adim=t.adim, servis=b.servis, hiz=cfg.hiz_tahmini(b.genislik), genislik=b.genislik,
            eski=round(b.merkez, 6), eskiZone=cfg.zone_frekans(b.merkez) or "bant dışı",
            yeni=t.yeni_merkez, yeniZone=t.yeni_zone, durum=t.durum, sorunlar=b.sorunlar,
            sira=t.bagimlilik, linkler=b.linkler, rotaTipleri=sorted(b.rota_tipleri),
            maxKul=round(t.max_kullanim * 100, 1) if t.max_kullanim is not None else None))
    tasinan = {t.birim.anahtar for t in satirlar}
    kanal_listesi = []
    for k, b in sorted(bs.items()):
        kanal_listesi.append(dict(servis=b.servis, merkez=round(b.merkez, 6), genislik=b.genislik,
                                  hiz=cfg.hiz_tahmini(b.genislik), zone=cfg.zone_frekans(b.merkez),
                                  olmali=cfg.zone_genislik(int(b.genislik)),
                                  sorunlar=b.sorunlar, tasinacak=k in tasinan,
                                  linkSayisi=len(b.linkler), rotaTipleri=sorted(b.rota_tipleri)))
    # yeniden planlanan kanallar planlayıcıda "servis@eskiMerkez" adıyla işlendi -> orijinal ada çevir
    tasinan_ad = {f"{t.birim.servis}@{t.birim.merkez}": t.birim.servis for t in satirlar}
    sonra_l = {}
    for d in link_listesi(sonra):
        kl = []
        for k in d["kanallar"]:
            if k[4] == "PLAN" and k[0] in tasinan_ad:
                k = [tasinan_ad[k[0]], k[1], k[2], k[3], "TASINDI"]
            kl.append(k)
        sonra_l[d["id"]] = dict(kul=d["kul"], kanallar=kl)
    return dict(meta=meta(once), linkler=link_listesi(once), sonraLinkler=sonra_l,
                kanallar=kanal_listesi, yeniden=yeniden,
                me=sorted(once.me_listesi), uyarilar=uyarilar)


def sonuc_json(ag: Ag, s: Sonuc) -> dict:
    def aday(a):
        return dict(merkez=a.merkez, alt=a.alt, ust=a.ust, zone=a.zone, s0=a.s0, n=a.n,
                    seviye=a.seviye, maxKul=round(a.max_kullanim * 100, 1)) if a else None
    return dict(talep=s.talep, hiz=s.hiz, genislik=s.genislik, anaZone=s.ana_zone, durum=s.durum,
                aciklama=s.aciklama, oneri=aday(s.oneri), alternatifler=[aday(a) for a in s.alternatifler],
                darbogaz=s.darbogaz, uyarilar=s.uyarilar,
                linkler=[dict(id=lid, kanallar=_kanallar(ag, lid),
                              kulSonra=round(s.oneri.link_kullanim.get(lid, 0) * 100, 1) if s.oneri else None)
                         for lid in s.linkler])
