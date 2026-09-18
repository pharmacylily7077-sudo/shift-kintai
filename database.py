import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 永続ストレージ用（/data ディレクトリが存在する場合は自動的にそちらを優先）
if os.path.exists("/data") and os.path.isdir("/data"):
    default_db_url = "sqlite:////data/kintai.db"
else:
    default_db_url = "sqlite:///./kintai.db"

DATABASE_URL = os.getenv("DATABASE_URL", default_db_url)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLiteの場合、スレッドチェックを無効化
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
