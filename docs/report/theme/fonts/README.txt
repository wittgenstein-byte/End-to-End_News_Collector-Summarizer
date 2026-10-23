ฟอนต์ที่แนบมากับ template (theme/fonts)
==========================================

THSarabunNew-Regular/Bold/Italic/BoldItalic.ttf
  TH Sarabun New เวอร์ชัน 1.3 (2011)
  Copyright (c) 2010-2011 Software Industry Promotion Agency (SIPA)
  สัญญาอนุญาต: GNU GPL รุ่น 2 หรือใหม่กว่า พร้อมข้อยกเว้นสำหรับฟอนต์ (font exception)
  ใช้เป็นฟอนต์หลักของเอกสาร ตามคู่มือการจัดทำเอกสารโครงงานข้อ 5
  (template รุ่นก่อนใช้ชื่อไฟล์ Sarabun-*.ttf แต่ภายในเป็นฟอนต์เดียวกัน)

TlwgMonoTH-Regular/Bold/Oblique/BoldOblique.ttf
  ฟอนต์ความกว้างคงที่สำหรับโค้ดและคำสั่ง (\texttt, listings, \cmd)
  ดัดแปลงจาก TlwgMono เวอร์ชัน 002.003 ของ Thai Linux Working Group
  Copyright (C) 2003 Poonlap Veerathanabutr
  ต้นฉบับ: https://github.com/tlwg/fonts-tlwg
  สัญญาอนุญาต: GNU GPL รุ่น 2 หรือใหม่กว่า พร้อม font exception (คงข้อยกเว้นไว้)

  การดัดแปลง (15 ต.ค. 2026) ทำด้วยสคริปต์ fixmono.py ในโฟลเดอร์นี้
    - สระบน สระล่าง และวรรณยุกต์ (U+0E31, U+0E34-0E3A, U+0E47-0E4E และรูปแปรใน
      PUA U+F700-F71A) ให้มีความกว้างเป็น 0 และย้ายรูปอักษรไปวางบนพยัญชนะตัวหน้า
    - ลบตาราง GSUB/GPOS เพื่อให้ XeTeX (HarfBuzz) จัดตำแหน่งสระและวรรณยุกต์ด้วย
      Thai PUA shaping
    - เปลี่ยนชื่อ family เป็น TlwgMonoTH เพื่อไม่ให้สับสนกับฟอนต์ต้นฉบับ
  เหตุผล: TlwgMono ต้นฉบับกำหนดความกว้างของสระและวรรณยุกต์ไว้ 1 ช่อง
  เมื่อพิมพ์ด้วย XeTeX สระและวรรณยุกต์จึงแยกออกจากพยัญชนะ เช่น "ส ุ่ ม"

ข้อยกเว้นสำหรับฟอนต์ (font exception) ทำให้นำฟอนต์ไปฝังใน PDF ของเล่มรายงาน
ได้โดยเล่มรายงานไม่ต้องอยู่ภายใต้สัญญาอนุญาต GPL


Fonts bundled with the template
-------------------------------
TH Sarabun New 1.3 (SIPA) and TlwgMono 002.003 (TLWG), both GPL-2+ with font
exception. TlwgMonoTH is a modified TlwgMono (2026-10-15, see fixmono.py):
Thai combining marks set to zero advance width and moved over the preceding
base glyph; GSUB/GPOS removed so HarfBuzz applies Thai PUA shaping; family
renamed to TlwgMonoTH. The font exception is kept for the modified version.
