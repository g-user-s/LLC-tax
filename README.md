# LLC-tax — Form 5472 + Pro Forma 1120 hazırlayıcı

**New Mexico'da kurulu, tek üyeli, sahibi ABD dışında yaşayan ve geliri App Store / Google Play
kaynaklı** LLC'ler için yıllık **Form 5472** ve **Pro Forma Form 1120**'yi hazırlayan yerel uygulama.

- Grafik arayüz tarayıcıda açılır ama sunucu yalnızca `127.0.0.1` üzerinde çalışır; **hiçbir veri dışarı gönderilmez**.
- Girilen veriler `data/`, üretilen formlar `output/` klasöründe kalır (ikisi de `.gitignore`'da).

> Bu araç bir hazırlama yardımcısıdır, vergi danışmanlığı değildir. Göndermeden önce her alanı kontrol edin.

## Kurulum ve çalıştırma

```bash
pip install -r requirements.txt
python3 app.py
```

Tarayıcıda 6 adımlı sihirbaz açılır:

1. **Uygunluk** — koşulların tamamı sağlanmazsa devam edilemez.
2. **Şirket** — LLC adı, EIN, adres, kuruluş tarihi, yıl başı/sonu banka bakiyesi.
3. **Ortak** — ad, adres, FTIN, Reference ID, ülkeler.
4. **İşlemler** — elle giriş ve/veya **Mercury CSV** içe aktarma (kategori tahmini, tekrar eden kayıt atlama; emin olunamayanlar sarı işaretlenir).
5. **Kontrol** — hatalar, uyarılar, formlara yazılacak tüm değerler.
6. **Formlar** — doldurulmuş resmi PDF'ler: pro forma 1120, Form 5472, Part V eki ve hepsini birleştiren faks paketi.

Önceki yılın şirket/ortak bilgileri yeni yıla otomatik taşınır.

### Gerekli IRS PDF'leri (`forms/`)

| Dosya | Durum |
|---|---|
| `forms/f5472.pdf` (Rev. 12-2023) | Repoda mevcut |
| `forms/f1120.pdf` (2025) | Repoda mevcut. Her yeni vergi yılı için o yılın Form 1120'si ile değiştirilmeli; araç yıl uyuşmazlığını yakalar. |

## Yapı

| Dosya | Görev |
|---|---|
| `app.py` | Grafik arayüzü başlatır |
| `llc_tax/engine.py` | Doğrulama + hesaplama (satır eşleştirmeleri) |
| `llc_tax/mercury.py` | Mercury CSV içe aktarıcı |
| `llc_tax/pdf_fill.py` | Resmi PDF'leri doldurur, Part V ekini üretir |
| `llc_tax/server.py`, `llc_tax/static/` | Yerel arayüz |
| `generator.py` | Komut satırı sürümü (`config.json` + `transactions.csv`, `--pdf`) |

## Kategoriler

- `amount_usd` her zaman pozitif; yönü kategori belirler. Döviz işlemleri USD'ye çevrilmiş girilir.
- `paid_by`: `llc` (LLC banka hesabı) veya `owner` (ortak kendi cebinden).

| Kategori | paid_by | LLC nakdi | Form 5472 |
|---|---|---|---|
| `revenue` (App Store / Google Play) | llc | + | — (üçüncü taraf) |
| `software_expense`, `bank_fee`, `other_expense` | llc | − | — (üçüncü taraf) |
| aynı giderler | **owner** | etkisiz | Part V (ortak katkısı) |
| `capital_contribution` | owner | + | Part V |
| `owner_draw` | llc | − | Part V |
| `loan_from_owner` / `loan_repayment_to_owner` | owner / llc | + / − | Part IV 17a/17b (bakiye) |
| `loan_to_owner` / `loan_repayment_from_owner` | llc / owner | − / + | Part IV 31a/31b (bakiye) |
| `interest_paid_to_owner` | llc | − | Part IV 32 |

## Hesaplama kuralları

Satır numaraları **Form 5472 Rev. 12-2023** ve **Instructions Rev. 12-2024** esas alınır.

- **Sermaye / çekim yalnızca Part V'e** girer. Part IV satır 21/35 sadece vergilendirilebilir
  geliri etkileyen tutarlar içindir (Reg. §1.6038A-2(b)(3)(x)); DE'nin katkı ve dağıtımları
  ayrıca (b)(3)(xi) ve Part V kapsamındadır.
- **Toplam varlık** (1120 D → 5472 1c) = açılış nakdi + LLC hesabından geçen net hareketler.
  Varsayım: LLC'nin nakit dışında varlığı yok.
- **22 / 36** = Part IV toplamları (borçlarda yalnızca 17b / 31b dahil).
- **1f / 1h** = satır 22 + 36 + Part V tutarları (DE için talimat Part V'i de sayar). Tek ortak → 1g = 1.
- **Part II** DE'de de doldurulur (sahip = direct 25% foreign shareholder). FTIN yoksa "None".
- **Reference ID**: ortağın SSN/ITIN'i yoksa zorunlu; harf/rakam, ≤50 karakter, her yıl aynı.
- Yabancı ülke adları kısaltılmaz ("TR" değil "Turkey").
- **Part VII** herkes doldurur; ortakla borç varsa 42a/42b elle cevaplanır (araç uyarır).
- **Pro forma 1120**: üstte "Foreign-owned U.S. DE"; zorunlu: isim, adres, B (EIN), E. D de doldurulur.

## Dosyalama

- Son tarih: takvim yılı için **15 Nisan**. Uzatma: Form 7004 (üstüne "Foreign-owned U.S. DE", Form 1120 kodu).
- E-file **yapılamaz**. Faks: **855-887-7737** (300 DPI+) veya posta:
  Internal Revenue Service, 1973 Rulon White Blvd, M/S 6112, Attn: PIN Unit, Ogden, UT 84201
- Ekler: pro forma 1120 + Form 5472 + Part V statement.
- Gecikme/eksik dosyalama cezası form başına **$25.000**.

## Yol haritası

1. ✅ Kural motoru (Form 5472 Rev. 12-2023), CLI
2. ✅ Grafik arayüz, Mercury içe aktarma, Form 5472 PDF doldurma
3. ✅ Pro forma 1120 PDF doldurma (üstte "Foreign-owned U.S. DE" damgası) ve faks paketi
4. ⏭ Birim testleri
