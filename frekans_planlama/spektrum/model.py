"""Spektrum modeli: konfigürasyon, slot hesapları, link doluluk tabloları."""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

EPS = 1e-6


def _norm(s: str) -> str:
    """Büyük/küçük harf ve Türkçe karakter farkını yok sayan karşılaştırma anahtarı."""
    s = s.replace("İ", "I").replace("ı", "i")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


@dataclass
class Zone:
    kod: str
    ad: str
    baslangic: float  # THz (kanal kenarı)
    bitis: float
    genislikler: list[int]
    dolum_yonu: str  # "yukari" | "asagi"
    overflow: list[str]
    s0: int = 0  # slot aralığı [s0, s1)
    s1: int = 0

    @property
    def toplam_ghz(self) -> float:
        return round((self.bitis - self.baslangic) * 1000, 3)


@dataclass
class Config:
    alt_kenar: float
    ust_kenar: float
    adim: float  # GHz
    ref: float  # THz
    zonelar: dict[str, Zone]
    esik: float
    esik_ustu_izin: bool
    rota_tipleri: list[str]
    kart_hiz: dict[str, str]
    servis_genislik: dict[str, int]
    hizalama: dict[int, float]
    hiz_genislik: dict[str, int] = field(default_factory=dict)

    @classmethod
    def yukle(cls, yol: str | Path) -> "Config":
        d = yaml.safe_load(Path(yol).read_text(encoding="utf-8"))
        sp = d["spektrum"]
        zonelar = {}
        for kod, z in d["zonelar"].items():
            zonelar[kod] = Zone(kod, z.get("ad", kod), float(z["baslangic"]), float(z["bitis"]),
                                [int(g) for g in z.get("genislikler") or []], z["dolum_yonu"],
                                list(z.get("overflow") or []))
        hiz = {int(k): float(v) for k, v in (d.get("hizalama") or {}).items()}
        c = cls(float(sp["alt_kenar"]), float(sp["ust_kenar"]), float(sp["adim_ghz"]),
                float(sp.get("grid_referans", sp["alt_kenar"])), zonelar,
                float(d.get("kullanim_esigi", 0.7)), bool(d.get("esik_ustu_izin", True)),
                list(d.get("dolulugu_sayilan_rota_tipleri") or ["Working"]),
                {k.upper(): str(v).upper().replace(" ", "") for k, v in (d.get("kart_hiz") or {}).items()},
                dict(d.get("servis_genislik_duzeltme") or {}), hiz,
                {str(k).upper().replace(" ", ""): int(v) for k, v in (d.get("hiz_genislik") or {}).items()})
        for z in c.zonelar.values():
            z.s0, z.s1 = c.slot(z.baslangic), c.slot(z.bitis)
        return c

    # --- slot dönüşümleri -------------------------------------------------
    @property
    def slot_sayisi(self) -> int:
        return self.slot(self.ust_kenar)

    @property
    def s_min(self) -> int:
        return self.slot(self.alt_kenar)

    def slot(self, thz: float) -> int:
        """Bir kenar frekansının slot indeksini döndürür (en yakın tam slota yuvarlar)."""
        return int(round((thz - self.ref) * 1000 / self.adim))

    def thz(self, slot: int) -> float:
        return round(self.ref + slot * self.adim / 1000, 6)

    def kanal_slotlari(self, merkez: float, genislik: float) -> tuple[int, int]:
        """Merkez/genişlikten [s0, s1) slot aralığı (grid dışı kanallar için dışa yuvarlar)."""
        lo = (merkez - genislik / 2000 - self.ref) * 1000 / self.adim
        hi = (merkez + genislik / 2000 - self.ref) * 1000 / self.adim
        return math.floor(lo + EPS), math.ceil(hi - EPS)

    def merkez(self, s0: int, n: int) -> float:
        return round(self.ref + (s0 + n / 2) * self.adim / 1000, 6)

    def hiza(self, genislik: int) -> int:
        """Kanal kenarının oturması gereken slot adımı."""
        g = self.hizalama.get(int(genislik), self.adim)
        return max(1, int(round(g / self.adim)))

    def genislik_coz(self, hiz: str | None = None, genislik=None) -> int:
        """Talepteki hız (100G/200G) veya genişlikten kanal genişliğini belirler."""
        if hiz and str(hiz).strip():
            h = str(hiz).strip().upper().replace(" ", "")
            if not h.endswith("G"):
                h += "G"
            if h not in self.hiz_genislik:
                raise ValueError(f"'{hiz}' hızı için genişlik tanımlı değil "
                                 f"(tanımlı: {', '.join(self.hiz_genislik)}); Genislik_GHz verin")
            g = self.hiz_genislik[h]
            if genislik not in (None, "") and int(float(genislik)) != g:
                raise ValueError(f"{h} için genişlik {g} GHz olmalı, talepte {genislik} verilmiş")
            return g
        if genislik in (None, ""):
            raise ValueError("Hız veya genişlik verilmeli")
        return int(float(genislik))

    def hiz_tahmini(self, genislik) -> str:
        return next((h for h, g in self.hiz_genislik.items() if g == int(genislik)), "")

    def zone_genislik(self, genislik: int) -> str:
        for kod, z in self.zonelar.items():
            if int(genislik) in z.genislikler:
                return kod
        # "ihtiyaca göre" zone (genislik listesi boş olan)
        for kod, z in self.zonelar.items():
            if not z.genislikler:
                return kod
        raise ValueError(f"{genislik} GHz için zone bulunamadı")

    def zone_frekans(self, merkez: float) -> str | None:
        for kod, z in self.zonelar.items():
            if z.baslangic - EPS <= merkez < z.bitis - EPS:
                return kod
        return None


def site_adi(me: str) -> str:
    """'052_FATSA_SLAVE2_ADD DROP_5116' -> '052_FATSA', '053 IKIZDERE MASTER_..' -> '053_IKIZDERE'."""
    n = _norm(me)
    m = re.match(r"^(\d+)[ _]+(.*)$", n)
    if not m:
        return n
    kod, rest = m.groups()
    ad = re.split(r"[ _]", rest, maxsplit=1)[0]
    return f"{kod}_{ad}"


@dataclass
class Link:
    id: str
    a: str  # ME
    b: str
    kartlar: set = field(default_factory=set)

    @property
    def site_a(self) -> str:
        return site_adi(self.a)

    @property
    def site_b(self) -> str:
        return site_adi(self.b)

    @property
    def site_ici(self) -> bool:
        return self.site_a == self.site_b

    @property
    def kisa(self) -> str:
        return f"{self.a}  <->  {self.b}"


@dataclass
class Kanal:
    """Bir linkte bir servisin kapladığı spektrum."""
    servis: str
    merkez: float
    genislik: float
    rota_tipi: str
    kaynak: str = "NMS"  # NMS | PLAN


@dataclass
class Ag:
    cfg: Config
    linkler: dict[str, Link] = field(default_factory=dict)
    kanallar: dict[str, list[Kanal]] = field(default_factory=dict)  # link id -> kanallar
    me_listesi: set[str] = field(default_factory=set)

    def link_ekle(self, me1, k1, me2, k2) -> str:
        """Link = iki ME arasındaki fiber çifti (yönsüz). İleri/geri yön farklı kartlardan
        geçse de aynı link sayılır; kartlar bilgi amaçlı tutulur."""
        a, b = sorted([me1, me2])
        lid = f"{a}  <->  {b}"
        if lid not in self.linkler:
            self.linkler[lid] = Link(lid, a, b)
            self.kanallar[lid] = []
        self.linkler[lid].kartlar.update([f"{me1}:{k1}", f"{me2}:{k2}"])
        self.me_listesi.update([a, b])
        return lid

    def kanal_ekle(self, lid: str, k: Kanal):
        for m in self.kanallar[lid]:
            if m.servis == k.servis and abs(m.merkez - k.merkez) < EPS and m.genislik == k.genislik:
                return
        self.kanallar[lid].append(k)

    def doluluk(self, lid: str) -> list[list[Kanal]]:
        """Slot başına o slotu kullanan kanallar."""
        tab: list[list[Kanal]] = [[] for _ in range(self.cfg.slot_sayisi)]
        for k in self.kanallar.get(lid, []):
            s0, s1 = self.cfg.kanal_slotlari(k.merkez, k.genislik)
            for s in range(max(s0, 0), min(s1, len(tab))):
                tab[s].append(k)
        return tab

    def bos_maske(self, lid: str) -> list[bool]:
        return [not x for x in self.doluluk(lid)]

    def zone_kullanim(self, lid: str, zkod: str, ek: tuple[int, int] | None = None) -> float:
        z = self.cfg.zonelar[zkod]
        dol = self.doluluk(lid)
        dolu = sum(1 for s in range(z.s0, z.s1) if dol[s] or (ek and ek[0] <= s < ek[1]))
        return dolu / (z.s1 - z.s0)

    def parcalanma(self, lid: str, zkod: str) -> tuple[float, float]:
        """(en büyük boş blok GHz, parçalanma oranı 0..1) — 0: boş alan tek parça."""
        z = self.cfg.zonelar[zkod]
        bos = self.bos_maske(lid)
        bloklar, cur = [], 0
        for s in range(z.s0, z.s1):
            if bos[s]:
                cur += 1
            elif cur:
                bloklar.append(cur)
                cur = 0
        if cur:
            bloklar.append(cur)
        top = sum(bloklar)
        if not top:
            return 0.0, 0.0
        return max(bloklar) * self.cfg.adim, round(1 - max(bloklar) / top, 3)
