import io
from PyPDF2 import PdfReader
from docx import Document

def text(file_bytes, mime_type):
    stream = io.BytesIO(file_bytes)
    raw_text = ""
    
    if mime_type == "application/pdf":
        reader = PdfReader(stream)
        raw_text = " ".join([page.extract_text() or "" for page in reader.pages])
        
    elif mime_type == "text/plain":
        raw_text = file_bytes.decode("utf-8", errors="ignore")
        
    elif mime_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        doc = Document(stream)
        raw_text = " ".join([para.text for para in doc.paragraphs])

    return raw_text.split()