from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import app.services.driveServices as driveServices
import app.services.extract as extract

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
        file_types = [
            "application/pdf",
            "text/plain",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword"
        ]

        mime_query = " or ".join([f"mimeType = '{t}'" for t in file_types])

        query = f"'{folderId}' in parents and ({mime_query}) and trashed = false"
    
        results = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType, size)",
            pageSize=100
        ).execute()
        
        items = results.get('files', [])

        if not items:
            return {"message": "No files found in this folder."}

        all_extracted_data = []

        for file in items:
            try:
                
                file_content_bytes = service.files().get_media(fileId=file["id"]).execute()

                word_array = extract.text(file_content_bytes, file["mimeType"])
                
                all_extracted_data.append({
                    "fileName": file['name'],
                    "content": word_array
                })

                print(f"Processed: ({file['id']})")

            except Exception as e:
                print(f"Failed to process {file['name']}: {e}")
                continue

        print(all_extracted_data)
        return {"status": "success", "data": all_extracted_data}

    except Exception as e:
        return {"error": str(e)}