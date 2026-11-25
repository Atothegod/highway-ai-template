from django.db import migrations


LEVEL_1 = {
    "Strategic & Business": "กลยุทธ์และธุรกิจ",
    "Operations & Management": "ปฏิบัติการและการจัดการ",
    "Financial": "การเงิน",
    "Compliance": "การปฏิบัติตามกฎเกณฑ์",
}
LEVEL_2 = {
    "Government Concession, Policy & Governance": "สัมปทาน นโยบายรัฐ และธรรมาภิบาล",
    "Ethics & Corruption": "จริยธรรมและการทุจริต",
    "Community, Environment & Human Rights": "ชุมชน สิ่งแวดล้อม และสิทธิมนุษยชน",
    "Investment Projects & Business Expansion": "โครงการลงทุนและการขยายธุรกิจ",
    "Rail Service Availability": "ความพร้อมให้บริการรถไฟฟ้า",
    "Expressway Service Delivery": "การให้บริการทางพิเศษ",
    "Assets, Maintenance & Contractors": "สินทรัพย์ การบำรุงรักษา และผู้รับเหมา",
    "Passenger, Road User & Employee Safety": "ความปลอดภัยของผู้ใช้บริการและพนักงาน",
    "Customer & Service Experience": "ลูกค้าและประสบการณ์การใช้บริการ",
    "Technology & Cybersecurity": "เทคโนโลยีและไซเบอร์",
    "External Threats & Business Continuity": "ภัยภายนอกและความต่อเนื่องทางธุรกิจ",
    "Revenue": "รายได้",
    "Financial Markets": "ตลาดการเงิน",
    "Laws & Concession Agreements": "กฎหมายและสัญญาสัมปทาน",
}


def translate(apps, schema_editor):
    incident = apps.get_model("chat", "IncidentReport")
    for old, new in LEVEL_1.items():
        incident.objects.filter(category_level_1=old).update(category_level_1=new)
    for old, new in LEVEL_2.items():
        incident.objects.filter(category_level_2=old).update(category_level_2=new)


class Migration(migrations.Migration):
    dependencies = [("chat", "0001_initial")]
    operations = [migrations.RunPython(translate, migrations.RunPython.noop)]
