"""ZTE NMS dışa aktarımlarını (Service Basic Information + Service Route) okur.

Topoloji ayrıca verilmediği için rotalardan çıkarılır: bir rota içinde ME değiştiği her
geçiş (çıkış portunun kartı -> giriş portunun kartı) bir link sayılır. Transponder (OTSi/OCH
uç portu) ile mux arasındaki geçişler servise özel olduğundan link sayılmaz.
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .model import Ag, Config, Kanal

UC_PORT = re.compile(r"/\d{3}\.\d+")  # 'MX2H[2/2]/191.30000_OCH_Bi' gibi uç (transponder) portları
FREKANS = re.compile(r"Frequency:([\d.]+)")


def kart(port: str) -> str:
    """'WSUPA9P9[1/3/0]_OTS_TTP_So:1(OUT1)' -> 'WSUPA9P9[1/3/0]'"""
    return port.split("_", 1)[0]


def kart_tipi(port: str) -> str:
    """'MQ4H/D[1/2]/191.31250/...' -> 'MQ4H/D'"""
    return port.split("[", 1)[0].strip().upper()


def _oku(yol: Path) -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if yol.suffix.lower() == ".csv":
            return pd.read_csv(yol, dtype=str).fillna("--")
        return pd.read_excel(yol, dtype=str).fillna("--")


@dataclass
class RotaSegmenti:
    servis: str
    rota_tipi: str
    yon: str
    frekans: float | None
    uc_kart: str | None
    linkler: list[str] = field(default_factory=list)


def _gridde(cfg: Config, merkez: float, genislik: int) -> bool:
    """Merkez, o genişliğin standart gridinde mi? (kenarlar 191.275 + k*genişlik)"""
    off = (merkez - cfg.ref) * 1000 - genislik / 2
    return abs(off / genislik - round(off / genislik)) < 1e-6


def genislik_tahmin(cfg: Config, servis: str, kart_t: str | None, merkez: float) -> tuple[int, str, str]:
    """(genişlik GHz, kaynak, hız)"""
    if servis in cfg.servis_genislik:
        g = int(cfg.servis_genislik[servis])
        return g, "elle", cfg.hiz_tahmini(g)
    hiz = cfg.kart_hiz.get(kart_t) if kart_t else None
    if hiz and hiz in cfg.hiz_genislik:
        return cfg.hiz_genislik[hiz], f"kart:{kart_t}", hiz
    for g in (75, 50):
        if _gridde(cfg, merkez, g):
            return g, f"grid{g}:{kart_t or '?'}", cfg.hiz_tahmini(g)
    return 50, f"varsayilan50:{kart_t or '?'}", cfg.hiz_tahmini(50)


def grid_uyumu(cfg: Config, merkez: float, genislik: int) -> str:
    if genislik not in cfg.hizalama:
        return "-"
    return "uygun" if _gridde(cfg, merkez, genislik) else f"GRID DIŞI ({genislik:g} GHz gridine oturmuyor)"


def rotalari_ayristir(df: pd.DataFrame) -> list[RotaSegmenti]:
    """Service Route tablosunu (servis, rota tipi, yön, frekans) segmentlerine böler."""
    seg: list[RotaSegmenti] = []
    satirlar: list[list[tuple[str, str]]] = []
    onceki = None
    for r in df.itertuples(index=False):
        lab, rt, me, port, fr, yon = r[0], r[1], r[2], r[3], r[4], r[6]
        f = None if fr in ("--", "", None) else float(fr)
        anahtar = (lab, rt, yon)
        yeni = onceki is None or anahtar != onceki[0] or (f is not None and onceki[1] is not None
                                                          and abs(f - onceki[1]) > 1e-6)
        if yeni:
            uc = kart_tipi(port) if UC_PORT.search(port) else None
            seg.append(RotaSegmenti(lab, rt, yon, f, uc))
            satirlar.append([])
            onceki = [anahtar, f]
        elif f is not None and onceki[1] is None:
            onceki[1] = f
            seg[-1].frekans = f
        satirlar[-1].append((me, port))
    return seg, satirlar


def ag_kur(cfg: Config, info_yol: Path | None, rota_yol: Path) -> tuple[Ag, pd.DataFrame, list[str]]:
    uyarilar: list[str] = []
    ag = Ag(cfg)
    rota = _oku(Path(rota_yol))
    rota.columns = [c.strip() for c in rota.columns]
    beklenen = ["User Label", "Route Type", "ME Name", "Port Name", "Frequency(THz)", "Time Slot", "Path"]
    eksik = [c for c in beklenen if c not in rota.columns]
    if eksik:
        raise ValueError(f"Route dosyasında eksik sütun(lar): {eksik}")
    rota = rota[beklenen]
    segler, satirlar = rotalari_ayristir(rota)

    servis_satir = []
    for sg, rows in zip(segler, satirlar):
        for (me1, p1), (me2, p2) in zip(rows, rows[1:]):
            if me1 == me2 or UC_PORT.search(p1) or UC_PORT.search(p2):
                continue
            sg.linkler.append(ag.link_ekle(me1, kart(p1), me2, kart(p2)))
        if sg.frekans is None:
            uyarilar.append(f"{sg.servis} ({sg.rota_tipi}/{sg.yon}): frekans bulunamadı, atlandı")
            continue
        g, kaynak, hiz = genislik_tahmin(cfg, sg.servis, sg.uc_kart, sg.frekans)
        say = sg.rota_tipi in cfg.rota_tipleri
        if say:
            for lid in sg.linkler:
                ag.kanal_ekle(lid, Kanal(sg.servis, sg.frekans, g, sg.rota_tipi))
        servis_satir.append(dict(Servis=sg.servis, RotaTipi=sg.rota_tipi, Yon=sg.yon,
                                 Merkez_THz=sg.frekans, Hiz=hiz, Genislik_GHz=g,
                                 GridUyumu=grid_uyumu(cfg, sg.frekans, g),
                                 GenislikKaynagi=kaynak,
                                 Zone=cfg.zone_frekans(sg.frekans) or "BANT DIŞI",
                                 BeklenenZone=cfg.zone_genislik(g), LinkSayisi=len(sg.linkler),
                                 DolulugaSayildi=say))
    servisler = pd.DataFrame(servis_satir)
    if len(servisler):
        servisler = (servisler[servisler.Yon == "Forward"] if (servisler.Yon == "Forward").any() else servisler)
        servisler = servisler.drop(columns=["Yon"]).drop_duplicates(["Servis", "RotaTipi", "Merkez_THz"])

    if info_yol:
        info = _oku(Path(info_yol))
        if "User Label" in info.columns and len(servisler):
            ek = info[["User Label"] + [c for c in ["A End", "Z End", "Run Status", "Service Level",
                                                    "Switch State"] if c in info.columns]].copy()
            ek["Merkez_THz"] = ek["A End"].str.extract(FREKANS)[0].astype(float)
            servisler = servisler.merge(ek.rename(columns={"User Label": "Servis"}),
                                        on=["Servis", "Merkez_THz"], how="left")
            rotasiz = set(info["User Label"]) - set(servisler["Servis"])
            for s in sorted(rotasiz):
                uyarilar.append(f"{s}: Service Info'da var, Route dosyasında rotası yok")
    return ag, servisler, uyarilar


def rota_dosyasindan_linkler(ag: Ag, yol: Path, servis: str | None = None) -> dict[str, list[str]]:
    """NMS Route formatındaki bir dosyadan (frekanssız olabilir) servis -> link listesi."""
    df = _oku(Path(yol))
    df = df[["User Label", "Route Type", "ME Name", "Port Name", "Frequency(THz)", "Time Slot", "Path"]]
    segler, satirlar = rotalari_ayristir(df)
    out: dict[str, list[str]] = {}
    for sg, rows in zip(segler, satirlar):
        if servis and sg.servis != servis:
            continue
        if sg.rota_tipi not in ("Working", "--"):
            continue
        for (me1, p1), (me2, p2) in zip(rows, rows[1:]):
            if me1 == me2 or UC_PORT.search(p1) or UC_PORT.search(p2):
                continue
            lid = ag.link_ekle(me1, kart(p1), me2, kart(p2))
            lst = out.setdefault(sg.servis, [])
            if lid not in lst:
                lst.append(lid)
    return out
