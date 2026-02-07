from uuid import UUID
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, ConfigDict

class UserBase(BaseModel):
    email: EmailStr

class FolderData(BaseModel):
    folderId: str
    googleToken: str
    description: str

class UserCreate(UserBase):
    password: str

class FolderLinkRequest(BaseModel):
    userId: UUID
    folderId: str
    email: Optional[EmailStr] = None

class AnalysisResponse(BaseModel):
    id: UUID
    status: str
    filename: str
    created_at: datetime
    details: Optional[dict] = None
    candidate_info: Optional[dict] = None
    match_score: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)

class UserResponse(UserBase):
    id: UUID
    updated_at: datetime
    linked_folder_ids: List[str] = []
    processed_filenames: List[str] = []
    analyses: List[AnalysisResponse] = [] 
    model_config = ConfigDict(from_attributes=True)

class LatestFolderResponse(BaseModel):
    latest_folder_id: Optional[str] = None

class VideoIngestRequest(BaseModel):
    url: str
    user_id: str

class StatusUpdate(BaseModel):
    source_id: str
    status: str

class ChatRequest(BaseModel):
    question: str
    source_id: str
    conversation_id: Optional[str] = None

class ChunkData(BaseModel):
    content: str
    embedding: List[float]

class SyncRequest(BaseModel):
    source_id: str
    chunks: List[ChunkData]

class ConnectData(BaseModel):
    email: str
    password: str

class SourceSchema(BaseModel):
    id: UUID
    source_name: str
    source_type: str
    status: str
    created_at: datetime