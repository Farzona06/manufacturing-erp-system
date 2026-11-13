# Manufacturing Production Planning System

Flask asosidagi ishlab chiqarishni rejalashtirish va boshqarish uchun akademik ERP MVP.

## Imkoniyatlar
- Dashboard va Chart.js statistikasi
- Mahsulotlar katalogi
- Ishlab chiqarish rejalari va monitoring
- BOM (Bill of Materials) asosida xomashyo talabi
- Ombor kirim-chiqim tranzaksiyalari
- Mijoz buyurtmalari
- Scikit-learn Linear Regression prognozi
- PDF va Excel hisobotlari
- Login va rollarga asoslangan ruxsatlar

## O‘rnatish (Windows)
```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```
Brauzer: http://127.0.0.1:5000

## Demo akkauntlar
| Rol | Login | Parol |
|---|---|---|
| Administrator | admin | Admin123! |
| Ishlab chiqarish menejeri | manager | Manager123! |
| Ombor menejeri | warehouse | Warehouse123! |

Birinchi ishga tushirishda SQLite bazasi va demo ma’lumotlar avtomatik yaratiladi.

## Muhim
Demo parollarni real muhitda almashtiring. `SECRET_KEY` ni `.env` faylida kuchli tasodifiy qiymatga o‘zgartiring. `.env` va ma’lumotlar bazasi GitHub'ga yuklanmasligi kerak. Prognoz moduli namoyish uchun sun’iy tarixiy ma’lumotlardan foydalanadi.

## Test
```bash
pytest -q
```

## Akademik MVP cheklovlari
- BOM materiallari ishlab chiqarish rejasi uchun bir marta chiqariladi; haqiqiy korxona jarayonida partiya, rezerv va real sarf alohida boshqarilishi kerak.
- Demo ML ma’lumotlari real korxona prognozi o‘rnini bosa olmaydi.
- Audit va migratsiya infratuzilmasi kengaytirilishi mumkin.
