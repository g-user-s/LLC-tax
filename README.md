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
| aynı giderler | **owner** | etkisiz | Part IV satır 12 + Part V (ortak katkısı sayılır) |
| `capital_contribution` | owner | + | Part IV satır 12 + Part V |
| `owner_draw` | llc | − | Part IV satır 25 + Part V |
| `loan_from_owner` / `loan_repayment_to_owner` | owner / llc | + / − | Part IV 9a/9b (bakiye) |
| `loan_to_owner` / `loan_repayment_from_owner` | llc / owner | − / + | Part IV 22a/22b (bakiye) |
| `interest_paid_to_owner` | llc | − | Part IV satır 23 |

## Hesaplama kuralları

- **Toplam varlık** (1120 D, 5472 1c) = açılış nakdi + LLC hesabından geçen net hareketler.
  Varsayım: LLC'nin nakit dışında varlığı yok.
- **5472 1f / 1h** = Part IV satır 13 + satır 26. Tek ortak → 1g = 1.
- **Part V**: katkı/çekim varsa kutu işaretlenir, detay `part_v_statement_<yıl>.txt` ek sayfasına yazılır.
- `options.report_contributions_distributions_in_part_iv=false` yaparsanız katkı/çekim
  yalnızca Part V'te raporlanır (uygulamada iki yaklaşım da görülür).
- **Pro forma 1120**: üstte "Foreign-owned U.S. DE", isim, adres, B (EIN), C, D, E; gelir/gider satırları boş.

## Dosyalama hatırlatmaları

- Son tarih: takvim yılı için **15 Nisan** (uzatma: Form 7004).
- E-file yok; faks veya posta ile IRS'e gönderilir — güncel adres/faks numarasını IRS talimatından teyit edin.
- Gecikme/eksik dosyalama cezası form başına **$25.000**.

## Yol haritası

1. ✅ Klasör yapısı, örnek config/CSV, doğrulama + satır matrisi (`generator.py`)
2. ⏭ Resmi IRS PDF'lerindeki alan adlarını çıkarıp `pdf_field_map.json` ile otomatik PDF doldurma (yerel, `pypdf`)
3. ⏭ Banka (Mercury/Wise) CSV dışa aktarımlarını `transactions.csv` formatına çeviren içe aktarıcı
4. ⏭ Çok yıllı açılış bakiyesi devri ve birim testleri
