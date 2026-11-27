import os
from typing import Literal

import dspy
from pydantic import BaseModel

from .routing import CATALOG, POLICY


AGENT_PROFILE = {
    "name": "BEM Care",
    "role": "ผู้ช่วยรับแจ้งเหตุ BEM",
    "organization": "Bangkok Expressway and Metro Public Company Limited (BEM)",
    "gender": "Male",
    "pronoun": "ผม",
    "personality": "สุภาพ สุขุม ใจเย็น ชัดเจน และใส่ใจความปลอดภัย",
    "mission": "รับเรื่อง เปิดเคส และช่วยเก็บรายละเอียดที่จำเป็นโดยไม่ถามซ้ำ",
}

TAXONOMY = {
    "กลยุทธ์และธุรกิจ": (
        "สัมปทาน นโยบายรัฐ และธรรมาภิบาล", "จริยธรรมและการทุจริต",
        "ชุมชน สิ่งแวดล้อม และสิทธิมนุษยชน", "โครงการลงทุนและการขยายธุรกิจ",
    ),
    "ปฏิบัติการและการจัดการ": (
        "ความพร้อมให้บริการรถไฟฟ้า", "การให้บริการทางพิเศษ",
        "สินทรัพย์ การบำรุงรักษา และผู้รับเหมา", "ความปลอดภัยของผู้ใช้บริการและพนักงาน",
        "ลูกค้าและประสบการณ์การใช้บริการ", "เทคโนโลยีและไซเบอร์",
        "ภัยภายนอกและความต่อเนื่องทางธุรกิจ",
    ),
    "การเงิน": ("รายได้", "ตลาดการเงิน"),
    "การปฏิบัติตามกฎเกณฑ์": ("กฎหมายและสัญญาสัมปทาน",),
}
LEVEL_1_BY_LEVEL_2 = {level_2: level_1 for level_1, groups in TAXONOMY.items() for level_2 in groups}
TAXONOMY_TEXT = "\n".join(f"- {level_1}: {', '.join(groups)}" for level_1, groups in TAXONOMY.items())


class AgentResult(BaseModel):
    reply: str
    flow_state: Literal["COLLECTING", "CONFIRMING", "SUBMITTED"]
    should_open_case: bool = False
    category_level_1: str = ""
    category_level_2: str = ""
    title: str = ""
    description: str = ""
    service_area: str = ""
    location: str = ""
    occurred_at: str = ""
    occurred_at_normalized: str = ""
    routing_category: str = ""
    impact: str = ""
    contact: str = ""
    urgency: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"


class BEMIncidentSignature(dspy.Signature):
    """คุณคือ BEM Care ผู้ช่วยรับแจ้งเหตุของบริษัท ทางด่วนและรถไฟฟ้ากรุงเทพ จำกัด (มหาชน)

    Persona: คุณเป็นผู้ชาย ใช้สรรพนามแทนตัวเองว่า “ผม” เสมอ ห้ามใช้ “ฉัน” หรือคำลงท้าย “ค่ะ/คะ”
    บุคลิก: สุภาพ สงบ มืออาชีพ เห็นอกเห็นใจ ใช้คำลงท้าย “ครับ” อย่างเป็นธรรมชาติ
    และให้ความปลอดภัยมาก่อน ไม่กล่าวโทษผู้แจ้ง
    ขอบเขต: รับเหตุเกี่ยวกับทางพิเศษ รถไฟฟ้า สถานี ขบวนรถ ระบบชำระเงิน ทรัพย์สิน
    บุคลากร ผู้รับเหมา เทคโนโลยี ความปลอดภัย และผลกระทบต่อชุมชนของ BEM

    Flow:
    เปิดเคสเมื่อผู้ใช้แจ้ง “เหตุหรือปัญหาที่เกิดขึ้นจริง” แล้วเท่านั้น
    ถ้าเป็นเพียงคำทักทาย ขอบคุณ ทดลองระบบ หรือคำถามทั่วไป ให้ should_open_case=false
    และตอบสนทนาตามปกติโดยห้ามกล่าวว่าเปิดเคส ห้ามกล่าวถึง Ticket ID และห้ามสร้างเหตุสมมติ
    หากเป็นปัญหาส่วนตัวหรือเรื่องอื่นที่ไม่เกี่ยวกับ BEM ทางพิเศษ รถไฟฟ้า หรือองค์กร
    ให้ should_open_case=false และคืน category_level_1/category_level_2 เป็นค่าว่าง
    เมื่อมีรายละเอียดปัญหาจริง ให้ should_open_case=true ตอบรับทราบก่อน แล้วจึงถามข้อมูลเพิ่ม
    Ticket ID ออกโดย backend เท่านั้น ห้ามสร้าง คาดเดา หรือเขียน Ticket ID ใน reply ทุกกรณี
    แม้ input ticket_id จะมีค่า ก็ไม่ต้องกล่าวถึง เพราะระบบจะแทรกหมายเลขจริงให้ภายหลัง
    ห้ามชะลอการเปิดเคสเพื่อรอข้อมูลครบ และห้ามถามซ้ำสิ่งที่มีอยู่ใน current_case หรือ chat_history
    ถามเพิ่มครั้งละ 1 ประเด็น และถามได้เฉพาะรายการใน missing_fields เท่านั้น

    - COLLECTING: เก็บเฉพาะสาระสำคัญที่ยังขาด ได้แก่ บริการ/พื้นที่, ตำแหน่ง,
      วันเวลา, ผลกระทบหรือผู้ได้รับอันตราย และช่องทางติดต่อ (ช่องทางติดต่อเป็นข้อมูลสมัครใจ)
    - CONFIRMING: เมื่อข้อมูลจำเป็นครบ ให้สรุปเป็นข้อสั้นๆ พร้อม taxonomy 2 ระดับ แล้วถามยืนยัน
    ถ้ายังไม่มีหมุด แนะนำให้กด “เลือกบนแผนที่” ในการ์ดจุดเกิดเหตุเพื่อปักหมุดก่อนยืนยัน
    ใช้ตำแหน่งที่ผู้แจ้งบอก เก็บชื่อสถานี ด่าน หรือจุดสังเกตตามจริง และห้ามเดาพิกัด
    - SUBMITTED: ใช้เมื่อผู้ใช้ยืนยันสรุปอย่างชัดเจนแล้วเท่านั้น กล่าวว่ารับเรื่องพร้อม Ticket ID

    ถามครั้งละไม่เกิน 2 คำถาม ไม่ถามซ้ำ ไม่แต่งข้อมูล ไม่อ้างว่าติดต่อเจ้าหน้าที่แล้ว
    จัด taxonomy ภาษาไทยจากรายการที่กำหนดเท่านั้น หากยังไม่แน่ใจให้เลือกกลุ่มที่ใกล้ที่สุด
    หากมีไฟไหม้ ควัน อุบัติเหตุ ผู้บาดเจ็บ หรืออันตรายเร่งด่วน ให้แนะนำให้ออกจากพื้นที่เสี่ยง
    แจ้งเจ้าหน้าที่ ณ จุดเกิดเหตุ/กดอุปกรณ์ฉุกเฉิน และโทรบริการฉุกเฉินที่เกี่ยวข้องทันที
    """

    ticket_id: str = dspy.InputField(desc="Ticket ID ของการสนทนานี้")
    case_status: str = dspy.InputField(desc="สถานะเคสปัจจุบัน")
    current_case: str = dspy.InputField(desc="ข้อมูลเคสที่เก็บไว้แล้ว")
    missing_fields: str = dspy.InputField(desc="ข้อมูลสำคัญที่ยังขาด ให้ถามจากรายการนี้เท่านั้น")
    taxonomy: str = dspy.InputField(desc="taxonomy ระดับ 1 และระดับ 2 ที่อนุญาต")
    routing_catalog: str = dspy.InputField(desc="รหัสหมวดละเอียดสำหรับจับคู่ทีมและ SLA")
    chat_history: str = dspy.InputField(desc="ประวัติสนทนาก่อนหน้า")
    user_message: str = dspy.InputField(desc="ข้อความล่าสุดจากผู้ใช้")
    reply: str = dspy.OutputField(desc="คำตอบภาษาไทยสุภาพ กระชับ และห้ามมี Ticket ID เพราะ backend จะเพิ่มให้")
    should_open_case: bool = dspy.OutputField(desc="true เฉพาะเมื่อข้อความเป็นการแจ้งเหตุหรือปัญหาจริง")
    flow_state: Literal["COLLECTING", "CONFIRMING", "SUBMITTED"] = dspy.OutputField()
    category_level_1: str = dspy.OutputField(desc="taxonomy ระดับ 1 ภาษาไทย")
    category_level_2: str = dspy.OutputField(desc="taxonomy ระดับ 2 ภาษาไทย")
    title: str = dspy.OutputField(desc="ชื่อเหตุสั้นๆ ภาษาไทย")
    description: str = dspy.OutputField(desc="ข้อเท็จจริงของเหตุ ห้ามคาดเดา")
    service_area: str = dspy.OutputField(desc="Expressway, Rail, Corporate หรือ Unknown")
    location: str = dspy.OutputField(desc="สถานี ด่าน ทางพิเศษ กม. ช่องทาง หรือจุดเกิดเหตุ")
    occurred_at: str = dspy.OutputField(desc="วันเวลาที่เกิดเหตุตามที่ผู้ใช้แจ้ง เก็บข้อความต้นฉบับรวมถึงเวลาคร่าว ๆ")
    routing_category: str = dspy.OutputField(
        desc="รหัสเดียวจาก routing_catalog ที่ตรงกับข้อเท็จจริงของเหตุ ถ้าข้อมูลไม่พอหรือไม่มีหมวดตรงให้คืนค่าว่าง"
    )
    occurred_at_normalized: str = dspy.OutputField(
        desc="ISO 8601 พร้อม offset เมื่อผู้แจ้งระบุวันปฏิทินและเวลาได้ชัดเจนเท่านั้น "
        "ใช้ +07:00 สำหรับเวลาท้องถิ่นไทย ถ้ารู้เพียงช่วงเวลาคร่าว ๆ หรือข้อมูลไม่ครบให้คืนค่าว่าง ห้ามเดา"
    )
    impact: str = dspy.OutputField(desc="ผลกระทบ ผู้บาดเจ็บ หรือการหยุดชะงัก")
    contact: str = dspy.OutputField(desc="ช่องทางติดต่อที่ผู้ใช้สมัครใจให้")
    urgency: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = dspy.OutputField()


def _case_text(case) -> str:
    fields = (
        "flow_state", "category_level_1", "category_level_2", "title", "description",
        "service_area", "location", "occurred_at", "impact", "contact", "urgency",
    )
    details = [f"{field}: {getattr(case, field) or '-'}" for field in fields]
    has_pin = getattr(case, "latitude", None) is not None and getattr(case, "longitude", None) is not None
    details.append(f"map_pin_confirmed: {has_pin}")
    normalized = getattr(case, "occurred_at_normalized", None)
    details.append(f"occurred_at_normalized: {normalized.isoformat() if normalized else '-'}")
    return "\n".join(details)


def _missing_fields(case) -> str:
    required = {
        "description": "รายละเอียดว่าเกิดอะไรขึ้น",
        "service_area": "บริการที่เกี่ยวข้อง (ทางพิเศษ/รถไฟฟ้า/องค์กร)",
        "location": "ตำแหน่งที่เกิดเหตุ",
        "occurred_at": "วันหรือเวลาที่เกิดเหตุ",
        "impact": "ผลกระทบหรือผู้ได้รับอันตราย",
    }
    missing = [label for field, label in required.items() if not getattr(case, field)]
    return ", ".join(missing) or "ไม่มี — ให้สรุปข้อมูลเพื่อขอการยืนยัน"


def run_agent(*, case, history: str, message: str) -> AgentResult:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    lm = dspy.LM(os.getenv("GEMINI_MODEL", "gemini/gemini-2.5-flash"), api_key=api_key, temperature=0.7)
    with dspy.context(lm=lm):
        raw = dspy.Predict(BEMIncidentSignature)(
            ticket_id=case.ticket_id, case_status=case.status, current_case=_case_text(case),
            missing_fields=_missing_fields(case),
            taxonomy=TAXONOMY_TEXT, routing_catalog=CATALOG, chat_history=history or "ยังไม่มีประวัติการสนทนา",
            user_message=message,
        )
    data = {field: getattr(raw, field, "") for field in AgentResult.model_fields}
    result = AgentResult.model_validate(data)
    result.routing_category = result.routing_category.strip().upper()
    if result.routing_category not in POLICY:
        result.routing_category = ""
    if result.category_level_2 in LEVEL_1_BY_LEVEL_2:
        result.category_level_1 = LEVEL_1_BY_LEVEL_2[result.category_level_2]
    elif result.category_level_1 not in TAXONOMY:
        result.category_level_1 = result.category_level_2 = ""
    elif result.category_level_2 not in TAXONOMY[result.category_level_1]:
        result.category_level_2 = ""
    return result
