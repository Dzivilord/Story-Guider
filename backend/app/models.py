from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Index, Float, Boolean
from .database import Base
class Book(Base):
    __tablename__='books'
    work_id=Column(Integer, primary_key=True)
    title=Column(Text, nullable=False); description=Column(Text); first_author=Column(Text); content_tags=Column(Text, nullable=False, default='[]'); series=Column(Text, nullable=False, default='[]')
    earliest_known_publication_year=Column(Integer); publication_decade=Column(Text); pages=Column(Integer); length_category=Column(Text)
    average_rating=Column(Float); ratings_count=Column(Integer); reviews_count=Column(Integer); has_rating=Column(Boolean)
    rating_confidence=Column(Float); weighted_rating=Column(Float); log_ratings_count=Column(Float); log_reviews_count=Column(Float); num_editions=Column(Integer); log_num_editions=Column(Float); is_part_of_series=Column(Boolean); url=Column(Text); language=Column(Text)
    __table_args__=(Index('ix_books_title','title'), Index('ix_books_author','first_author'))
class User(Base):
    __tablename__='users'; id=Column(String, primary_key=True); name=Column(String, nullable=False); created_at=Column(DateTime, default=datetime.utcnow)
class Interaction(Base):
    __tablename__='interactions'; user_id=Column(String, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True); work_id=Column(Integer, ForeignKey('books.work_id', ondelete='CASCADE'), primary_key=True); liked=Column(Boolean, nullable=False, default=False); disliked=Column(Boolean, nullable=False, default=False); followed=Column(Boolean, nullable=False, default=False); rating=Column(Integer, nullable=True); created_at=Column(DateTime, default=datetime.utcnow); updated_at=Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__=(Index('ix_interactions_user','user_id'), Index('ix_interactions_work','work_id'))
