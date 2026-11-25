# Vırak

Android telefonda (tarayıcıda) oynanan kurbağa oyunu. `virak/index.html` tek dosyadır, kurulum gerektirmez.

**Oynanış**
- Ekrana dokun: kurbağa dilini oraya fırlatır. Sinek, güve, yusufçuk yakala.
- Ateş böceği (sarı, parlayan): 50 puan ve +1 can.
- Sarı-siyah arıyı yeme: can kaybedersin.
- Kırmızı eşek arısı bir nilüferin üstünde uyarı verip dalar. Başka nilüfere dokunarak zıpla ve kaç.
- Açlık çubuğu boşalırsa can gider. Arka arkaya yakaladıkça çarpan artar (en fazla x5).

**Telefonda açmak:** GitHub Pages açıldıktan sonra oyun şu adreste: https://akbuluterhan.github.io/For_Claude/

Android'de Chrome ile aç, sağ üstteki menüden **Ana ekrana ekle** de. Oyun ikonuyla ana ekrana gelir ve tam ekran açılır.

**GitHub Pages'i açmak (bir kere):** Depo → Settings → Pages → Source: "Deploy from a branch", Branch: `main`, klasör: `/ (root)` → Save. Bir iki dakika içinde adres çalışır.

---

# Saha İlerleme Takibi

`takip/index.html`: DWDM saha kurulumları (Faz-1, Faz-2, Faz-1-2, Faz-3) için ilerleme takip aracı. Tek dosya, kurulum gerektirmez.

**Adres:** https://akbuluterhan.github.io/For_Claude/takip/

- **Excel yükle:** Faz-1-2 ve Faz-3 Excel dosyalarını seç (ikisi birden olabilir). Dosyalar sadece tarayıcıda işlenir, hiçbir yere gönderilmez; veri bu tarayıcının belleğinde durur.
- Güncel Excel'i tekrar yüklediğinde hangi sahada hangi aşamanın ilerlediği geçmişe yazılır. Elle girilen notlar ve engel işaretleri korunur.
- **Özet:** saha sayıları, aşama bazında tamamlanma, bölgelere göre durum, geciken ve yaklaşan işler.
- **Sahalar:** filtrelenebilir liste. Bir sahaya tıklayınca aşamalarını (durum, plan tarihi, gerçekleşen tarih), notunu ve engel durumunu güncelleyebilirsin.
- **Plan & gecikmeler:** geciken, bu hafta ve sonraki 30 gün içinde planlı işler; planı girilmemiş sahalar.
- **Excel'e aktar:** güncel durumu Excel olarak indirir. **Yedek al / Yedek yükle:** notlar ve geçmiş dahil tüm veriyi başka cihaza taşımak için.
