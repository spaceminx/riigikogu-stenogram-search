from sqlalchemy import Column, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Speech(Base):
    __tablename__ = "speeches"

    id = Column(Integer, primary_key=True)
    date = Column(Text, nullable=False)
    time = Column(Text, nullable=False)
    source_file = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    agenda_title = Column(Text, nullable=True)
    video_url = Column(Text, nullable=True)
    speaker = Column(Text, nullable=False)
    speaker_role = Column(Text, nullable=True)
    speaker_faction = Column(Text, nullable=True)
    speaker_uuid = Column(Text, nullable=True, index=True)
    ems_id = Column(Text, nullable=True)
    speech_type = Column(Text, nullable=True)
    external_id = Column(Integer, nullable=True, index=True)
    start_time = Column(Text, nullable=True)
    end_time = Column(Text, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    speech_key = Column(Text, nullable=True, index=True)
    text = Column(Text, nullable=False)
    text_lemmas = Column(Text, nullable=True)
    status = Column(Text, nullable=True, default="EDITED")


class SpeechAlias(Base):
    __tablename__ = "speech_aliases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alias_external_id = Column(Integer, nullable=False, index=True)
    speech_id = Column(Integer, ForeignKey("speeches.id"), nullable=False, index=True)


class Person(Base):
    __tablename__ = "persons"

    uuid = Column(Text, primary_key=True)
    first_name = Column(Text, nullable=False)
    last_name = Column(Text, nullable=False)
    full_name = Column(Text, nullable=False, index=True)
    gender = Column(Text, nullable=True)
    date_of_birth = Column(Text, nullable=True)
    email = Column(Text, nullable=True)
    photo_url = Column(Text, nullable=True)
    electoral_district = Column(Text, nullable=True)
    seniority_days = Column(Integer, nullable=True)
    active = Column(Integer, nullable=True, default=1)


class Lemma(Base):
    __tablename__ = "lemmas"

    id = Column(Integer, primary_key=True)
    lemma = Column(Text, unique=True, nullable=False)


class SpeechTerm(Base):
    __tablename__ = "speech_terms"

    id = Column(Integer, primary_key=True)

    speech_id = Column(Integer, ForeignKey("speeches.id"), nullable=False)

    lemma_id = Column(Integer, ForeignKey("lemmas.id"), nullable=False)

    count = Column(Integer, nullable=False, default=1)

    __table_args__ = (UniqueConstraint("speech_id", "lemma_id", name="uq_speech_lemma"),)


class Attendance(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True)
    session_date = Column(Text, nullable=False)
    voting_uuid = Column(Text, nullable=False)
    member_name = Column(Text, nullable=False)
    faction = Column(Text, nullable=True)
    status = Column(Text, nullable=False)

    __table_args__ = (UniqueConstraint("voting_uuid", "member_name", name="uq_attendance"),)
