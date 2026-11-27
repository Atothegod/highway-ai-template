"""Initial assignment policy from BEM_GRC_SLA_and_Responsibility.md §1 and §2."""
from datetime import timedelta

POLICY = {'T01.01': ('Signaling & 750 VDC Power Fault / ระบบอาณัติสัญญาณและจ่ายไฟขัดข้อง', 'RAIL-ME', 'สูง', 72),
 'T01.02': ('Platform Screen Door (PSD) Fault / ประตูกั้นชานชาลาขัดข้อง', 'RAIL-ME', 'ปานกลาง', 168),
 'T01.03': ('Train Delay & Headway Disruption / ขบวนรถล่าช้าและจอดแช่หลายสถานี', 'RAIL-OPS', 'สูง', 72),
 'T01.04': ('Purple Line Fleet Capacity Readiness / ความเพียงพอขบวนรถสายสีม่วง', 'RAIL-OPS', 'ปานกลาง', 168),
 'T02.01': ('Easy Pass & Toll Plaza Bottleneck / คอขวดช่อง Easy Pass หน้าด่าน', 'EXP-TOLL', 'สูง', 72),
 'T02.02': ('Toll Collection & Balance Sync Fault / ระบบเก็บค่าผ่านทางและตัดยอดขัดข้อง',
            'EXP-TOLL',
            'ปานกลาง',
            168),
 'T03.01': ('Viaduct, Tunnel & Expansion Joint Defect / โครงสร้างทางวิ่งและรอยต่อชำรุด', 'CIVIL-ENG', 'สูง', 72),
 'T03.02': ('Gen-1 Rolling Stock & HVAC Leak / ขบวนรถรุ่นแรกเสียบ่อยและน้ำแอร์รั่ว', 'RAIL-ME', 'ปานกลาง', 168),
 'T03.03': ('M&E Contractor SLA Non-Compliance / ผู้รับเหมาหลักงานระบบผิดสัญญา', 'RAIL-ME', 'ปานกลาง', 168),
 'T04.01': ('Station & Escalator Passenger Safety / ความปลอดภัยผู้โดยสารและบันไดเลื่อน', 'RAIL-OPS', 'สูง', 72),
 'T04.02': ('Track/Tunnel Smoke & Fire Emergency / เหตุไฟไหม้รางหรือควันในอุโมงค์', 'RAIL-OPS', 'สูง', 72),
 'T04.03': ('Expressway Accident & Rescue >12 Min / อุบัติเหตุทางพิเศษและกู้ภัยเกิน 12 นาที',
            'EXP-OPS',
            'สูง',
            72),
 'T04.04': ('Night Maintenance Worker Safety / ความปลอดภัยงานซ่อมบำรุงกลางคืน', 'SHE-BCP', 'สูง', 72),
 'T04.05': ('Monsoon Station Flood & Seismic BCP / น้ำท่วมทางเข้าสถานีและแผ่นดินไหว', 'SHE-BCP', 'สูง', 72),
 'T04.06': ('Third-Party Adjacent Construction Impact / งานก่อสร้างบุคคลภายนอกเชื่อมสถานี',
            'CIVIL-ENG',
            'สูง',
            72),
 'T05.01': ('EMV Switchover & Bank Gateway Outage / การเปลี่ยนระบบบัตร EMV และเกตเวย์ล่ม', 'RAIL-AFC', 'สูง', 72),
 'T05.02': ('Interchange Rush-Hour Overcrowding / ความแออัดสถานีเปลี่ยนถ่ายช่วงเร่งด่วน', 'RAIL-OPS', 'สูง', 72),
 'T05.03': ('Staff Conduct & Repeat VOC Complaint / พฤติกรรมพนักงานและข้อร้องเรียนซ้ำ', 'CRM-VOC', 'ปานกลาง', 168),
 'T06.01': ('Cyber Threat, OT Separation & AI Guardrail / ภัยไซเบอร์และธรรมาภิบาล AI', 'IT-CYBER', 'ปานกลาง', 168),
 'T06.02': ('Human Rights & PDPA Privacy Violation / การละเมิดสิทธิมนุษยชนและข้อมูลส่วนบุคคล',
            'LEGAL-CMP',
            'ปานกลาง',
            168),
 'T07.01': ('Fare & Toll Tariff Adjustment VOC / การปรับอัตราค่าโดยสารและค่าผ่านทาง', 'FIN-TREAS', 'ปานกลาง', 168),
 'T07.02': ('State 20/50 THB Fare-Cap & FX Exposure / นโยบายค่าโดยสารรัฐและตลาดการเงิน', 'FIN-TREAS', 'สูง', 72),
 'T08.01': ('Concession Governance & Bidding Dispute / ธรรมาภิบาลสัมปทานและคดีประมูล',
            'LEGAL-CMP',
            'ปานกลาง',
            168),
 'T08.02': ('Community EIA, Orange Line & Double Deck / ชุมชนสิ่งแวดล้อมและโครงการลงทุนใหม่',
            'CIVIL-ENG',
            'สูง',
            72)}

TEAMS = {'EXEC-BOD': 'บริหารสูงสุดและกลยุทธ์องค์กร',
 'GRC-RM': 'บรรษัทภิบาลและบริหารความเสี่ยง',
 'LEGAL-CMP': 'กฎหมาย คุ้มครองข้อมูล และสัญญาสัมปทาน',
 'FIN-TREAS': 'การเงิน บัญชี และบริหารเงินคงคลัง',
 'IT-CYBER': 'เทคโนโลยีสารสนเทศและความมั่นคงไซเบอร์',
 'CRM-VOC': 'ลูกค้าสัมพันธ์และศูนย์บริการผู้ใช้บริการ',
 'COMM-BMN': 'พัฒนาเชิงพาณิชย์และสื่อโฆษณา',
 'RAIL-OPS': 'ปฏิบัติการเดินรถไฟฟ้าและสถานี',
 'RAIL-ME': 'ซ่อมบำรุงอาณัติสัญญาณ จ่ายไฟ และขบวนรถ',
 'RAIL-AFC': 'ระบบจัดเก็บค่าโดยสารอัตโนมัติและ EMV',
 'EXP-OPS': 'ควบคุมจราจรและกู้ภัยทางพิเศษ',
 'EXP-TOLL': 'จัดเก็บค่าผ่านทางและระบบ Easy Pass',
 'CIVIL-ENG': 'วิศวกรรมโครงสร้างโยธาและโครงการลงทุน',
 'SHE-BCP': 'ความปลอดภัย สิ่งแวดล้อม และ BCP'}

CATEGORY_CHOICES = [(code, f"{code} · {name.split(' / ')[-1]}") for code, (name, *_) in POLICY.items()]
TEAM_CHOICES = list(TEAMS.items())
CATALOG = "\n".join(f"{code}: {name}" for code, (name, *_) in POLICY.items())


def apply_initial_routing(case, now, *, rematch=False):
    """Apply defaults after submission and when staff changes the matched category."""
    if case.flow_state != "SUBMITTED":
        return []
    changed = []
    if not case.grc_handoff_status:
        case.grc_handoff_status = "PENDING"
        changed.append("grc_handoff_status")
    policy = POLICY.get(case.routing_category)
    if not policy:
        return changed
    _, team, _, hours = policy
    if not case.assigned_team:
        case.assigned_team, case.assigned_at = team, now
        changed.extend(("assigned_team", "assigned_at"))
    if case.sla_due_at is None or rematch:
        case.sla_due_at = (case.received_at or case.created_at) + timedelta(hours=hours)
        changed.append("sla_due_at")
    return changed
