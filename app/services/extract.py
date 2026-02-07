import io
import re
from PyPDF2 import PdfReader
from docx import Document

def text(content: bytes, mime_type: str) -> str:
    text = ""
    try:
        if not content: return ""
        stream = io.BytesIO(content)
        
        if "pdf" in mime_type:
            reader = PdfReader(stream)
            text = " ".join([p.extract_text() for p in reader.pages if p.extract_text()])
        elif "wordprocessingml" in mime_type or "docx" in mime_type:
            doc = Document(stream)
            text = " ".join([para.text for para in doc.paragraphs if para.text])
        else:
            text = content.decode("utf-8", errors="ignore")
            
    except Exception as e:
        raise Exception(f"Extraction Error: {str(e)}")

    pattern = r'[a-zA-Z0-9]+(?:[\+#\-\/][a-zA-Z0-9]+|[\+#]+)?'

    clean_tokens = re.findall(pattern, text)
    result = " ".join(clean_tokens)
    return result