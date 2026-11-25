# Oyunlar

Tarayıcıda oynanan, kurulum gerektirmeyen oyunlar. Ana sayfa (`index.html`) iki oyuna da bağlantı verir.

Adres (GitHub Pages açıkken): https://akbuluterhan.github.io/For_Claude/

## Demir Kafa

`demirkafa/index.html` tek dosyadır. Yan kaydırmalı aksiyon platform oyunu. Baretli inşaat işçisi Demir Kafa, deli bilimci Dr. Balçık'ın yeşil mutantlarını temizliyor.

- **3 bölüm:** Gökdelen Çatıları, Metro Tünelleri, Balçık Fabrikası (sonunda boss dövüşü)
- **3 silah:** Perçin tabancası (sınırsız), Çivi saçar (pompalı tüfek gibi), Kaynak ışını (düşmanları deler)
- Kart anahtarını bul, çıkış kapısına ulaş. Kontrol noktaları, kırılabilir kasalar, patlayan variller var.
- Kafesteki kedileri kurtar (+500). 100 cıvata = +1 can. Düşmanların üstüne zıplayıp ezebilirsin.

**Klavye:** ← → / A D yürü · Boşluk / ↑ zıpla · X / J ateş · C / Q silah değiştir · ↓ + zıpla platformdan in · P duraklat · M ses

**Telefon:** Ekrandaki tuşlar. Yatay tutmak daha rahat.

## Vırak

Android telefonda (tarayıcıda) oynanan kurbağa oyunu. `virak/index.html` tek dosyadır.

- Ekrana dokun: kurbağa dilini oraya fırlatır. Sinek, güve, yusufçuk yakala.
- Ateş böceği (sarı, parlayan): 50 puan ve +1 can.
- Sarı-siyah arıyı yeme: can kaybedersin.
- Kırmızı eşek arısı bir nilüferin üstünde uyarı verip dalar. Başka nilüfere dokunarak zıpla ve kaç.
- Açlık çubuğu boşalırsa can gider. Arka arkaya yakaladıkça çarpan artar (en fazla x5).

## Telefonda açmak

Android'de Chrome ile aç, sağ üstteki menüden **Ana ekrana ekle** de. Oyun ikonuyla ana ekrana gelir ve tam ekran açılır.

**GitHub Pages'i açmak (bir kere):** Depo → Settings → Pages → Source: "Deploy from a branch", Branch: `main`, klasör: `/ (root)` → Save. Bir iki dakika içinde adres çalışır.

## Google Play Store

`android/` klasörü oyunu çevrimdışı, tam ekran çalışan bir Android uygulamasına sarar (paket adı `io.github.akbuluterhan.virak`).
GitHub Actions her gönderimde paketi derler: **Actions → Android paketi → son çalışma → Artifacts** altında `virak-N` zip'i iner. İçinde:

- `virak-N.aab`: Play Console'a yüklenecek paket.
- `virak-N.apk`: Telefona doğrudan kurup denemek için.

**Play için imza:** Depoda Settings → Secrets and variables → Actions → New repository secret ile iki secret ekle:
`VIRAK_KEYSTORE_BASE64` ve `VIRAK_KEYSTORE_PASSWORD`. Bunlar yoksa paket debug anahtarıyla imzalanır; telefonda çalışır ama Play kabul etmez.

**Mağaza için hazır dosyalar:** `play-store/` (512 simge, 1024x500 tanıtım görseli, 3 ekran görüntüsü).
Gizlilik politikası: https://akbuluterhan.github.io/For_Claude/gizlilik.html
