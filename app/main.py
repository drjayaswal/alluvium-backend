import uuid
import httpx
import logging
import asyncio
import app.services.extract as extract

from typing import List
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm.attributes import flag_modified
from fastapi_mail import FastMail, MessageSchema, MessageType
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Form, FastAPI, UploadFile, File, HTTPException, Depends, Security, BackgroundTasks

import app.services.extract as extract

from app.config import settings
from app.db.models import User, Source
from app.lib.aws_client import s3_client
from contextlib import asynccontextmanager
from app.db.connect import init_db, get_db
from app.lib.aws_client import upload_to_s3
from app.lib.mail_client import conf, create_html_body, create_resolve_html_body
from app.db.cruds import create_file_record, get_or_create_source
from app.lib.auth_client import hash_password, verify_password, create_access_token, decode_token
from app.db.models import ResumeAnalysis, AnalysisStatus, SourceChunk, ChatMessage, Conversation,Feedback
from app.services.ml_process import ml_analysis_s3, ml_analysis_drive, ml_health_check, ml_analysis_video, ml_analysis_document
from app.db.schemas import FolderDataSchema, AnalysisResponseSchema,StatusUpdateSchema, VideoIngestRequestSchema, SyncRequestSchema, ConnectDataSchema, SourceSchema, ChatRequestSchema, FeedbackSchema, FeedbackResolveSchema

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

security = HTTPBearer()
get_settings = settings()
app = FastAPI(lifespan=lifespan)
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        get_settings.FRONTEND_URL,
        get_settings.NEXT_PUBLIC_FRONTEND_URL
        ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Startup Route ---
@app.on_event("startup")
# async def startup_event():
#     # Fire and forget: send a ping to ML server when Backend starts
#     # This begins the ML wake-up process immediately
#     asyncio.create_task(ml_health_check(max_retries=1, delay=0))

# --- Auth Dependency ---
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security), 
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    
    user = db.query(User).filter(User.email == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found")
    return user

# --- Helper Logic: Persistence ---
def save_to_history(background_tasks: BackgroundTasks,db: Session, user: User, new_results: List[dict]):
    if not new_results:
        return
    current_history = list(user.analysis_history or [])
    updated_history = (new_results + current_history)[:100]
    user.analysis_history = updated_history
    new_filenames = [r["filename"] for r in new_results]
    user.processed_filenames = (list(user.processed_filenames or []) + new_filenames)[-100:]
    flag_modified(user, "analysis_history")
    flag_modified(user, "processed_filenames")
    
    db.commit()
    db.refresh(user)

# --- Root Routes ---
@app.get("/")
async def read_root():
    return {"status": "Alluvium Backend is running..."}
@app.get("/health")
async def health_check():
    return {"service":"Backend","status": "healthy", "active":True}
@app.get("/ml-server/health")
async def health_check():
    is_awake = await ml_health_check()
    return {"service":"ML Server", "status": "healthy" if is_awake else "unhealthy", "active":is_awake}

# --- Authentication Routes ---
@app.post("/connect")
async def connect(background_tasks: BackgroundTasks,data: ConnectDataSchema, db: Session = Depends(get_db)):
    #   background_tasks.add_task(ml_health_check)
    user = db.query(User).filter(User.email == data.email).first()

    if user:
        if verify_password(data.password, user.hashed_password):
            token = create_access_token(data={"sub": user.email})
            return {
                "success": True, 
                "token": token,
                "email": user.email,
                "id": str(user.id)
            }
        raise HTTPException(status_code=401, detail="Incorrect password")
    new_user = User(
        email=data.email, 
        hashed_password=hash_password(data.password),
        linked_folder_ids=[],
        processed_filenames=[]
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    token = create_access_token(data={"sub": new_user.email})
    return {
        "success": True,
        "token": token,
        "email": new_user.email,
        "id": str(new_user.id)
    }
@app.get("/auth/me")
async def get_me(background_tasks: BackgroundTasks,current_user: User = Depends(get_current_user)):
    #   background_tasks.add_task(ml_health_check)
    return {
        "email": current_user.email,
        "id": str(current_user.id),
        "updated_at": str(current_user.updated_at),
        "authenticated": True,
        "credits": current_user.credits,
        "total_conversations": len(current_user.conversations)
        }

# --- Updation Routes ---
@app.patch("/update-source-status")
async def update_source_status(data: StatusUpdateSchema, db: Session = Depends(get_db)):
    """Called by ML server when processing completes; no user auth."""
    src = db.query(Source).filter(Source.id == data.source_id).first()
    if src:
        src.status = AnalysisStatus(data.status)
        db.commit()
        return {"message": "updated"}
    raise HTTPException(status_code=404, detail="Source not found")


@app.post("/update-source-chunks")
async def update_source_chunks(data: SyncRequestSchema, db: Session = Depends(get_db)):
    """Called by ML server to sync chunks; no user auth."""
    try:
        source_uuid = uuid.UUID(str(data.source_id))

        existing_source = db.query(Source).filter(Source.id == source_uuid).first()
        if not existing_source:
            raise HTTPException(status_code=404, detail="Source record not found")

        db.query(SourceChunk).filter(SourceChunk.source_id == source_uuid).delete()

        new_chunks = []
        for item in data.chunks:
            chunk_obj = SourceChunk(
                source_id=source_uuid,
                content=item.content,
                embedding=item.embedding,
                status=AnalysisStatus.COMPLETED 
            )
            new_chunks.append(chunk_obj)
        
        db.add_all(new_chunks)

        existing_source.status = AnalysisStatus.COMPLETED
        
        db.commit()
        return {
            "status": "success",
            "count": len(new_chunks),
            "source_id": str(source_uuid)
        }

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database Sync Failed")
@app.get("/get-sources", response_model=List[SourceSchema])
async def get_user_sources(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        sources = (
            db.query(Source)
            .filter(Source.user_id == current_user.id)
            .order_by(Source.created_at.desc())
            .all()
        )
        return sources
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not fetch sources from database")

# --- Ingestion Routes ---
@app.post("/ingest-video")
async def ingest_video(
    request: VideoIngestRequestSchema, 
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.credits <= 0:
        return {"message": "You have 0 Credits left"}
    
    user_prefix = current_user.email.split("@")[0]
    filename = request.url.split("/")[-1] 
    unique_key = f"{user_prefix}_{filename}"

    source_id, exists = get_or_create_source(
        db, 
        unique_key=unique_key,
        source_type="video", 
        source_name=request.url, 
        user_id=current_user.id
    )
    
    if exists:
        return {"source_id": source_id, "status": "ready", "message": "Already exists"}

    current_user.credits -= 1
    db.add(current_user)
    db.commit()

    background_tasks.add_task(ml_analysis_video, request.url, str(source_id))

    return {
        "source_id": source_id, 
        "status": "processing", 
        "message": "You can start chatting in a minute..!"
    }
@app.post("/ingest-document")
async def ingest_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.credits <= 0:
        return {"message": "You have 0 Credits left"}

    user_prefix = current_user.email.split("@")[0]
    unique_key = f"{user_prefix}_{file.filename}"

    source_id, exists = get_or_create_source(
        db, 
        unique_key=unique_key,
        source_type="document", 
        source_name=file.filename, 
        user_id=current_user.id
    )
    
    if exists:
        return {"source_id": source_id, "status": "ready", "message": "Already exists"}

    current_user.credits -= 1
    db.add(current_user)
    db.commit()
    file_bytes = await file.read()

    background_tasks.add_task(ml_analysis_document, file_bytes, file.filename, str(source_id))

    return {
        "source_id": source_id, 
        "status": "processing", 
        "message": "You can start chatting in a minute..!"
    }

# --- History Routes ---
@app.delete("/reset-history")
async def reset_history(
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    analyses = db.query(ResumeAnalysis).filter(ResumeAnalysis.user_id == current_user.id).all()
    
    for item in analyses:
        try:
            s3_client.delete_object(Bucket=get_settings.AWS_BUCKET_NAME, Key=item.s3_key)
        except:
            pass
        db.delete(item)
    
    db.commit()
    return {"status": "success"}
@app.get("/history", response_model=List[AnalysisResponseSchema])
async def get_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    history = db.query(ResumeAnalysis).filter(
        ResumeAnalysis.user_id == current_user.id
    ).order_by(ResumeAnalysis.created_at.desc()).all()
    
    return history

# --- Chat & Conversation Routes ---
@app.post("/chat")
async def chat(
    data: ChatRequestSchema, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    
    if current_user.credits <= 0:
        raise HTTPException(status_code=402, detail="Insufficient credits.")

    try:
        conversation = None
        if data.conversation_id:
            try:
                conv_id = uuid.UUID(str(data.conversation_id))
                conversation = db.query(Conversation).filter(
                    Conversation.id == conv_id,
                    Conversation.user_id == current_user.id
                ).first()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid conversation ID format")

        if not conversation:
            title = (data.question[:27] + "...") if len(data.question) > 30 else data.question
            conversation = Conversation(title=title, user_id=current_user.id)
            db.add(conversation)
            db.flush() 
        
        db.add(ChatMessage(conversation_id=conversation.id, role="user", content=data.question))

        async with httpx.AsyncClient() as client:
            try:
                v_resp = await client.post(
                    f"{get_settings.ML_SERVER_URL}/get-vector", 
                    json={"text": data.question},
                    timeout=20.0 
                )
                v_resp.raise_for_status()
                query_vector = v_resp.json().get("vector")
            except Exception as e:
                print(f"Vectorization Error: {str(e)}")
                raise HTTPException(status_code=502, detail="Failed to vectorize question.")

            chunks = (
                db.query(SourceChunk)
                .join(Source, SourceChunk.source_id == Source.id)
                .filter(Source.user_id == current_user.id)
                .order_by(SourceChunk.embedding.cosine_distance(query_vector))
                .limit(5)
                .all()
            )

            context_text = "\n\n".join([c.content for c in chunks]) if chunks else ""

            try:
                ai_resp = await client.post(
                    f"{get_settings.ML_SERVER_URL}/generate-answer", 
                    json={
                        "question": data.question,
                        "context": context_text
                    },
                    timeout=90.0
                )
                ai_resp.raise_for_status()
                resp_data = ai_resp.json()
                answer_text = resp_data.get("answer", "I couldn't process that.")
            except Exception as e:
                print(f"Generation Error: {str(e)}")
                raise HTTPException(status_code=502, detail="ML Model failed to respond.")

        db.add(ChatMessage(conversation_id=conversation.id, role="assistant", content=answer_text))
        current_user.credits -= 1
        db.commit() 

        return {
            "answer": answer_text,
            "conversation_id": str(conversation.id),
            "context_used": len(chunks) > 0 
        }
            
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"Chat Route Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
@app.get("/conversations")
async def get_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.created_at.desc())
        .all()
    )


@app.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID format")
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conv_uuid,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conv_uuid)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

# --- Service Routes ---
@app.post("/get-folder")
async def get_folder(
    request_data: FolderDataSchema, 
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    # #   background_tasks.add_task(ml_health_check)
    if current_user.credits == 0:
        return {"message": "You have 0 Credits left"}
    async with httpx.AsyncClient() as client:
        drive_url = (
            f"https://www.googleapis.com/drive/v3/files?"
            f"q='{request_data.folderId}'+in+parents+and+trashed=false"
            f"&fields=files(id, name, mimeType)"
        )
        headers = {"Authorization": f"Bearer {request_data.googleToken}"}
        response = await client.get(drive_url, headers=headers)
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Drive access failed")
            
        files = response.json().get("files", [])
        file_list = [f for f in files if f['mimeType'] != 'application/vnd.google-apps.folder']

    if not file_list:
        return {"message": "No files found."}
    
    background_tasks.add_task(
        ml_analysis_drive,
        str(current_user.id),
        file_list,
        request_data.googleToken,
        request_data.description
    )

    return {"message": f"Queued {len(file_list)} files for background processing.","files":file_list}
@app.post("/upload")
async def upload_files(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    description: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    #   background_tasks.add_task(ml_health_check)
    if current_user.credits == 0:
        return {"message": "You have 0 Credits left"}
    for file in files:
        file_id = uuid.uuid4()
        s3_url, s3_key = await upload_to_s3(file, file.filename)
        create_file_record(db, current_user.id, file.filename, s3_key, file_id)
        background_tasks.add_task(ml_analysis_s3, str(file_id), s3_url, file.filename, description)
    
    return {"message": "Processing started"}

# --- Misc Routes ---
@app.post("/get-description")
async def get_description(file: UploadFile = File(...)):
    content = await file.read()
    return {"description": extract.text(content, file.content_type)}
@app.post("/feedback")
async def create_feedback(
    data: FeedbackSchema, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    try:
        new_feedback = Feedback(
            email=data.email,
            category=data.category.value,
            content=data.content,
        )
        db.add(new_feedback)
        db.commit()
        db.refresh(new_feedback)

        html_content = create_html_body(data.category.value, data.content)

        message = MessageSchema(
            subject="Feedback Received • Alluvium™",
            recipients=[data.email],
            body=html_content,
            subtype=MessageType.html,
            attachments=[{
            "file": "app/static/logo.png",
            "headers": { "Content-ID": "<logo>" },
            "mime_type": "image",
            "mime_subtype": "png"
        }]
        )
        fm = FastMail(conf)

        background_tasks.add_task(fm.send_message, message)

        return {"status": "success", "id": str(new_feedback.id)}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Transmission error.")
@app.get("/get-feedbacks")
async def get_all_feedbacks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.email != "dhruv@gmail.com":
        raise HTTPException(
            status_code=403, 
            detail="Access denied. Administrator privileges required"
        )
    
    feedbacks = db.query(Feedback).order_by(Feedback.created_at.desc()).all()
    return feedbacks


@app.get("/admin/data")
async def get_admin_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all DB data for admin (useremail === dhruv@gmail.com)."""
    if current_user.email != "dhruv@gmail.com":
        raise HTTPException(
            status_code=403,
            detail="Access denied. Administrator privileges required",
        )
    users = db.query(User).order_by(User.updated_at.desc()).all()
    users_data = [
        {
            "id": str(u.id),
            "email": u.email,
            "credits": u.credits,
            "updated_at": str(u.updated_at) if u.updated_at else None,
            "linked_folder_ids": u.linked_folder_ids or [],
            "processed_filenames": u.processed_filenames or [],
        }
        for u in users
    ]
    sources = db.query(Source).order_by(Source.created_at.desc()).all()
    sources_data = [
        {
            "id": str(s.id),
            "source_name": s.source_name,
            "source_type": s.source_type,
            "status": s.status.value if hasattr(s.status, "value") else str(s.status),
            "unique_key": s.unique_key,
            "user_id": str(s.user_id),
            "created_at": str(s.created_at) if s.created_at else None,
            "updated_at": str(s.updated_at) if s.updated_at else None,
        }
        for s in sources
    ]
    analyses = (
        db.query(ResumeAnalysis)
        .order_by(ResumeAnalysis.created_at.desc())
        .all()
    )
    analyses_data = [
        {
            "id": str(a.id),
            "user_id": str(a.user_id),
            "filename": a.filename,
            "s3_key": a.s3_key,
            "status": a.status.value if hasattr(a.status, "value") else str(a.status),
            "match_score": a.match_score,
            "details": a.details,
            "candidate_info": a.candidate_info,
            "created_at": str(a.created_at) if a.created_at else None,
            "updated_at": str(a.updated_at) if a.updated_at else None,
        }
        for a in analyses
    ]
    conversations = (
        db.query(Conversation)
        .order_by(Conversation.created_at.desc())
        .all()
    )
    conversations_data = []
    for c in conversations:
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == c.id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        conversations_data.append(
            {
                "id": str(c.id),
                "user_id": str(c.user_id),
                "title": c.title,
                "created_at": str(c.created_at) if c.created_at else None,
                "message_count": len(messages),
                "messages": [
                    {
                        "id": str(m.id),
                        "role": m.role,
                        "content": m.content,
                        "created_at": str(m.created_at) if m.created_at else None,
                    }
                    for m in messages
                ],
            }
        )
    feedbacks = db.query(Feedback).order_by(Feedback.created_at.desc()).all()
    feedbacks_data = [
        {
            "id": str(f.id),
            "email": f.email,
            "category": f.category.value if hasattr(f.category, "value") else str(f.category),
            "content": f.content,
            "created_at": str(f.created_at) if f.created_at else None,
        }
        for f in feedbacks
    ]
    return {
        "users": users_data,
        "sources": sources_data,
        "resume_analyses": analyses_data,
        "conversations": conversations_data,
        "feedbacks": feedbacks_data,
    }


@app.post("/resolve-feedback")
async def resolve_feedback(
    data: FeedbackResolveSchema, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    feedback_item = db.query(Feedback).filter(Feedback.id == data.id).first()
    
    if not feedback_item:
        raise HTTPException(status_code=404, detail="Feedback record not found.")

    try:
        html_content = create_resolve_html_body(feedback_item.category, feedback_item.content)

        message = MessageSchema(
            subject="Feedback Resolved • Alluvium™",
            recipients=[feedback_item.email],
            body=html_content,
            subtype=MessageType.html,
            attachments=[{
                "file": "app/static/logo.png",
                "headers": { "Content-ID": "<logo>" },
                "mime_type": "image",
                "mime_subtype": "png"
            }]
        )
        
        fm = FastMail(conf)
        background_tasks.add_task(fm.send_message, message)

        db.delete(feedback_item)
        db.commit()

        return {"status": "success", "message": f"Feedback {data.id} resolved and email sent."}
        
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error during resolution.")