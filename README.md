# LLC-tax — Form 5472 + Pro Forma 1120 veri hazırlayıcı

Yabancı ortaklı, tek üyeli (disregarded entity) New Mexico LLC için yıllık
**Form 5472** ve **Pro Forma Form 1120** verilerini yerelde hesaplar.

- Sadece Python standart kütüphanesi, **ağ erişimi yok**, dış bağımlılık yok.
- Gerçek veriler (`config.json`, `transactions.csv`, `output/`) `.gitignore` ile repoya girmez.

> Bu araç bir hesaplama yardımcısıdır, vergi danışmanlığı değildir. Dosyalamadan önce
> güncel IRS talimatlarıyla (Instructions for Form 5472) karşılaştırın.

## Yapı

| Dosya | Görev |
|---|---|
| `config.example.json` | Şirket + ortak bilgileri şablonu → `config.json` olarak kopyala |
| `transactions.example.csv` | Yıllık işlem kaydı şablonu → `transactions.csv` olarak kopyala |
| `generator.py` | Doğrular, hesaplar, satır/kutu matrisini basar, `output/`'a yazar |
| `output/` | `form_data_<yıl>.json`, `part_v_statement_<yıl>.txt` |

## Kullanım

```bash
cp config.example.json config.json
cp transactions.example.csv transactions.csv
# iki dosyayı kendi verinizle düzenleyin
python3 generator.py
```

Seçenekler: `--config`, `--transactions`, `--output-dir`, `--no-write`.
Doğrulama hatası varsa hiçbir şey yazılmaz ve çıkış kodu `1` olur.

## transactions.csv

Sütunlar: `date,description,category,amount_usd,counterparty,paid_by,notes`

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

1. ✅ Klasör yapısı, örnek config/CSV, doğrulama + satır matrisi (`generator.py`)
2. ⏭ Resmi IRS PDF'lerindeki alan adlarını çıkarıp `pdf_field_map.json` ile otomatik PDF doldurma (yerel, `pypdf`)
3. ⏭ Banka (Mercury/Wise) CSV dışa aktarımlarını `transactions.csv` formatına çeviren içe aktarıcı
4. ⏭ Çok yıllı açılış bakiyesi devri ve birim testleri
