# Django Agent Template

Template กลางสำหรับแชตบอทรับเรื่องแจ้งปัญหา ประกอบด้วย Django, DSPy agent, PostgreSQL และหน้า Chat UI
โดยไม่ใช้ CSV, dashboard หรือข้อมูลตัวอย่าง

## Run

```bash
cp .env.example .env
# ใส่ GEMINI_API_KEY ใน .env
docker compose up --build
```

เปิด http://localhost:8000/ ประวัติแชตเก็บใน Django session บน PostgreSQL และจำกัดเฉพาะข้อความล่าสุด
Docker Compose จะรอ PostgreSQL พร้อมและรัน migration ให้อัตโนมัติ

## BEM incident flow

- Agent flow: `COLLECTING` → `CONFIRMING` → `SUBMITTED`
- Case status: `OPEN` → `IN_PROGRESS` → `CLOSED`
- ทุกการแจ้งเหตุมี Ticket ID รูปแบบ `BEM-YYYYMMDD-XXXXXX`
- Taxonomy เป็น structured output 2 ระดับตาม BEM Risk Events Taxonomy
- หน้า Chat ตรวจสถานะใหม่ทุก 7 วินาทีและแจ้งผู้ใช้เมื่อสถานะเปลี่ยน

สร้างบัญชีเจ้าหน้าที่และจัดการสถานะเคสที่ `/admin/`:

```bash
docker compose exec backend python manage.py createsuperuser
```

เมื่อแก้สถานะเคสผ่าน Django Admin ระบบจะสร้าง status event เพื่อแจ้งหน้า user อัตโนมัติ

หน้าเจ้าหน้าที่สำหรับติดตาม Ticket แบบรวมศูนย์อยู่ที่ `/monitor/` (ต้องเข้าสู่ระบบด้วยบัญชี staff)
รองรับ KPI, ค้นหา, กรองสถานะ/ความเร่งด่วน, เปิดดูรายละเอียดและ timeline และรีเฟรชอัตโนมัติทุก 15 วินาที
