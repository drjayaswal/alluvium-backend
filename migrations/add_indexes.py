"""
Database index optimization script
Run this to add indexes for better query performance
"""
from sqlalchemy import create_engine, text
from app.config import settings
from app.db.connect import get_settings

def add_indexes():
    """Add database indexes for optimized queries"""
    engine = create_engine(get_settings.DATABASE_URL)
    
    indexes = [
        # User table indexes
        "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);",
        "CREATE INDEX IF NOT EXISTS idx_users_updated_at ON users(updated_at DESC);",
        
        # Source table indexes
        "CREATE INDEX IF NOT EXISTS idx_sources_user_id ON sources(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_sources_user_id_created_at ON sources(user_id, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_sources_unique_key ON sources(unique_key);",
        "CREATE INDEX IF NOT EXISTS idx_sources_status ON sources(status);",
        
        # SourceChunk table indexes
        "CREATE INDEX IF NOT EXISTS idx_source_chunks_source_id ON source_chunks(source_id);",
        "CREATE INDEX IF NOT EXISTS idx_source_chunks_status ON source_chunks(status);",
        # Note: Vector index for embeddings should be created separately using pgvector
        
        # Conversation table indexes
        "CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_conversations_user_id_created_at ON conversations(user_id, created_at DESC);",
        
        # ChatMessage table indexes
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_id ON chat_messages(conversation_id);",
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_id_created_at ON chat_messages(conversation_id, created_at ASC);",
        
        # ResumeAnalysis table indexes
        "CREATE INDEX IF NOT EXISTS idx_resume_analyses_user_id ON resume_analyses(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_resume_analyses_user_id_created_at ON resume_analyses(user_id, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_resume_analyses_status ON resume_analyses(status);",
        
        # Feedback table indexes
        "CREATE INDEX IF NOT EXISTS idx_feedbacks_created_at ON feedbacks(created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_feedbacks_category ON feedbacks(category);",
    ]
    
    with engine.connect() as conn:
        for index_sql in indexes:
            try:
                conn.execute(text(index_sql))
                conn.commit()
                print(f"✓ Created index: {index_sql.split('ON')[1].split('(')[0].strip()}")
            except Exception as e:
                print(f"✗ Failed to create index: {e}")
                conn.rollback()
    
    print("\nIndex creation completed!")

if __name__ == "__main__":
    add_indexes()
