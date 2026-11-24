"""Yeni servis için frekans atama.

Adımlar:
  1. Genişlikten servisin zone'u belirlenir (50->Z1, 75->Z2, 100/150->Z3, diğer->Z4).
  2. Rotadaki TÜM linklerde aynı anda boş olan (süreklilik) ve bitişik slotlardan oluşan
     (contiguity) konumlar bulunur.
  3. Aday konumlar, zone'un dolum yönüne göre first-fit sıralanır: Z1/Z3 aşağıdan yukarı,
     Z2/Z4 yukarıdan aşağı. Böylece spektrum sıkı paketlenir, büyük boş bloklar korunur.
  4. Öncelik sırası:
       a) Kendi zone'u, rotadaki her linkte kullanım eşiği (%70) aşılmadan
       b) Overflow zone'u, eşik aşılmadan. Kendi zone'unun dolum yönünde devam eder:
          Z1->Z2 alt kenarından yukarı, Z2->Z1 üst kenarından aşağı, Z3->Z4 alt kenarından yukarı.
       c) (izin varsa) kendi zone'u, eşik üstü — UYARI
       d) (izin varsa) overflow zone'u, eşik üstü — UYARI
  5. Hiçbiri yoksa BLOKE: darboğaz linkler raporlanır.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import Ag, Kanal


@dataclass
class Aday:
    merkez: float
    genislik: int
    zone: str
    s0: int
    n: int
    seviye: str  # UYGUN | OVERFLOW | ESIK_USTU | OVERFLOW_ESIK_USTU
    max_kullanim: float  # atama sonrası rotadaki en yüksek zone kullanımı
    link_kullanim: dict[str, float] = field(default_factory=dict)

    @property
    def alt(self) -> float:
        return round(self.merkez - self.genislik / 2000, 6)

    @property
    def ust(self) -> float:
        return round(self.merkez + self.genislik / 2000, 6)


@dataclass
class Sonuc:
    talep: str
    genislik: int
    ana_zone: str
    linkler: list[str]
    oneri: Aday | None
    alternatifler: list[Aday]
    durum: str
    aciklama: str
    darbogaz: list[str] = field(default_factory=list)
    uyarilar: list[str] = field(default_factory=list)
    hiz: str = ""


SEVIYE_ACIKLAMA = {
    "UYGUN": "Kendi zone'unda, %{e} eşiği altında",
    "OVERFLOW": "Kendi zone'u rotada %{e} eşiğine ulaştığı için overflow zone'una ({z}) yerleşti",
    "ESIK_USTU": "Kendi zone'unda ama %{e} eşiği ÜSTÜNDE (uygun eşik-altı yer yok)",
    "OVERFLOW_ESIK_USTU": "Overflow zone'unda ({z}) ve %{e} eşiği ÜSTÜNDE",
}


class Planlayici:
    def __init__(self, ag: Ag):
        self.ag = ag
        self.cfg = ag.cfg

    def _ortak_bos(self, linkler: list[str]) -> list[bool]:
        bos = [True] * self.cfg.slot_sayisi
        for lid in linkler:
            for i, b in enumerate(self.ag.bos_maske(lid)):
                if not b:
                    bos[i] = False
        return bos

    def _konumlar(self, bos: list[bool], bolge: str, n: int, yon: str, hiza: int) -> list[int]:
        z = self.cfg.zonelar[bolge]
        konum = []
        for s in range(z.s0, z.s1 - n + 1):
            if (s - self.cfg.s_min) % hiza:
                continue
            if all(bos[s:s + n]):
                konum.append(s)
        return konum if yon == "yukari" else list(reversed(konum))

    def _kullanim(self, linkler, bolge, s0, n) -> dict[str, float]:
        return {lid: self.ag.zone_kullanim(lid, bolge, (s0, s0 + n)) for lid in linkler}

    def ata(self, talep: str, genislik: int, linkler: list[str], zone: str | None = None,
            alternatif_sayisi: int = 5) -> Sonuc:
        cfg = self.cfg
        genislik = int(genislik)
        if genislik % cfg.adim:
            raise ValueError(f"Genişlik {cfg.adim} GHz'in katı olmalı")
        n = int(genislik // cfg.adim)
        ana = zone or cfg.zone_genislik(genislik)
        z = cfg.zonelar[ana]
        hiza = cfg.hiza(genislik)
        bos = self._ortak_bos(linkler)
        e = int(round(cfg.esik * 100))

        adaylar: list[Aday] = []
        planlar = [(ana, "UYGUN", False)] + [(o, "OVERFLOW", False) for o in z.overflow]
        if cfg.esik_ustu_izin:
            planlar += [(ana, "ESIK_USTU", True)] + [(o, "OVERFLOW_ESIK_USTU", True) for o in z.overflow]
        gorulen = set()
        for bolge, seviye, esik_ustu in planlar:
            # overflow bölgesinde de ana zone'un dolum yönü sürdürülür (sınırdan devam)
            for s in self._konumlar(bos, bolge, n, z.dolum_yonu, hiza):
                # alternatifler birbiriyle örtüşmesin (12.5 GHz kaydırılmış kopyalar anlamsız)
                if any(s < g + n and g < s + n for g in gorulen):
                    continue
                kul = self._kullanim(linkler, bolge, s, n)
                mx = max(kul.values(), default=0.0)
                if not esik_ustu and mx > cfg.esik + 1e-9:
                    continue
                gorulen.add(s)
                adaylar.append(Aday(cfg.merkez(s, n), genislik, bolge, s, n, seviye, mx, kul))
                if len(adaylar) > alternatif_sayisi:
                    break
            if len(adaylar) > alternatif_sayisi:
                break

        uyarilar = []
        if not linkler:
            uyarilar.append("Rota hiçbir mevcut linke eşlenemedi — doluluk kontrolü yapılamadı!")
        if not adaylar:
            darbogaz = self._darbogaz(linkler, ana, n, hiza)
            return Sonuc(talep, genislik, ana, linkler, None, [], "BLOKE",
                         f"Rotada {genislik} GHz bitişik ve uçtan uca ortak boş spektrum yok "
                         f"({ana} ve overflow zone'larında).", darbogaz, uyarilar)
        o = adaylar[0]
        acik = SEVIYE_ACIKLAMA[o.seviye].format(e=e, z=o.zone)
        return Sonuc(talep, genislik, ana, linkler, o, adaylar[1:], o.seviye, acik, [], uyarilar)

    def _darbogaz(self, linkler, ana, n, hiza) -> list[str]:
        """Rotadan çıkarıldığında atamayı mümkün kılan linkler = darboğaz."""
        z = self.cfg.zonelar[ana]
        bolgeler = [ana] + z.overflow
        sonuc = []
        for lid in linkler:
            diger = [x for x in linkler if x != lid]
            bos = self._ortak_bos(diger)
            if any(self._konumlar(bos, b, n, z.dolum_yonu, hiza) for b in bolgeler):
                sonuc.append(lid)
        return sonuc

    def isle(self, sonuc: Sonuc, aday: Aday | None = None):
        """Atamayı ağ modeline işler (sonraki talepler bunu görür)."""
        a = aday or sonuc.oneri
        if not a:
            return
        for lid in sonuc.linkler:
            self.ag.kanal_ekle(lid, Kanal(sonuc.talep, a.merkez, a.genislik, "Working", "PLAN"))
