from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select, Session
from app.models.user import UserModel, UserUpdateModel
from app.entities.User import User
from app.services.auth import get_password_hash


def is_system_admin(role: str) -> bool:
    return role == "system_admin"


class UserService:
    @staticmethod
    def update_user(
        db: Session, user_id: int, request: UserUpdateModel, current_user: UserModel
    ) -> User:
        try:
            existing_user = UserService.get_user(db, user_id, current_user)

            update_data = request.model_dump(exclude_unset=True)

            # --- PERMISSIONS FOR UPDATING USERS ---
            if is_system_admin(current_user.role):
                # system_admin can edit anything
                pass
            else:
                # non-admins can only edit themselves
                if current_user.id != existing_user.id:
                    raise HTTPException(status_code=403, detail="Permission denied")

                # non-admins cannot change these fields
                forbidden_fields = ("role", "mission_id")
                for field in forbidden_fields:
                    if field in update_data:
                        raise HTTPException(
                            status_code=403,
                            detail=f"You cannot change {field}",
                        )
            # ---------------------------------------

            # Apply updates
            for key, value in update_data.items():
                if key == "password":
                    setattr(existing_user, "hashed_password", get_password_hash(value))
                else:
                    setattr(existing_user, key, value)

            db.commit()
            db.refresh(existing_user)
            return existing_user

        except HTTPException as http_e:
            raise http_e
        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(
                status_code=503,
                detail=f"Database error while updating user {user_id}: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while updating user {user_id}: {str(e)}",
            )

    @staticmethod
    def get_users(db: Session, current_user: UserModel) -> list[User]:
        try:
            # 🔹 Only system admins can list all users
            if not is_system_admin(current_user.role):
                raise HTTPException(status_code=403, detail="Permission denied")

            statement = select(User)
            users = db.exec(statement).all()

            return list(users)

        except HTTPException as http_e:
            raise http_e
        except SQLAlchemyError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Database error while fetching users: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while fetching users: {str(e)}",
            )

    @staticmethod
    def get_user(db: Session, user_id: int, current_user: UserModel) -> User:
        try:
            # 🔹 System admin can see any user
            # 🔹 Non-admin can only see themselves
            if not is_system_admin(current_user.role) and current_user.id != user_id:
                raise HTTPException(status_code=403, detail="Permission denied")

            statement = select(User).where(User.id == user_id)
            user = db.exec(statement).first()

            if not user:
                raise HTTPException(
                    status_code=404, detail=f"User with ID {user_id} not found"
                )
            return user

        except HTTPException as http_e:
            raise http_e
        except SQLAlchemyError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Database error while fetching user {user_id}: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while fetching user {user_id}: {str(e)}",
            )
