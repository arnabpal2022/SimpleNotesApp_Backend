from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import models
import database
import auth
import secrets
import string

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables
models.Base.metadata.create_all(bind=database.engine)

# Pydantic models
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class NoteCreate(BaseModel):
    title: str
    content: str

class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    is_public: Optional[bool] = None

class NoteResponse(BaseModel):
    id: int
    title: str
    content: str
    is_public: bool
    share_id: Optional[str]
    created_at: str
    updated_at: str

# Helper function to generate share ID
def generate_share_id():
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10))

# Routes
@app.post("/register")
def register(user: UserCreate, db: Session = Depends(database.get_db)):
    # Check if user exists
    db_user = db.query(models.User).filter(
        (models.User.username == user.username) | (models.User.email == user.email)
    ).first()
    
    if db_user:
        raise HTTPException(status_code=400, detail="Username or email already registered")
    
    # Create new user
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    
    return {"message": "User created successfully"}

@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = auth.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/notes", response_model=List[NoteResponse])
def get_notes(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    notes = db.query(models.Note).filter(models.Note.owner_id == current_user.id).all()
    return [
        NoteResponse(
            id=note.id,
            title=note.title,
            content=note.content,
            is_public=note.is_public,
            share_id=note.share_id,
            created_at=note.created_at.isoformat(),
            updated_at=note.updated_at.isoformat()
        )
        for note in notes
    ]

@app.post("/notes", response_model=NoteResponse)
def create_note(note: NoteCreate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    db_note = models.Note(
        title=note.title,
        content=note.content,
        owner_id=current_user.id,
        share_id=generate_share_id()
    )
    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    
    return NoteResponse(
        id=db_note.id,
        title=db_note.title,
        content=db_note.content,
        is_public=db_note.is_public,
        share_id=db_note.share_id,
        created_at=db_note.created_at.isoformat(),
        updated_at=db_note.updated_at.isoformat()
    )

@app.put("/notes/{note_id}", response_model=NoteResponse)
def update_note(note_id: int, note_update: NoteUpdate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    db_note = db.query(models.Note).filter(
        models.Note.id == note_id,
        models.Note.owner_id == current_user.id
    ).first()
    
    if not db_note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    if note_update.title is not None:
        db_note.title = note_update.title
    if note_update.content is not None:
        db_note.content = note_update.content
    if note_update.is_public is not None:
        db_note.is_public = note_update.is_public
    
    db.commit()
    db.refresh(db_note)
    
    return NoteResponse(
        id=db_note.id,
        title=db_note.title,
        content=db_note.content,
        is_public=db_note.is_public,
        share_id=db_note.share_id,
        created_at=db_note.created_at.isoformat(),
        updated_at=db_note.updated_at.isoformat()
    )

@app.delete("/notes/{note_id}")
def delete_note(note_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    db_note = db.query(models.Note).filter(
        models.Note.id == note_id,
        models.Note.owner_id == current_user.id
    ).first()
    
    if not db_note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    db.delete(db_note)
    db.commit()
    
    return {"message": "Note deleted successfully"}

@app.get("/shared/{share_id}")
def get_shared_note(share_id: str, db: Session = Depends(database.get_db)):
    note = db.query(models.Note).filter(
        models.Note.share_id == share_id,
        models.Note.is_public == True
    ).first()
    
    if not note:
        raise HTTPException(status_code=404, detail="Note not found or not public")
    
    return {
        "title": note.title,
        "content": note.content,
        "created_at": note.created_at.isoformat()
    }