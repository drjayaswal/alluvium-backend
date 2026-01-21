from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import app.services.driveServices as driveServices

class Settings(BaseSettings):
    frontend_url: str
    model_config = SettingsConfigDict(env_file=".env")

@lru_cache
def get_settings():
    return Settings()

app = FastAPI()

current_settings = get_settings() 

app.add_middleware(
    CORSMiddleware,
    allow_origins=[current_settings.frontend_url], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Welcome"}

@app.get("/get-folder/{folderId}")
def getFolderId(folderId: str, service=Depends(driveServices.get_drive_service)):
    try:
        pdf_mime = "application/pdf"
        docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        
        # Build the query: folder parent AND (is PDF OR is DOCX) AND not trashed
        query = (
            f"'{folderId}' in parents and "
            f"(mimeType = '{pdf_mime}' or mimeType = '{docx_mime}') and "
            "trashed = false"
        )
        results = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType, size)",
            pageSize=100
        ).execute()
        
        items = results.get('files', [])
        return {"files": items}
    except Exception as e:
        return {"error": str(e)}