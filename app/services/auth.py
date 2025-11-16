from datetime import datetime, timedelta
from typing import Optional, Any, Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select
from dotenv import load_dotenv
import os
import secrets
from pydantic import BaseModel
from ..entities.User import User, UserCreate
from app.services.db import get_db

# Generate random secret key
DEFAULT_SECRET_KEY = secrets.token_urlsafe(32)

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", DEFAULT_SECRET_KEY)

# Secret key should be loaded from environment variables in production.
# Use this for development only—change this to a secure random key!
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    statement = select(User).where(User.username == username)
    return db.exec(statement).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    statement = select(User).where(User.email == email)
    return db.exec(statement).first()


def get_user(db: Session, username: str) -> Optional[User]:
    return get_user_by_username(db, username)


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = get_user(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_access_token(
    data: Dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    to_encode: Dict[str, Any] = data.copy()
    if expires_delta:
        expire = datetime.now() + expires_delta
    else:
        expire = datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = get_user(db, username=username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def register_user(db: Session, user_data: UserCreate) -> User:
    """Register a new user after validating username and email are unique"""
    # Check if username already exists
    existing_user = get_user_by_username(db, user_data.username)
    if existing_user:
        raise ValueError("Username already registered")

    # Check if email already exists
    existing_email = get_user_by_email(db, user_data.email)
    if existing_email:
        raise ValueError("Email already registered")

    # Create new user
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user

def register_user(db: Session, user_data: UserCreate) -> User:
    """Register a new user after validating username and email are unique"""
    # Check if username already exists
    existing_user = get_user_by_username(db, user_data.username)
    if existing_user:
        raise ValueError("Username already registered")

    # Check if email already exists
    existing_email = get_user_by_email(db, user_data.email)
    if existing_email:
        raise ValueError("Email already registered")

    # Create new user
    hashed_password = get_password_hash(user_data.password)

    # 🔹 Use role + mission_id from user_data (with safe defaults)
    role = getattr(user_data, "role", "user") or "user"
    mission_id = getattr(user_data, "mission_id", None)

    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
        role=user_data.role,            # NEW
        mission_id=user_data.mission_id # NEW
        #role=role,
        #mission_id=mission_id,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user

