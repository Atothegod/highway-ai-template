# Django Agent Template

Template กลางสำหรับแชตบอทรับเรื่องแจ้งปัญหา ประกอบด้วย Django, DSPy agent, PostgreSQL และหน้า Chat UI
ข้อมูลเคสและประวัติการติดตามจัดเก็บใน PostgreSQL

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

## Operations

- `/operations/` Dashboard ภาพรวมจำนวนเคสตามสถานะและเคสที่แจ้งล่าสุด
- `/operations/map/` แผนที่ตำแหน่งเคส แสดงสีตามความเร่งด่วน พร้อมรายการเคสและตัวกรอง
- `/operations/board/` บอร์ด Kanban แบ่งตามสถานะเคส ลากการ์ดข้ามคอลัมน์เพื่อเปลี่ยนสถานะ หรือเลือก **แก้ไขเคส** เพื่อเปลี่ยนสถานะ ความเร่งด่วน สถานที่ และพิกัด ระบบจะแจ้งสถานะใหม่ผ่านแชต BEM Care ของผู้แจ้ง

เข้าสู่ Operations ด้วยบัญชี staff เช่นเดียวกับหน้า Monitor เจ้าหน้าที่ที่มีสิทธิ์แก้ไขเคสสามารถคลิกแผนที่ ลากหมุด ใช้ตำแหน่งอุปกรณ์ (เมื่อเบราว์เซอร์อนุญาต) หรือกรอกละติจูดและลองจิจูดเอง
ระบบรองรับตำแหน่งที่บันทึกเป็นคู่พิกัดในช่องสถานที่ เช่น `13.7563, 100.5018` เคสที่ยังไม่มีพิกัดจะอยู่ในรายการและบอร์ด
แผนที่พื้นฐานใช้ OpenStreetMap และโหลด Leaflet จาก CDN


### พิกัดจุดเกิดเหตุในหน้าแชต

ผู้แจ้งแตะหรือลากหมุดบนแผนที่แล้วบันทึกก่อนยืนยันส่งเรื่อง ระบบใช้พิกัดเดิม
หรือคู่พิกัดที่แจ้งมาเป็นจุดเริ่ม ถ้าต้องการค้นจุดเริ่มจากชื่อสถานที่ ให้ตั้ง
`INCIDENT_GEOCODER_URL` ใน `.env` เป็น URL สำหรับค้นหาของบริการ geocoder
ที่องค์กรอนุมัติและรองรับผลลัพธ์รูปแบบ Nominatim JSON v2 ระบบส่งเฉพาะข้อความในฟิลด์สถานที่
เมื่อมีการเปิดแผนที่และยังไม่มีจุดเริ่ม ถ้าหาไม่พบ ผู้แจ้งเลือกตำแหน่งเองได้

Agent แนบการ์ดจุดเกิดเหตุในข้อความแชต หากใช้ผู้ให้บริการแผนที่ขององค์กร
ให้ตั้ง `INCIDENT_MAP_TILE_URL` (XYZ raster) และ `INCIDENT_MAP_ATTRIBUTION`
ใน `.env` จากนั้นสร้างคอนเทนเนอร์ backend ใหม่

ทีมรับผิดชอบ SLA ผลการแก้ไข และข้อมูลส่งต่อ GRC แก้ไขได้ใน Django Admin
เวลามอบหมายบันทึกเมื่อเปลี่ยนทีม เวลาปิดเคสใช้ประวัติสถานะเดิม
และสถานะส่งต่อ GRC เป็นข้อมูลที่เจ้าหน้าที่บันทึก

## ทดสอบโหลดแชต BEM Care ด้วยผู้ใช้ 200 คน

ใช้ Python 3 โดยไม่ต้องติดตั้งไลบรารีเพิ่ม สคริปต์สร้างบทความแจ้งเหตุสมมติหนึ่งเรื่องต่อผู้ใช้
ล็อกอินให้แต่ละคนมี cookie และ session ของตัวเอง แล้วส่ง `POST /api/chat/` หนึ่งคำขอต่อคนพร้อมกัน
หากล็อกอินบางคนไม่สำเร็จ สคริปต์จะส่งเฉพาะ session ที่พร้อมและบันทึกความล้มเหลวลง CSV ด้วย
ให้ชี้ไปที่สภาพแวดล้อมทดสอบ เพราะ agent อาจสร้าง Ticket จริงในฐานข้อมูลของปลายทางและใช้โควตา Gemini

จากโฟลเดอร์ `agent-builder` ถ้ามี staging แบบ HTTPS ให้ใช้ origin ของ staging กับ `--base-url`
สำหรับ Docker บนเครื่อง ให้รันคำสั่งต่อไปนี้ในอีกเทอร์มินัล โดยให้พอร์ต 8000 ว่างและตั้งค่า `.env` ตามหัวข้อ Run แล้ว
คำสั่งนี้ปิด Secure cookies เฉพาะคอนเทนเนอร์ทดสอบ เพื่อให้ล็อกอินผ่าน HTTP บนเครื่องได้

```bash
docker compose run --rm --build --service-ports -e DJANGO_HTTPS_DOMAIN= backend
```

รัน smoke test แล้วจึงยิง 200 คำขอพร้อมกัน

```bash
python3 scripts/load_chat.py --base-url http://127.0.0.1:8000 --users 5 --output results/chat-5.csv
python3 scripts/load_chat.py --base-url http://127.0.0.1:8000 --users 200 --output results/chat-200.csv
```

CSV มีหนึ่งแถวต่อผู้ใช้และเปิดใน Excel ได้ โดยมีคอลัมน์หลักดังนี้

| คอลัมน์ | ความหมาย |
| --- | --- |
| `user_id`, `article`, `reply` | ผู้ใช้จำลอง บทความที่ส่ง และคำตอบของ agent |
| `state`, `http_status`, `error` | ผลของคำขอ สถานะ HTTP และรายละเอียดเมื่อเกิดข้อผิดพลาด |
| `sent_at_utc`, `latency_ms` | เวลาเริ่มส่งจากเครื่องทดสอบ และเวลาจนรับ response ครบหรือพบข้อผิดพลาด |
| `ticket_id`, `flow_state` | เลข Ticket และสถานะของบทสนทนา ถ้ามี |

สคริปต์แสดงจำนวนคำตอบสำเร็จและ p50/p95/p99 ของคำตอบสำเร็จเมื่อจบ
หากมีผู้ใช้ที่ไม่ได้รับคำตอบ สคริปต์ยังบันทึก CSV และคืน exit code 1
เปลี่ยนชื่อไฟล์ `--output` เมื่อรันซ้ำ ค่า `--timeout` เริ่มต้นที่ 120 วินาทีสำหรับ socket
เวลาที่วัดรวมเส้นทางจากเครื่องยิงโหลดถึง agent และขึ้นกับ backend, ฐานข้อมูล และผู้ให้บริการโมเดล
การทดสอบนี้วัดคำขอแชตระลอกเดียว โดยจับเวลาเฉพาะช่วงส่งข้อความและรับคำตอบ

### รันบน Linux VM และบันทึกสรุป

ถ้าต้องการวัด CPU และ RAM ของ backend ให้รันบน Linux VM ที่รัน backend โดยตรง
จากโฟลเดอร์ `agent-builder` ของ VM ใช้ URL ของระบบทดสอบ ตัวอย่างนี้ใช้ backend HTTP บนเครื่องเดียวกันตามวิธีด้านบน

```bash
run_dir="results/chat-200-$(date -u +%Y%m%dT%H%M%SZ)"
python3 scripts/load_chat.py \
  --base-url http://127.0.0.1:8000 \
  --users 200 \
  --vm-metrics \
  --p95-limit-ms 15000 \
  --output "$run_dir/chat.csv"
```

`15000` เป็นตัวอย่างเกณฑ์ p95 ที่ 15 วินาที ให้เปลี่ยนตามเป้าหมายของทีม หรือตัด flag นี้ออกหากยังไม่ได้กำหนดเป้าหมาย
เมื่อระบุเกณฑ์ รายงานจะแสดง PASS ถ้าทั้ง 200 คนได้รับคำตอบและ p95 อยู่ในเกณฑ์
เมื่อไม่ผ่าน สคริปต์บันทึกรายงานก่อนคืน exit code 1

| ไฟล์ | ข้อมูล |
| --- | --- |
| `chat.csv` | บทความ คำตอบ สถานะ และเวลาตอบของแต่ละคน |
| `chat.summary.txt` | สรุปจำนวนสำเร็จ/ล้มเหลว HTTP status, latency, ผลเทียบเป้าหมาย และสัญญาณทรัพยากร |
| `chat.vm.csv` | ตัวอย่าง CPU busy, CPU steal, I/O wait, RAM, swap และ OOM ของ VM ทุกประมาณหนึ่งวินาทีระหว่างส่งแชต รวมตัวอย่างตอนจบ |

อ่านความพร้อมจากผลเทียบเป้าหมายและกราฟหรือค่าจาก CSV ควบคู่กัน ถ้ารอบ 200 คนผ่านและไม่มีสัญญาณทรัพยากรตึง
ถือว่า VM รองรับโหลดรูปแบบนี้ในรอบที่ทดสอบได้ ถ้า p95 สูงหรือมี error ให้ดูว่าช่วงเดียวกัน CPU แตะ 90%, RAM ใช้ถึง 90%,
เริ่ม swap out, มี OOM kill, I/O wait ถึง 10% หรือ CPU steal ถึง 5% หรือไม่ ตัวเลขเหล่านี้เป็นเกณฑ์สังเกตเบื้องต้น
หาก latency หรือ error สูงแต่ค่าวัด VM ยังต่ำ ให้ตรวจ log ของ backend, PostgreSQL และ Gemini quota เพิ่มเติม

`--vm-metrics` อ่านค่ารวมของ Linux host ที่รันสคริปต์ ถ้ายิงจาก VM เดียวกับ backend ค่าจะรวมโหลดของตัวสคริปต์ด้วย
ถ้ายิงจาก VM อื่น ต้องเก็บ metrics ฝั่ง backend แยกต่างหาก ค่ารวมของ host อาจไม่สะท้อน CPU/RAM limit ของแต่ละคอนเทนเนอร์
ให้เทียบกับ `docker stats` บน VM ที่รัน backend หากตั้ง limit ไว้ ผลรอบนี้เป็นการทดสอบ burst เดียว

ถ้ารายงานขึ้น `Chat attempts: 0` ให้ดูบรรทัด `Login diagnosis` หรือคอลัมน์ `error` ใน `chat.csv`
ค่าเริ่มต้นของ Compose ตั้ง `DJANGO_HTTPS_DOMAIN` และ Django จะตั้ง Secure cookies
ถ้าเรียกพอร์ต 8000 ของ service นี้ตรง ๆ ผ่าน HTTP ให้เปลี่ยน `--base-url` เป็น HTTPS origin ของ **ระบบทดสอบ**
สำหรับการทดสอบ HTTP บนเครื่อง ให้เปิด backend ทดสอบที่ตั้ง `DJANGO_HTTPS_DOMAIN=` ตามตัวอย่าง Docker ด้านบน
ถ้าพอร์ต 8000 ถูกใช้อยู่ ให้ใช้พอร์ต 8001 โดยแทน `--service-ports` ด้วย `-p 127.0.0.1:8001:8000` และแก้ `--base-url` ให้ตรงกัน
ลอง `--users 1` ก่อนเพิ่มเป็น 200 และตรวจว่ารายงานได้ `Chat attempts: 1` พร้อมคำตอบ

### เทียบ Gunicorn กับ runserver เมื่อ PostgreSQL เต็ม

ถ้า PostgreSQL ขึ้น `FATAL: sorry, too many clients already` ให้เก็บผล `runserver` ที่ 25 คนก่อน
จากนั้นหยุดเฉพาะคอนเทนเนอร์ backend ทดสอบบนพอร์ต 8001 ด้วย Ctrl+C ในเทอร์มินัลที่เปิดไว้
แล้วเปิด Gunicorn บนพอร์ตเดิมและ VM เดิม โดยใช้ Compose ของระบบทดสอบ

```bash
docker compose run --rm --build --name bem-gunicorn-test \
  -p 127.0.0.1:8001:8000 -e DJANGO_HTTPS_DOMAIN= backend \
  sh -c 'python manage.py migrate --noinput &&
    exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 \
      --worker-class gthread --workers 2 --threads 8 \
      --access-logfile - --error-logfile -'
```

จากอีกเทอร์มินัล รัน workload เดิมที่ 25 คน

```bash
run_dir="results/gunicorn-25-$(date -u +%Y%m%dT%H%M%SZ)"
python3 scripts/load_chat.py --base-url http://127.0.0.1:8001 \
  --users 25 --vm-metrics --p95-limit-ms 15000 --output "$run_dir/chat.csv"
docker logs --timestamps bem-gunicorn-test > "$run_dir/backend.log" 2>&1
```

Gunicorn ชุดนี้มี 16 request threads ผู้ใช้ที่เกินจะรอ จึงอาจเห็น p95 เพิ่มแม้ได้คำตอบครบ
เทียบจำนวนคำตอบ, connection failures, HTTP 500 และ p95 กับ baseline 25 คน แล้วตรวจ PostgreSQL log
ในช่วงเวลาเดียวกันประกอบ คง `max_connections` ที่ 100 และขนาด VM เดิมในรอบเปรียบเทียบนี้

### อ่านเวลาของแต่ละช่วง

หลัง build backend จากโค้ดล่าสุด และรันสคริปต์เวอร์ชันเดียวกัน รอบ 25 คนจะได้เวลาจาก `Server-Timing`
เพิ่มใน CSV และค่า p95 ของแต่ละช่วงในไฟล์สรุป

| คอลัมน์ | ช่วงที่วัด |
| --- | --- |
| `agent_ms` | เวลารวมใน `run_agent` รวมการตั้งค่า DSPy, การเรียกโมเดล และการแปลงผล |
| `chat_view_ms` | เวลารวมใน view ของ Django |
| `view_other_ms` | เวลาที่เหลือใน view หลังหักการเรียก agent รวมฐานข้อมูลและตรรกะของแชต |
| `outside_view_ms` | เวลาฝั่ง client หลังหักเวลา view รวม middleware, คิว web server และ HTTP overhead |

เทียบคอลัมน์ในแถวเดียวกันของคำขอที่ช้าเพื่อดูว่าช้าในช่วงไหน ค่า p95 ของแต่ละคอลัมน์อาจมาจากคนละคำขอ
เมื่อ backend รุ่นเก่าไม่ส่ง header คอลัมน์เวลารายช่วงจะว่าง

เมื่อ CSV มี `lm_calls` และ `lm_call_durations_ms` ค่าจะแสดงจำนวนครั้งที่ DSPy เรียก LM
และเวลาของแต่ละครั้งตามลำดับ โดยนับที่ขอบเขต DSPy LM การ retry ภายในครั้งเดียว
หรือ cache hit อาจไม่ตรงกับจำนวน HTTP requests ที่ถึงผู้ให้บริการ
