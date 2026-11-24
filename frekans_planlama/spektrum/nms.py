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


def genislik_tahmin(cfg: Config, servis: str, kart_t: str | None, merkez: float) -> tuple[int, str]:
    if servis in cfg.servis_genislik:
        return int(cfg.servis_genislik[servis]), "elle"
    k = cfg.kart_genislik.get(kart_t) if kart_t else None
    if isinstance(k, int):
        return k, f"kart:{kart_t}"
    off = round((merkez - cfg.ref) * 1000, 4)  # GHz, alt kenardan
    if abs((off - 37.5) / 75 - round((off - 37.5) / 75)) < 1e-6:
        return 75, f"grid75:{kart_t or '?'}"
    if abs((off - 25) / 50 - round((off - 25) / 50)) < 1e-6:
        return 50, f"grid50:{kart_t or '?'}"
    return 50, f"varsayilan50:{kart_t or '?'}"


def hiz_bilgisi(cfg: Config, servis: str, genislik: int) -> dict:
    """Servis adındaki hız (ör. '_100G_') ile kanal genişliğinin hız kuralına uyumu."""
    m = re.search(r"(?<!\d)(\d{3})G(?![A-Z])", servis.upper())
    ad_hiz = f"{m.group(1)}G" if m else ""
    hiz = ad_hiz or cfg.hiz_tahmini(genislik)
    kural = cfg.hiz_genislik.get(hiz)
    if not ad_hiz:
        uyum = "hız adda yok (genişlikten tahmin)"
    elif kural is None:
        uyum = f"{hiz} için kural tanımlı değil"
    elif kural == genislik:
        uyum = "uygun"
    else:
        uyum = f"KURAL DIŞI: {hiz} {kural} GHz olmalı, {genislik:g} GHz slotta"
    return dict(Hiz=hiz, HizKaynagi="servis adı" if ad_hiz else "genişlikten", HizGenislikUyumu=uyum)


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
        g, kaynak = genislik_tahmin(cfg, sg.servis, sg.uc_kart, sg.frekans)
        say = sg.rota_tipi in cfg.rota_tipleri
        if say:
            for lid in sg.linkler:
                ag.kanal_ekle(lid, Kanal(sg.servis, sg.frekans, g, sg.rota_tipi))
        servis_satir.append(dict(Servis=sg.servis, RotaTipi=sg.rota_tipi, Yon=sg.yon,
                                 Merkez_THz=sg.frekans, Genislik_GHz=g, **hiz_bilgisi(cfg, sg.servis, g),
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
