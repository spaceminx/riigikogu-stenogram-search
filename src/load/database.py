import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import DATABASE_DIR, DATABASE_URL

os.makedirs(DATABASE_DIR, exist_ok=True)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
