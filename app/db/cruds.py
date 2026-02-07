import uuid
from sqlalchemy.orm import Session
from app.db.models import Source, AnalysisStatus
from .models import Source, ResumeAnalysis, SourceChunk, AnalysisStatus, User, Conversation, ChatMessage

def create_file_record(db: Session, user_id: str, filename: str, s3_key: str = None, file_id=None, candidate_info: dict = None):
    db_record = ResumeAnalysis(
        id=file_id or uuid.uuid4(),
        user_id=user_id,
        filename=filename,
        s3_key=s3_key,
        status=AnalysisStatus.PROCESSING,
        match_score=0.0,
        details={},
        candidate_info=candidate_info or {}
    )
    db.add(db_record)
    try:
        db.commit()
        db.refresh(db_record)
    except Exception as e:
        db.rollback()
        raise e
    return db_record
def update_file_record(db: Session, file_id: str, status: AnalysisStatus, score: float = None, details: dict = None, candidate_info: dict = None):
    if isinstance(file_id, str):
        file_uuid = uuid.UUID(file_id)
    else:
        file_uuid = file_id
    db_record = db.query(ResumeAnalysis).filter(ResumeAnalysis.id == file_uuid).first()
    if not db_record:
        return None

    db_record.status = status
    if score is not None: db_record.match_score = score
    if details is not None: db_record.details = details
    if candidate_info is not None: db_record.candidate_info = candidate_info
    if status == AnalysisStatus.COMPLETED:
        user = db.query(User).filter(User.id == db_record.user_id).first()
        if user and user.credits > 0:
            user.credits -= 1

    db.commit()
    db.refresh(db_record)
    return db_record

def create_source_record(db: Session, user_id: uuid.UUID, source_name: str, unique_key: str, source_type: str = "video"):
    db_source = Source(
        id=uuid.uuid4(),
        user_id=user_id,
        source_name=source_name,
        source_type=source_type,
        unique_key=unique_key,
        status=AnalysisStatus.PROCESSING
    )
    db.add(db_source)
    try:
        db.commit()
        db.refresh(db_source)
        return db_source
    except Exception as e:
        db.rollback()
        raise e
def update_source_status(db: Session, source_id: str, status: str):
    try:
        if isinstance(source_id, str):
            source_id = uuid.UUID(source_id)
            
        db_record = db.query(Source).filter(Source.id == source_id).first()
        
        if not db_record:
            print(f"Source {source_id} not found.")
            return None
        
        if status == "ready":
            db_record.status = AnalysisStatus.COMPLETED
        elif status == "failed":
            db_record.status = AnalysisStatus.FAILED
        else:
            db_record.status = AnalysisStatus.PROCESSING

        db.commit()
        db.refresh(db_record)
        return db_record
    except Exception as e:
        db.rollback()
        print(f"Error updating source status: {e}")
        return None

def add_source_chunks(db: Session, source_id: uuid.UUID, chunks_data: list):
    try:
        for data in chunks_data:
            chunk = SourceChunk(
                source_id=source_id,
                content=data['content'],
                embedding=data['embedding'],
                status='completed'
            )
            db.add(chunk)
        
        # Mark source as completed
        db.query(Source).filter(Source.id == source_id).update({"status": AnalysisStatus.COMPLETED})
        db.commit()
    except Exception as e:
        db.rollback()
        db.query(Source).filter(Source.id == source_id).update({"status": AnalysisStatus.FAILED})
        db.commit()
        raise e
def get_source_by_id(db: Session, source_id: uuid.UUID):
    return db.query(Source).filter(Source.id == source_id).first()

def get_or_create_source(
        db: Session, 
        unique_key: str, 
        source_type: str, 
        source_name: str, 
        user_id: str
    ):
        existing_source = db.query(Source).filter(Source.unique_key == unique_key).first()
        
        if existing_source:
            return existing_source.id, True
        
        new_source = Source(
            unique_key=unique_key,
            source_type=source_type,
            source_name=source_name,
            user_id=user_id,
            status=AnalysisStatus.PROCESSING
        )
        
        db.add(new_source)
        db.commit()
        db.refresh(new_source)
        
        return new_source.id, False

def create_conversation(db: Session, user_id: uuid.UUID, title: str = "New Chat"):
    new_conv = Conversation(
        id=uuid.uuid4(),
        user_id=user_id,
        title=title
    )
    db.add(new_conv)
    db.commit()
    db.refresh(new_conv)
    return new_conv
def save_message(db: Session, conversation_id: uuid.UUID, role: str, content: str):
    new_msg = ChatMessage(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role=role,
        content=content
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)
    return new_msg
def get_chat_history(db: Session, conversation_id: uuid.UUID, limit: int = 20):
    return db.query(ChatMessage)\
             .filter(ChatMessage.conversation_id == conversation_id)\
             .order_by(ChatMessage.created_at.asc())\
             .limit(limit)\
             .all()