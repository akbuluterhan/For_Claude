"""Kurala uymayan mevcut servislerin yeniden planlanması ve taşıma sırası.

Sorun türleri (kanal = servis + merkez frekans; regen ile frekans değiştiren servisin her
frekans bölümü ayrı kanaldır):
  * YANLIŞ ZONE   : kanal, hızının zone'unda değil (ör. 100G kanal Z4'te)
  * GRID DIŞI     : kanal kendi genişliğinin standart gridine oturmuyor
  * ZONE SINIRI   : kanal iki zone'a taşıyor
  * ÇAKIŞMA       : aynı linkte başka kanalla örtüşüyor (uyumlu kanal korunur, uyumsuz taşınır;
                    iki taraf da uyumluysa ikisi de yeniden planlanır)

Yöntem:
  1. Sorunlu kanallar ağdan çıkarılır, kurala uyan kanallar yerinde sabit kalır.
  2. Sorunlu kanallar zor olandan kolaya (çok linkli, geniş kanal önce) normal atama
     algoritmasıyla (zone, %70 eşiği, overflow, dolum yönü, süreklilik) yeniden yerleştirilir.
     Kendi rotasının tüm linkleri (Working + Protection + Restoration) kontrol edilir.
  3. Taşıma sırası: hedef frekansı bugünkü ağda boş olan kanal hemen taşınabilir; bir kanal
     taşındıkça boşalttığı spektrum başkasının önünü açar. Döngüsel bağımlılıkta kalanlar
     için geçici frekans gerekir (blokajı yapan kanallar listelenir).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import Ag, Kanal
from .nms import _gridde
from .planlayici import Planlayici


@dataclass
class Birim:
    servis: str
    merkez: float
    genislik: float
    linkler: list[str]
    rota_tipleri: set[str]
    sorunlar: list[str] = field(default_factory=list)
    cakisan: set[tuple] = field(default_factory=set)

    @property
    def anahtar(self):
        return (self.servis, round(self.merkez, 6))


def birimler(ag: Ag) -> dict[tuple, Birim]:
    out: dict[tuple, Birim] = {}
    for lid, ks in ag.kanallar.items():
        for k in ks:
            if k.kaynak != "NMS":
                continue
            key = (k.servis, round(k.merkez, 6))
            b = out.setdefault(key, Birim(k.servis, k.merkez, k.genislik, [], set()))
            if lid not in b.linkler:
                b.linkler.append(lid)
            b.rota_tipleri.add(k.rota_tipi)
    return out


def _cakisma_bul(ag: Ag, bs: dict[tuple, Birim]):
    for b in bs.values():
        b.cakisan = set()
    for lid in ag.linkler:
        for ks in ag.doluluk(lid):
            keys = {(k.servis, round(k.merkez, 6)) for k in ks if k.kaynak == "NMS"}
            if len(keys) > 1:
                for a in keys:
                    bs[a].cakisan |= keys - {a}


def sorunlari_bul(ag: Ag, bs: dict[tuple, Birim]):
    cfg = ag.cfg
    for b in bs.values():
        b.sorunlar = []
        g = int(b.genislik)
        olmali = cfg.zone_genislik(g)
        s0, s1 = cfg.kanal_slotlari(b.merkez, b.genislik)
        z0 = cfg.zone_frekans(cfg.thz(s0) + 1e-4)
        z1 = cfg.zone_frekans(cfg.thz(s1) - 1e-4)
        if z0 != z1:
            b.sorunlar.append(f"ZONE SINIRI ({z0 or 'bant dışı'}/{z1 or 'bant dışı'} arasında)")
        bulundugu = cfg.zone_frekans(b.merkez) or "bant dışı"
        if bulundugu != olmali:
            b.sorunlar.append(f"YANLIŞ ZONE ({bulundugu}'te, {olmali} olmalı)")
        if g in cfg.hizalama and not _gridde(cfg, b.merkez, g):
            b.sorunlar.append(f"GRID DIŞI ({g} GHz gridinde değil)")
    _cakisma_bul(ag, bs)


@dataclass
class TasimaSatiri:
    birim: Birim
    yeni_merkez: float | None
    yeni_zone: str | None
    durum: str
    aciklama: str
    max_kullanim: float | None
    adim: int | None = None
    bagimlilik: str = ""


def yeniden_planla(ag: Ag) -> tuple[list[TasimaSatiri], dict[tuple, Birim]]:
    cfg = ag.cfg
    bs = birimler(ag)
    sorunlari_bul(ag, bs)
    sorunlu = {k for k, b in bs.items() if b.sorunlar}
    # çakışma: uyumsuz taraf zaten taşınıyorsa uyumlu taraf yerinde kalır
    for k, b in bs.items():
        if b.cakisan and not b.sorunlar and all(c not in sorunlu for c in b.cakisan):
            sorunlu.add(k)
    for k, b in bs.items():
        if b.cakisan:
            ad = "; ".join(f"{s}@{m}" for s, m in sorted(b.cakisan))
            b.sorunlar.append(f"ÇAKIŞMA ({ad})" + ("" if k in sorunlu else " — karşı taraf taşınıyor"))

    orijinal = {lid: list(ks) for lid, ks in ag.kanallar.items()}
    # 1) sorunluları çıkar
    for lid in ag.kanallar:
        ag.kanallar[lid] = [k for k in ag.kanallar[lid]
                            if not (k.kaynak == "NMS" and (k.servis, round(k.merkez, 6)) in sorunlu)]
    # 2) zor olandan kolaya yerleştir
    sira = sorted(sorunlu, key=lambda k: (-len(bs[k].linkler), -bs[k].genislik, k))
    pl = Planlayici(ag)
    satirlar: list[TasimaSatiri] = []
    for k in sira:
        b = bs[k]
        s = pl.ata(f"{b.servis}@{b.merkez}", int(b.genislik), b.linkler)
        if s.oneri:
            pl.isle(s)
            ayni = abs(s.oneri.merkez - b.merkez) < 1e-6
            satirlar.append(TasimaSatiri(b, s.oneri.merkez, s.oneri.zone,
                                         "DEĞİŞİKLİK YOK" if ayni else s.durum, s.aciklama,
                                         s.oneri.max_kullanim))
        else:
            satirlar.append(TasimaSatiri(b, None, None, "BLOKE", s.aciklama + " Darboğaz: "
                                         + " | ".join(s.darbogaz), None))
    hedef_ag = {lid: list(ks) for lid, ks in ag.kanallar.items()}

    # 3) taşıma sırası: bugünkü ağdan başlayıp adım adım
    durum = {lid: list(ks) for lid, ks in orijinal.items()}

    def engel(t: TasimaSatiri) -> set[tuple]:
        b = t.birim
        s0, s1 = cfg.kanal_slotlari(t.yeni_merkez, b.genislik)
        eng = set()
        for lid in b.linkler:
            for k in durum[lid]:
                if (k.servis, round(k.merkez, 6)) == b.anahtar:
                    continue
                k0, k1 = cfg.kanal_slotlari(k.merkez, k.genislik)
                if k0 < s1 and s0 < k1:
                    eng.add((k.servis, round(k.merkez, 6)))
        return eng

    bekleyen = [t for t in satirlar if t.yeni_merkez is not None and t.durum != "DEĞİŞİKLİK YOK"]
    adim = 0
    while bekleyen:
        adim += 1
        tasinan = [t for t in bekleyen if not engel(t)]
        if not tasinan:
            break
        for t in tasinan:
            b = t.birim
            t.adim = adim
            for lid in b.linkler:
                durum[lid] = [k for k in durum[lid] if (k.servis, round(k.merkez, 6)) != b.anahtar]
                durum[lid].append(Kanal(b.servis, t.yeni_merkez, b.genislik, "Working", "TASINDI"))
        bekleyen = [t for t in bekleyen if t.adim is None]
    for t in bekleyen:
        t.bagimlilik = "Döngüsel bağımlılık, geçici frekans gerekli. Engelleyen: " + "; ".join(
            f"{s}@{m}" for s, m in sorted(engel(t)))
    for t in satirlar:
        if t.adim and t.adim > 1:
            t.bagimlilik = f"{t.adim - 1}. adımdaki taşımalar spektrumu boşalttıktan sonra"
        elif t.adim == 1:
            t.bagimlilik = "Hedef frekans bugün boş, hemen taşınabilir"
    ag.kanallar = hedef_ag
    return satirlar, bs
