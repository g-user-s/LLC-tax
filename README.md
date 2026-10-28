# LLC-tax — Form 5472 + Pro Forma 1120 hazırlayıcı

Yabancı ortaklı, tek üyeli New Mexico LLC'ler için IRS'e her yıl verilmesi zorunlu
**Form 5472** ve **Pro Forma Form 1120**'yi hazırlayan, yalnızca kendi bilgisayarınızda çalışan uygulama.

Bu belge iki okuyucu için yazıldı:

- **Kullanıcı** (bölüm 1–6): uygulamayı macOS veya Linux'ta kurar ve beyanı hazırlar.
- **Doğrulayıcı yapay zekâ** (bölüm 7): beyan göndermeden önce formların güncel, kuralların doğru,
  kodun hatasız ve doldurulan değerlerin tutarlı olduğunu adım adım kontrol eder.

> Bu araç bir hazırlama yardımcısıdır, vergi danışmanlığı değildir.

---

## 1. Kimler için?

Aşağıdaki koşulların **hepsi** sağlanmalıdır (uygulama ilk adımda sorar, biri bile sağlanmazsa ilerlemez):

1. LLC New Mexico'da kuruldu.
2. LLC'nin tek bir sahibi (üyesi) var.
3. IRS'e corporation olarak vergilendirilme seçimi yapılmadı (Form 8832 / 2553 verilmedi).
4. Sahip ABD vatandaşı, green card sahibi veya ABD vergi mukimi değil.
5. Sahip yıl içinde ABD'de yaşamadı, işi ABD dışından yürüttü.
6. Gelir yalnızca App Store / Google Play kaynaklı.
7. LLC'nin ABD'de ofisi, çalışanı veya adına iş yapan temsilcisi yok.

**Kapsam dışı:** Birden fazla ortak, ortağın şirket olması, ABD'de ticari faaliyet (ECI) veya
1040-NR gerektiren durumlar, eyalet vergileri, ortağın kendi ülkesindeki beyanı, Part VI
(nakit dışı işlemler), Part VIII (maliyet paylaşımı), Part IX.

## 2. Kurulum

Gerekenler: **Python 3.10 veya üstü** ve internet bağlantısı (yalnızca kurulum sırasında).

### macOS

```bash
python3 --version
```

Komut bulunamazsa veya sürüm 3.10'dan düşükse Python'u https://www.python.org/downloads/macos/
adresinden kurun (Homebrew varsa: `brew install python`).

```bash
git clone https://github.com/g-user-s/LLC-tax.git
cd LLC-tax
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Linux (Ubuntu / Debian)

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
git clone https://github.com/g-user-s/LLC-tax.git
cd LLC-tax
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Fedora: `sudo dnf install -y python3 python3-pip git`, sonra aynı adımlar.

### Kurulumu doğrulama (her iki sistem)

```bash
python3 -m llc_tax.verify --year 2025
```

Son satırda `SONUÇ: TAMAM` görünmelidir. `2025` yerine beyan ettiğiniz vergi yılını yazın.

## 3. Kullanım

Her açılışta önce sanal ortamı etkinleştirin, sonra uygulamayı başlatın:

```bash
cd LLC-tax
source .venv/bin/activate
python3 app.py
```

Tarayıcıda 6 adımlı sihirbaz açılır. Tarayıcı açılmazsa terminalde yazan
`http://127.0.0.1:...` adresini kopyalayın. Kapatmak için terminalde **Ctrl+C**.

| Adım | İçerik |
|---|---|
| 1. Uygunluk | Bölüm 1'deki 7 koşul |
| 2. Şirket | LLC adı, EIN, ABD adresi, kuruluş tarihi, yıl başı ve yıl sonu banka bakiyesi |
| 3. Ortak | Ad, yabancı adres, FTIN, Reference ID, ülkeler (kısaltmasız, örn. `Turkey`), yıl başı borç bakiyeleri |
| 4. İşlemler | Elle giriş ve/veya Mercury CSV içe aktarma. Sarı satırların kategorisini kontrol edin |
| 5. Kontrol | Hatalar, uyarılar ve forma yazılacak tüm değerler |
| 6. Formlar | Doldurulmuş PDF'ler + tek dosyalık faks paketi |

**İşlem kategorileri ve formdaki yerleri**

| Kategori | Ödeyen | LLC nakdi | Form 5472 |
|---|---|---|---|
| Gelir (App Store / Google Play) | LLC | + | — (üçüncü taraf) |
| Yazılım / banka / diğer gider | LLC | − | — (üçüncü taraf) |
| Aynı giderler, ortağın kişisel kartıyla | Ortak | etkisiz | Part V (ortak katkısı) |
| Sermaye (ortaktan LLC'ye) | Ortak | + | Part V |
| Kişisel çekim (LLC'den ortağa) | LLC | − | Part V |
| Ortaktan borç / geri ödeme | Ortak / LLC | + / − | Part IV 17a/17b (bakiye) |
| Ortağa borç / tahsilat | LLC / Ortak | − / + | Part IV 31a/31b (bakiye) |
| Ortağa ödenen faiz | LLC | − | Part IV 32 |
| LLC hesapları arası transfer | LLC | yok sayılır | — |

Tutarlar her zaman pozitif girilir; yönü kategori belirler. Yabancı para işlemleri USD karşılığıyla girilir.

**Dosyalar nerede?**

- Girilen veriler: `data/case_<yıl>.json`
- Üretilen formlar: `output/<yıl>/` (`<yıl>_FAX_PAKETI.pdf` = 1120 + 5472 + Part V eki)
- Önceki yılın şirket/ortak bilgileri yeni yıla otomatik taşınır.

**Komut satırı alternatifi:** `config.example.json` ve `transactions.example.csv` dosyalarını
`config.json` ve `transactions.csv` olarak kopyalayıp düzenleyin, sonra:

```bash
python3 generator.py --pdf
```

## 4. Her yıl yapılacaklar

1. `git pull` ile güncellemeleri alın.
2. Beyan edeceğiniz yılın Form 1120'sini https://www.irs.gov/pub/irs-pdf/f1120.pdf adresinden
   indirip `forms/f1120.pdf` dosyasının yerine koyun. Uygulama yanlış yılın formunu reddeder.
3. Doğrulamayı çalıştırın: `python3 -m llc_tax.verify --year <yıl> --online`
4. Herhangi bir satır `HATA` ise bölüm 7'yi bir yapay zekâya uygulatın veya geliştiriciye bildirin.
   macOS'ta `--online` kontrolü `CERTIFICATE_VERIFY_FAILED` hatası verirse, python.org kurulumuyla gelen
   **Install Certificates.command** dosyasını çalıştırın (Uygulamalar → Python 3.x klasöründe).

## 5. Gönderim

- **Son tarih:** Takvim yılı için izleyen yılın **15 Nisan**'ı. Uzatma için Form 7004
  (üstüne "Foreign-owned U.S. DE" yazılır, Form 1120 kodu seçilir).
- **E-file yapılamaz.** Faks: **855-887-7737** (300 DPI veya üzeri) ya da posta:
  Internal Revenue Service, 1973 Rulon White Blvd, M/S 6112, Attn: PIN Unit, Ogden, UT 84201
- Göndermeden önce 1120'deki **"Sign Here"** bölümünü imzalayın ve tarih atın.
- Geç veya eksik dosyalama cezası form başına **$25.000**'dır.

## 6. Gizlilik

- Sunucu yalnızca `127.0.0.1` adresini dinler ve başka host adlarından gelen istekleri reddeder.
- Uygulama hiçbir dış adrese bağlanmaz. Tek istisna `verify --online`; o da irs.gov'dan herkese
  açık PDF'leri indirir ve hiçbir kullanıcı verisi göndermez.
- `config.json`, `transactions.csv`, `data/` ve `output/` `.gitignore`'dadır ve repoya girmez.

---

## 7. Yapay zekâ doğrulama protokolü

> **Bu bölüm, beyan göndermeden önce bir yapay zekâ asistanının izlemesi için yazılmıştır.**
> Adımları sırayla uygula. Her adımın sonucunu `GEÇTİ`, `KALDI` veya `DOĞRULANAMADI` olarak kaydet
> ve en sonda 7.9'daki şablonla raporla.

### 7.0 Kurallar

1. **Tahmin yürütme.** Bir kaynağa erişemiyorsan veya bir şeyi doğrulayamıyorsan sonucu
   `DOĞRULANAMADI` yaz ve nedenini belirt. Hafızadaki bilgiyi resmi kaynak yerine kullanma.
2. **Birincil kaynak esastır:** IRS form/talimat PDF'leri ve 26 CFR (eCFR). Üçüncü taraf blogları
   yalnızca ipucu olabilir, kanıt olamaz.
3. **Gizlilik:** `data/`, `output/`, `config.json` ve `transactions.csv` içeriğini hiçbir dış
   servise gönderme. Ağ erişimi yalnızca irs.gov ve ecfr.gov'dan herkese açık belge okumak içindir.
4. **Kullanıcı verisini değiştirme.** Hata bulursan raporla; düzeltmeyi kullanıcı onaylamadan yapma.
5. Kod değişikliği önerirsen önce ilgili testi yaz, sonra `python3 -m unittest -v` ile tüm testlerin
   geçtiğini göster.

### 7.1 Adım 1 — Otomatik kontroller

```bash
python3 -m llc_tax.verify --year <VERGI_YILI> --online
```

Ağ erişimin yoksa `--online` olmadan çalıştır ve 7.2'yi elle yap. Çıktıdaki her satır:

| Satır | HATA ise anlamı ve yapılacak |
|---|---|
| `Python >= 3.10` | Python güncellenmeli (bölüm 2) |
| `pypdf kurulu` | `pip install -r requirements.txt` |
| `forms/f5472.pdf bilinen sürüm ve alan düzeni` | Yerel PDF değiştirilmiş veya bozuk. 7.6'yı uygula |
| `forms/f1120.pdf bilinen sürüm ve alan düzeni` | Yeni yılın 1120'si eklenmiş, eşleştirme bu yıl için doğrulanmamış. 7.6'yı uygula |
| `forms/f1120.pdf yılı = <yıl>` | Yanlış yılın 1120'si. Bölüm 4, madde 2 |
| `Birim testleri` | Kod hatası. Başarısız testin çıktısını incele (7.4) |
| `irs.gov f5472.pdf = yerel sürüm` | IRS yeni revizyon yayımlamış. 7.2 ve 7.6 |
| `irs.gov f1120.pdf = yerel sürüm` | irs.gov'daki güncel 1120 başka bir yıla ait olabilir (yeni yıl yayımlanmış olabilir). Beyan yılının formunun kullanıldığını teyit et |
| `irs.gov i5472 talimatı Rev. December 2024` | Talimat güncellenmiş. 7.3'teki tüm alıntıları yeni metinde ara |

Beklenen: `SONUÇ: TAMAM` ve çıkış kodu `0`.

### 7.2 Adım 2 — Form güncelliği (elle)

| Belge | Beklenen | Kaynak |
|---|---|---|
| Form 5472 | `Rev. December 2023` | https://www.irs.gov/pub/irs-pdf/f5472.pdf |
| Form 5472 talimatı | `Rev. December 2024` | https://www.irs.gov/instructions/i5472 |
| Form 1120 | Beyan yılı (`For calendar year <YIL>`) | https://www.irs.gov/pub/irs-pdf/f1120.pdf (önceki yıllar: https://www.irs.gov/pub/irs-prior/f1120--<YIL>.pdf) |
| Gelişmeler | Form/talimat değişikliği duyurusu | https://www.irs.gov/forms-pubs/about-form-5472 ("Recent developments") |

Revizyon farklıysa: 7.3'teki kuralları yeni talimatta yeniden doğrula, 7.6 ile alan eşleştirmesini
yeniden yap ve `llc_tax/verify.py` içindeki `EXPECTED` sözlüğünü güncelle.

### 7.3 Adım 3 — Kural matrisi

Her satır için: (a) alıntıyı güncel resmi metinde **birebir** ara, (b) kodun bu kuralı uyguladığını
kontrol et, (c) ilgili testin varlığını doğrula. Alıntı bulunamazsa veya anlamı değişmişse `KALDI`.

| # | Kural | Resmi metin (birebir aranacak alıntı) | Kaynak | Kodda | Test |
|---|---|---|---|---|---|
| K1 | Pro forma 1120'de yalnızca isim, adres, B ve E zorunlu | "The only information required to be completed on Form 1120 is the name and address of the foreign-owned U.S. DE and items B and E on the first page." | i5472, When and Where To File | `pdf_fill.values_1120` | `test_pro_forma_1120_fields` |
| K2 | 1120'nin üstüne ibare | "“Foreign-owned U.S. DE” should be written across the top of the Form 1120." | i5472, When and Where To File | `pdf_fill._stamp` | `test_pro_forma_1120_fields` |
| K3 | E-file yok; faks/posta | "If you are a foreign-owned U.S. DE, you cannot file Form 5472 electronically." / "Fax (300 DPI or higher) to 855-887-7737" | i5472 | README §5, arayüz 6. adım | — |
| K4 | 1c = 1120 D | "Domestic reporting corporations enter the total assets from Form 1120, page 1, item D." | i5472, Line 1c | `engine.compute` → `total_assets` | `test_pro_forma_1120_fields` |
| K5 | 1f, DE için Part V'i de kapsar | "Enter the total value in U.S. dollars of all foreign related party transactions reported in Parts IV and VI (and if the reporting corporation is a foreign-owned U.S. DE, Part V) of this Form 5472." | i5472, Line 1f | `engine.compute` → `gross` | `test_example_numbers` |
| K6 | Satır 3 işaretlenir | "Line 3. Check this box if you are a foreign-owned U.S. DE." | i5472, Line 3 | `pdf_fill.values_5472` → `c1_4` | `test_form_5472_fields` |
| K7 | DE, Part II'yi doldurur | "Only 25% foreign-owned U.S. corporations, including foreign-owned U.S. DEs, complete Part II." | i5472, Part II | `pdf_fill.values_5472` → `f1_20…f1_26` | `test_form_5472_fields` |
| K8 | FTIN yoksa "None" | "If you do not have an FTIN, enter “None” or “N/A” in the FTIN block." | i5472, Lines 4b(3)… | `pdf_fill.values_5472` → `ftin` | — |
| K9 | Reference ID kuralı | "A reference ID number is required only in cases where no U.S. identifying number was entered for the foreign related party on line 8b(1)." ve "no special characters or spaces are permitted. The length of a given reference ID number is limited to 50 characters." | i5472, Part III / Reference ID | `engine.validate`, `REF_ID_RE` | `test_validation_rules` |
| K10 | Part III herkes için zorunlu | "All filers must complete Part III even if the related party has been identified in Part II as a 25% foreign shareholder." | i5472, Part III | `pdf_fill.values_5472` → `f2_1…f2_8` | `test_form_5472_fields` |
| K11 | Ülke adı kısaltılmaz | "Do not abbreviate the country name." | i5472, Line 1a | `engine.validate` | `test_validation_rules` |
| K12 | Borç: başlangıç/bitiş bakiyesi | "If the outstanding balance method is used, enter the beginning and ending outstanding balances for the tax year on lines 17a and 17b." (31a/31b için aynı) | i5472, Line 17 / Line 31 | `engine.compute` → `line17a/b`, `line31a/b` | `test_example_numbers` |
| K13 | 21/35 yalnızca vergilendirilebilir geliri etkileyen tutarlar | "Include amounts on line 21 to the extent that these amounts are taken into account in determining the taxable income of the reporting corporation." | i5472, Line 21 / Line 35; 26 CFR 1.6038A-2(b)(3)(x) | `engine.compute` (21/35 hiç doldurulmaz) | `test_contributions_and_draws_never_in_part_iv` |
| K14 | Sermaye ve çekimler Part V'e | "You must check the box in Part V if you are a foreign-owned DE that had any other transaction, as defined by Regulations section 1.482-1(i)(7) not already entered in Part IV. These transactions include amounts paid or received in connection with the formation, dissolution, acquisition, and disposition of the entity, including contributions to, and distributions from, the entity." | i5472, Part V; 26 CFR 1.6038A-2(b)(3)(xi) | `engine.compute` → `part_v_total`, `engine.part_v_statement` | `test_contributions_and_draws_never_in_part_iv` |
| K15 | Ortağın LLC adına ödemesi bir "transaction"dır | "Transaction means any sale, assignment, lease, license, loan, advance, contribution, or any other transfer of any interest in or a right to use any property (whether tangible or intangible, real or personal) or money" | 26 CFR 1.482-1(i)(7) | `engine.compute` → `owner_paid_exp` | `test_example_numbers` |
| K16 | Part VII herkes için zorunlu | "All reporting corporations must complete the additional information in Part VII." | i5472, Part VII | `pdf_fill.values_5472` → `answers` | `test_form_5472_fields` |
| K17 | Ceza | "A penalty of $25,000 will be assessed on any reporting corporation that fails to file Form 5472 when due" | i5472, Penalties | README §5 | — |
| K18 | Üçüncü taraf işlemler raporlanmaz | Part IV başlığı: "Monetary Transactions Between Reporting Corporations and Foreign Related Party" | f5472, Part IV | `engine.compute` (gelir ve LLC giderleri 5472'ye girmez) | `test_third_party_items_not_reported` |

eCFR: https://www.ecfr.gov/current/title-26/section-1.6038A-2 ve
https://www.ecfr.gov/current/title-26/section-1.482-1

### 7.4 Adım 4 — Kod incelemesi

Testler geçse bile aşağıdakileri kodu okuyarak doğrula:

1. **`llc_tax/engine.py` → `compute`**
   - Ortağın kişisel olarak ödediği giderler (`EXPENSE_CATEGORIES` ve `paid_by == "owner"`) LLC nakdini **etkilememeli**.
   - `line22 = borrowed_end` ve `line36 = loaned_end + interest_paid` olmalı; sermaye ve çekim bu toplamlara **girmemeli**.
   - `gross = line22 + line36 + part_v_total`.
   - Yuvarlama `ROUND_HALF_UP` ile tam dolara; toplamlar önce kuruşlu hesaplanıp sonra yuvarlanmalı.
2. **`engine.validate`**: `OWNER_PAYS` ve `LLC_PAYS` kümeleri kategorilerle tutarlı mı? Her işlem tarihi vergi yılı içinde mi kontrol ediliyor?
3. **`llc_tax/pdf_fill.py`**: Alan adları 7.7'deki tablolarla birebir aynı mı? Part VII'de "Yes" için `[0]`/`/1`, "No" için `[1]`/`/2` kullanılıyor mu (`F5472_YES_NO`)?
4. **`llc_tax/mercury.py`**: Durumu `failed / cancelled / pending / blocked / reversed` olanlar ve vergi yılı dışındaki satırlar atlanıyor mu? Emin olunamayan kategoriler `needs_review` ile işaretleniyor mu?
5. **`llc_tax/server.py`**: Yalnızca `127.0.0.1`'e bağlanıyor mu, `Host` kontrolü var mı, `/output/` yolu dizin dışına çıkışa (path traversal) kapalı mı?
6. Dış ağa istek yapan tek yer `llc_tax/verify.py` → `fetch` olmalı:

   ```bash
   grep -rnE "urlopen|requests|http\.client|socket\.connect" llc_tax/ app.py generator.py
   ```

### 7.5 Adım 5 — Kullanıcının beyanını kontrol

Girdi: `data/case_<YIL>.json` ve `output/<YIL>/` altındaki PDF'ler. Hesaplanan değerleri görmek için:

```bash
python3 -c "
import json; from llc_tax import engine
c = json.load(open('data/case_<YIL>.json')); e, t = engine.validate(c)
print('HATALAR:', e) if e else print(json.dumps(engine.compute(c, t), indent=1, ensure_ascii=False))"
```

| # | Kontrol | Nasıl |
|---|---|---|
| D1 | Doğrulama hatası yok | `HATALAR` çıktısı yok |
| D2 | Yıl sonu nakdi banka ekstresiyle tutuyor | `ending_cash_balance_usd_actual` dolu ve "banka bakiyesinden farklı" uyarısı yok |
| D3 | Kategorisi seçilmemiş işlem yok | `transactions` içinde `category == ""` yok |
| D4 | Ortağın kişisel kartıyla ödenen LLC giderleri `paid_by: owner` olarak girilmiş | Kullanıcıya sor; banka dışı ödemeler sık atlanır |
| D5 | 1c = 1120 D | İki PDF'te aynı değer |
| D6 | 1f = 22 + 36 + Part V toplamı | `numbers` üzerinden hesapla |
| D7 | 1f = 1h ve 1g = 1 | PDF'te kontrol |
| D8 | Part V kutusu ↔ Part V eki | `part_v_total > 0` ise kutu işaretli ve ek pakette olmalı |
| D9 | Reference ID önceki yılla aynı | `data/case_<YIL-1>.json` ile karşılaştır |
| D10 | Ülke adları kısaltmasız ve İngilizce | Part II/III alanları |
| D11 | Ortakla borç varsa 42a/42b cevaplanmış | `part_vii` boş olmamalı |
| D12 | 1j ve 1120 E(1) yalnızca ilk yıl işaretli | `first_year_filing_5472` ile kuruluş tarihi tutarlı |
| D13 | Uygunluk koşulları hâlâ doğru | Kullanıcıya bölüm 1'deki 7 maddeyi teyit ettir |
| D14 | Faks paketi sırası | `<YIL>_FAX_PAKETI.pdf`: 1120 → 5472 → Part V eki |
| D15 | İmza | 1120 "Sign Here" kullanıcı tarafından imzalanacak (uygulama doldurmaz) |

### 7.6 Form revizyonu değişirse: alan eşleştirmesini yeniden doğrulama

IRS PDF alanlarının açıklaması yoktur (`f1_5` gibi adlar); eşleştirme **görsel** olarak doğrulanmalıdır.

1. Her alana kendi adını yazan bir test PDF'i üret:

   ```bash
   python3 - <<'EOF'
   from pypdf import PdfReader, PdfWriter
   for name in ("f5472", "f1120"):
       w = PdfWriter(); w.append(PdfReader(f"forms/{name}.pdf"))
       for page in w.pages:
           vals = {}
           for a in page.get("/Annots", []) or []:
               t = str(a.get_object().get("/T", ""))
               if t.startswith("f"):
                   vals[t] = t.split("[")[0]
           w.update_page_form_field_values(page, vals, auto_regenerate=False)
       w.set_need_appearances_writer(True)
       w.write(f"/tmp/{name}_ids.pdf")
   EOF
   ```

2. Görüntüye çevir ve incele (macOS: `brew install poppler`, Linux: `sudo apt install poppler-utils`):

   ```bash
   pdftoppm -r 110 -png /tmp/f5472_ids.pdf /tmp/f5472_ids
   pdftoppm -r 110 -png -f 1 -l 1 /tmp/f1120_ids.pdf /tmp/f1120_ids
   ```

3. Her alan adının formda hangi satıra düştüğünü 7.7'deki tablolarla karşılaştır. Checkbox'lar için
   `/Rect` koordinatlarını satır metinleriyle eşleştir.
4. Farklılık varsa `llc_tax/pdf_fill.py`, 7.7 tabloları ve `tests/test_all.py` beklenen değerlerini güncelle.
5. Yeni parmak izini al ve `llc_tax/verify.py` → `EXPECTED` içine yaz:

   ```bash
   python3 -c "from llc_tax.verify import layout_fingerprint as f; print(f(open('forms/f5472.pdf','rb').read())); print(f(open('forms/f1120.pdf','rb').read(), {0}))"
   ```

6. `python3 -m llc_tax.verify --year <YIL>` → `SONUÇ: TAMAM`.

### 7.7 PDF alan eşleştirme tabloları

**Form 5472 (Rev. December 2023)** — `forms/f5472.pdf`

| Alan | Satır | Değer |
|---|---|---|
| `f1_1`, `f1_2` / `f1_3`, `f1_4` | Başlık: tax year beginning / ending | `01/01`, yıl / `12/31`, yıl |
| `f1_5`, `f1_6`, `f1_7` | 1a: isim; sokak; şehir, eyalet ZIP | Şirket |
| `f1_8` | 1b EIN | |
| `f1_9` | 1c Total assets | Yıl sonu nakdi |
| `f1_10`, `f1_11` | 1d, 1e faaliyet / kod | |
| `f1_12`, `f1_13`, `f1_14` | 1f, 1g, 1h | 1f, `1`, 1f |
| `c1_1`, `c1_2` | 1i consolidated, 1j initial year | 1i boş; 1j ilk yılsa |
| `f1_15`, `f1_16`, `f1_17` | 1k, 1l, 1m | `0`, `United States`, kuruluş tarihi (AA/GG/YYYY) |
| `f1_18`, `f1_19` | 1n, 1o | `United States`, kullanıcı girişi |
| `c1_3`, `c1_4`, `c1_5` | 2 (≥%50 yabancı), 3 (foreign-owned U.S. DE), Part II surrogate | işaretli, işaretli, boş |
| `f1_20` … `f1_26` | 4a, 4b(1), 4b(2), 4b(3), 4c, 4d, 4e | Ortak |
| `f1_27` … `f1_47` | 5a–7e | Boş (tek ortak) |
| `c2_1[0]` / `c2_1[1]` | Part III: foreign person / U.S. person | `[0]` işaretli |
| `f2_1` … `f2_6` | 8a, 8b(1), 8b(2), 8b(3), 8c, 8d | Ortak |
| `c2_2`, `c2_3`, `c2_4` | 8e: related to reporting corp / related to 25% shareholder / 25% foreign shareholder | `c2_4` işaretli |
| `f2_7`, `f2_8` | 8f, 8g | Ortak |
| `c2_5` | Part IV estimates | Boş |
| `f2_9` … `f2_17` | 9, 10, 11, 12, 13a, 13b, 14, 15, 16 | Boş |
| `f2_18`, `f2_19` | 17a, 17b | Ortaktan borç varsa |
| `f2_20` … `f2_23` | 18, 19, 20, 21 | Boş |
| `f2_24` | 22 Total | |
| `f2_25` … `f2_33` | 23, 24, 25, 26, 27a, 27b, 28, 29, 30 | Boş |
| `f2_34`, `f2_35` | 31a, 31b | Ortağa borç verildiyse |
| `f2_36` | 32 Interest paid | Varsa |
| `f2_37` … `f2_39` | 33, 34, 35 | Boş |
| `f2_40` | 36 Total | |
| `c2_6`, `c2_7` | Part V, Part VI | Part V tutarı varsa işaretli; VI boş |
| `c3_1` / `c3_2` / `c3_3` / `c3_4` | 37 / 38a / 38c / 39 (`[0]` = Yes `/1`, `[1]` = No `/2`) | 37 No, 39 No |
| `c3_5` + `f3_1` | 40a + 40b | No |
| `c3_6` + `f3_2` … `f3_4` | 41a + 41b–d | No |
| `c3_7`, `c3_8` | 42a, 42b | Borç yoksa No; varsa kullanıcı cevabı |
| `c3_9` + `f3_5`, `f3_6` | 43a + 43b(1), (2) | No |
| `f3_7` … `f3_18`, `c3_10` … `c3_12` | Part VIII–IX | Boş |

**Form 1120 (2025)** — `forms/f1120.pdf`, yalnızca 1. sayfa

| Alan | Satır | Değer |
|---|---|---|
| (damga) | Üst kenar | `Foreign-owned U.S. DE` |
| `f1_1`, `f1_2`, `f1_3` | Fiscal year beginning / ending | Boş (takvim yılı) |
| `f1_4` | Name | |
| `f1_5`, `f1_6` | Number and street; Room or suite no. | Sokak (suite dahil); boş |
| `f1_7`, `f1_8`, `f1_9`, `f1_10` | City; State; Country; ZIP | Şehir; eyalet; boş; ZIP |
| `f1_11` | B EIN | |
| `f1_12` | C Date incorporated | AA/GG/YYYY |
| `f1_13` | D Total assets | 5472 1c ile aynı |
| `c1_1` … `c1_5` | A: 1a, 1b, 2, 3, 4 | Boş |
| `c1_6`, `c1_7`, `c1_8`, `c1_9` | E(1) initial, (2) final, (3) name change, (4) address change | Yalnızca ilk yılsa `c1_6` |
| Diğer tüm alanlar | Gelir, gider, imza | Boş |

### 7.8 Bilinen sınırlamalar (rapora ekle)

- LLC'nin tek varlığının nakit olduğu varsayılır (toplam varlık = yıl sonu nakdi).
- Borçlarda "outstanding balance" yöntemi kullanılır; "monthly average" desteklenmez.
- "$50,000 or less" küçük tutar gösterimi kullanılmaz; gerçek tutarlar yazılır.
- Part VII 40a ve 43a her zaman "No"dur. Ortağa faiz ödendiyse uygulama uyarır; uzmana danışılmalıdır.
- Satır 1o'ya (işin yürütüldüğü ülke) ne yazılacağı yoruma açıktır; varsayılan `United States`.
- Mercury CSV biçimi Mercury tarafından yayımlanmamıştır; içe aktarılan her işlem 4. adımda gözden geçirilmelidir.
- Yabancı para işlemlerinin USD karşılığını kullanıcı girer; kur tablosu üretilmez.

### 7.9 Rapor şablonu

```
DOĞRULAMA RAPORU — <LLC adı> — Vergi yılı <YIL> — <tarih>

1. Otomatik kontroller (7.1):        GEÇTİ / KALDI / DOĞRULANAMADI — verify çıktısı özeti
2. Form güncelliği (7.2):            ... — 5472 rev: ..., talimat rev: ..., 1120 yılı: ...
3. Kural matrisi (7.3):              ... — KALDI / DOĞRULANAMADI olan K numaraları ve nedeni
4. Kod incelemesi (7.4):             ... — bulgular (dosya → fonksiyon)
5. Beyan kontrolü (7.5):             ... — D1–D15 sonuçları
6. Sınırlamalardan etkilenen durum:  ... — 7.8'den bu beyana uyanlar

GENEL SONUÇ: GÖNDERİLEBİLİR / DÜZELTME GEREKLİ / UZMANA DANIŞILMALI
Kullanıcının yapması gerekenler: (madde madde)
```

---

## Proje yapısı

| Yol | Görev |
|---|---|
| `app.py` | Grafik arayüzü başlatır |
| `generator.py` | Komut satırı sürümü |
| `llc_tax/engine.py` | Doğrulama + hesaplama |
| `llc_tax/mercury.py` | Banka CSV içe aktarma |
| `llc_tax/pdf_fill.py` | PDF doldurma, Part V eki, faks paketi |
| `llc_tax/server.py`, `llc_tax/static/` | Yerel arayüz |
| `llc_tax/verify.py` | Kurulum ve form güncelliği kontrolü |
| `tests/test_all.py` | Birim testleri (`python3 -m unittest -v`) |
| `forms/` | Resmi IRS PDF'leri (f5472 Rev. 12-2023, f1120 2025) |
