import pymupdf
import os

pdf_file_path="chap04/data/[어센트 내부공유용] 브랜드 파워 강화_지명검색 마케팅_240207 (1).pdf"
doc=pymupdf.open(pdf_file_path)

full_text=''

for page in doc:
    text=page.get_text()
    full_text += text

pdf_file_name=os.path.basename(pdf_file_path)
pdf_file_name=os.path.splitext(pdf_file_name)[0]

txt_file_path=f"chap04/output/{pdf_file_name}.txt"
with open(txt_file_path,'w',encoding='utf-8') as f:
    f.write(full_text)