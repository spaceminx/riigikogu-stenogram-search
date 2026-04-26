from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, Text, UniqueConstraint, ForeignKey

Base = declarative_base()


class Speech(Base):
    __tablename__ = "speeches"

    id = Column(Integer, primary_key=True)
    date = Column(Text, nullable=False)
    time = Column(Text, nullable=False)
    source_file = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    speaker = Column(Text, nullable=False)
    text = Column(Text, nullable=False)
    text_lemmas = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("source_file", "speaker", "text", name="uq_speech"),
    )

class Lemma(Base):
    __tablename__ = "lemmas"

    id = Column(Integer, primary_key=True)
    lemma = Column(Text, unique=True, nullable=False)

class SpeechTerm(Base):
    __tablename__ = "speech_terms"

    id = Column(Integer, primary_key=True)

    speech_id = Column(
        Integer,
        ForeignKey("speeches.id"),
        nullable=False
    )

    lemma_id = Column(
        Integer,
        ForeignKey("lemmas.id"),
        nullable=False
    )

    count = Column(Integer, nullable=False, default=1)