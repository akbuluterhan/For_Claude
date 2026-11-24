"""Kullanıcının yazdığı rota metnini (ME veya site adları) topolojideki linklere çevirir.

Rota yazımı: düğümler '>' veya ';' veya satır sonu ile ayrılır. Her düğüm:
  * tam ME adı            : 052_FATSA_MASTER_ORDU YONU_5114
  * ME adının benzersiz bir parçası : FATSA_MASTER
  * site adı              : FATSA  veya  052_FATSA
Ardışık iki düğüm arasında doğrudan link yoksa, aynı sitelerdeki ME'ler üzerinden
en kısa yol aranır (ör. SLAVE -> MASTER site içi geçişleri yazmak zorunlu değil).
"""
from __future__ import annotations

import re
from collections import deque

from .model import Ag, _norm, site_adi


class RotaHatasi(ValueError):
    pass


class RotaCozucu:
    def __init__(self, ag: Ag):
        self.ag = ag
        self.komsu: dict[str, list[tuple[str, str]]] = {}
        for lid, l in ag.linkler.items():
            self.komsu.setdefault(l.a, []).append((l.b, lid))
            self.komsu.setdefault(l.b, []).append((l.a, lid))
        self.me_norm = {_norm(m): m for m in ag.me_listesi}
        self.siteler: dict[str, set[str]] = {}
        for m in ag.me_listesi:
            self.siteler.setdefault(site_adi(m), set()).add(m)

    def dugum(self, metin: str) -> set[str]:
        t = _norm(metin)
        if t in self.me_norm:
            return {self.me_norm[t]}
        site = [s for s in self.siteler if s == t or s.split("_", 1)[-1] == t]
        if len(site) == 1:
            return set(self.siteler[site[0]])
        if len(site) > 1:
            raise RotaHatasi(f"'{metin}' birden çok siteye uyuyor: {', '.join(site)}")
        aday = [orj for n, orj in self.me_norm.items() if t in n]
        if len(aday) == 1:
            return {aday[0]}
        if not aday:
            raise RotaHatasi(f"'{metin}' hiçbir ME/site ile eşleşmedi")
        raise RotaHatasi(f"'{metin}' birden çok ME ile eşleşti: " + "; ".join(sorted(aday)[:8]))

    def _yol(self, kaynak: set[str], hedef: set[str]) -> list[str] | None:
        """kaynak -> hedef en kısa yol; ara düğümler yalnızca kaynak/hedef sitelerinden olabilir."""
        izin = {site_adi(m) for m in kaynak | hedef}
        q = deque((m, []) for m in kaynak)
        gor = set(kaynak)
        while q:
            m, yol = q.popleft()
            if m in hedef and yol:
                return yol
            for k, lid in self.komsu.get(m, []):
                if k in gor or site_adi(k) not in izin:
                    continue
                gor.add(k)
                q.append((k, yol + [lid]))
        return None

    def coz(self, rota: str) -> tuple[list[str], list[str]]:
        parcalar = [p.strip() for p in re.split(r"[>;\n]|->", rota) if p.strip()]
        if len(parcalar) < 2:
            raise RotaHatasi("Rota en az iki düğüm içermeli (A > ... > Z)")
        dugumler = [self.dugum(p) for p in parcalar]
        linkler: list[str] = []
        uyari: list[str] = []
        for (p1, d1), (p2, d2) in zip(zip(parcalar, dugumler), zip(parcalar[1:], dugumler[1:])):
            dogrudan = sorted({lid for m in d1 for k, lid in self.komsu.get(m, []) if k in d2})
            if len(dogrudan) == 1:
                yol = dogrudan
            elif len(dogrudan) > 1:
                yol = dogrudan
                uyari.append(f"'{p1}' - '{p2}' arasında {len(dogrudan)} paralel link var; "
                             "hepsi kontrol edildi (kesin sonuç için ME adı yazın)")
            else:
                yol = self._yol(d1, d2)
                if yol is None:
                    raise RotaHatasi(f"'{p1}' ile '{p2}' arasında topolojide bağlantı bulunamadı")
            for lid in yol:
                if lid not in linkler:
                    linkler.append(lid)
        if any(len(d) > 1 for d in (dugumler[0], dugumler[-1])):
            uyari.append("Uç noktalar site olarak verildi: add/drop ME'si içindeki site-içi linkler "
                         "kesinleşmedi. Kesin sonuç için uçlarda ME adı yazın.")
        return linkler, uyari
