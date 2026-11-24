# DWDM Frekans Planlama Aracı

Bu araç ZTE NMS export'larından (Service Basic Information + Service Route) mevcut spektrum
doluluğunu çıkarır. Her yeni servis talebinde, verilen rota ve kanal genişliğiyle zone kurallarına
uygun bir merkez frekans önerir.

## Kurulum
```bash
pip install pandas openpyxl pyyaml
```

## Veri
`veri/` klasörüne NMS export'larını koyun (bu dosyalar git'e eklenmez):

| Dosya | İçerik |
|---|---|
| `veri/ServiceInfo.xlsx` | Service → Basic Information export'u |
| `veri/ServiceRoute.xlsx` | Service Route export'u (User Label, Route Type, ME Name, Port Name, Frequency(THz), Time Slot, Path, ...) |

Topoloji ayrıca verilmez, rotalardan çıkarılır. Rota içinde ME değiştiği her geçiş bir link
sayılır (iki ME arası fiber çifti). Transponder ile mux arasındaki geçişler link sayılmaz.

## Komutlar
```bash
python plan.py analiz                    # mevcut durum -> cikti/analiz.xlsx
python plan.py ara KAVAK                 # ME / link adı ara
python plan.py ata -g 75 -t TALEP-001 -r "055_ILKADIM_MASTER_5001 > 055_KAVAK_MASTER_ILKADIM/ASARCIK YONU_5040"
python plan.py ata -g 50 -r "RIZE > KALKANDERE > IKIZDERE" --kaydet
python plan.py sablon                    # talep_sablonu.xlsx üretir
python plan.py toplu talepler.xlsx       # tüm talepleri sırayla planlar -> cikti/talep_sonuclari_*.xlsx
python plan.py planlananlar [--sil TALEP-001]
```

### Rota yazımı
Düğümler `>` (veya `;`) ile ayrılır. Her düğüm şunlardan biri olabilir:
- tam ME adı: `052_FATSA_MASTER_ORDU YONU_5114`
- ME adının benzersiz bir parçası: `FATSA_MASTER`
- site adı: `FATSA` veya `052_FATSA`

Ardışık iki düğüm arasında doğrudan link yoksa, aynı sitelerin ME'leri üzerinden geçen yol otomatik
bulunur (SLAVE → MASTER gibi site içi geçişleri yazmak gerekmez). Uçlarda add/drop ME'sinin tam
adını yazarsanız site içi linkler de kontrol edilir.

Rota yerine NMS Route formatında bir dosya da verilebilir: `--rota-dosyasi rota.xlsx`.

### Kayıt (`--kaydet`)
Onaylanan atamalar `veri/planlanan.csv`'ye yazılır ve sonraki talepler bu atamaları dolu görür.
NMS'ten yeni export alındığında, NMS'te aynı User Label ile görünen talepler bu listeden otomatik
düşülür. Bu yüzden NMS'te servisi talep adıyla açın.

`toplu` komutu talepleri sırayla işler; her atama bir sonraki talep için dolu sayılır.

## Atama kuralları (`config.yaml`)

| Zone | Aralık (kanal kenarı) | Toplam | Kanal | Dolum yönü | Overflow |
|---|---|---|---|---|---|
| Z1 | 191.275 – 192.275 | 1000 GHz | 50 GHz | ↑ yukarı | Z2 |
| Z2 | 192.275 – 193.475 | 1200 GHz | 75 GHz | ↓ aşağı | Z1 |
| Z3 | 193.475 – 195.475 | 2000 GHz | 100/150 GHz | ↑ yukarı | Z4 (tek yön) |
| Z4 | 195.475 – 196.075 | 600 GHz | ihtiyaca göre | ↓ aşağı | – |

Kural tablosundaki 191.3 / 192.3 / 193.5 / 195.5 / 196.1 değerleri ITU kanal merkezi
gösterimidir. Spektrum kenarı olarak 25 GHz aşağı kaydırıldı: 191.3 THz merkezli 50 GHz kanal
191.275'ten başlar ve mevcut 75 GHz grid de 191.275'e oturuyor. Farklıysa `config.yaml`'da
değiştirilebilir.

Algoritma:
1. Zone genişlikten belirlenir: 50 → Z1, 75 → Z2, 100/150 → Z3, diğer → Z4. `-z` ile elle de verilebilir.
2. Rotadaki **tüm linklerde** aynı anda boş olan (frekans sürekliliği), **bitişik** slotlardan
   oluşan konumlar bulunur (12.5 GHz flexgrid). 50/75 GHz kanallar mevcut ağdaki 50/75 GHz gridine hizalanır.
3. Konumlar zone'un dolum yönünde first-fit sıralanır. Spektrum zone sınırından içeri doğru sıkı
   paketlenir ve büyük boş bloklar korunur (parçalanma azalır).
4. Öncelik:
   - **UYGUN**: kendi zone'u, rotadaki her linkte zone kullanımı ≤ %70
   - **OVERFLOW**: overflow zone'u ≤ %70. Ana zone'un yönünde sınırdan devam eder:
     Z1 → Z2'nin alt kenarından yukarı, Z2 → Z1'in üst kenarından aşağı, Z3 → Z4'ün alt kenarından yukarı.
   - **ESIK_USTU**: kendi zone'u > %70 (uyarı ile; `esik_ustu_izin: false` ile kapatılabilir)
   - **OVERFLOW_ESIK_USTU**: overflow zone'u > %70
   - **BLOKE**: uygun yer yok. Rotadan çıkarıldığında atamayı mümkün kılan linkler **darboğaz** olarak listelenir.

### Kanal genişliği çıkarımı (mevcut servisler)
NMS'te kanal genişliği yok. Kart tipine göre belirleniyor:
- `MX2H`, `MXB2P` → 50 GHz
- `MQ4H/D`, `MDB2` → merkez frekansın grid uyumundan: 75 GHz grid merkezi (191.3125 + 0.075k) ise
  75 GHz, 50 GHz ITU gridinde ise 50 GHz. Bu kartlar mevcut ağda her iki modda da kullanılıyor.

Bu yöntemle mevcut ağda hiç çakışma oluşmuyor. Yanlış olan bir servis varsa
`servis_genislik_duzeltme` ile elle düzeltilebilir.

## Analiz raporu (`cikti/analiz.xlsx`)
- **Ozet**: zone başına ortalama ve en yüksek link kullanımı, eşiği aşan link sayısı
- **Link_Kullanim**: her link için zone kullanımları, en büyük boş blok, parçalanma oranı
- **Servisler**: her servisin merkez frekansı, genişliği, bulunduğu ve olması gereken zone
- **Cakismalar**: aynı linkte örtüşen kanallar
- **Spektrum_Haritasi**: link × 12.5 GHz slot renkli harita (koyu: dolu, açık: boş, kırmızı: çakışma, mor: planlanan)
