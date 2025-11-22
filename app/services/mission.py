# app/services/mission.py
from typing import List

from fastapi import HTTPException, status
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError
from app.services.permissions import is_system_role, is_mission_role
from app.models.user import UserModel

from app.entities.Mission import Mission
from app.models.mission import (
    MissionCreateModel,
    MissionReadModel,
    MissionUpdateModel,
)


class MissionService:
    @staticmethod
    def create_mission(db: Session, mission_in: MissionCreateModel) -> Mission:
        try:
            mission = Mission(**mission_in.model_dump())
            db.add(mission)
            db.commit()
            db.refresh(mission)
            return mission
        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Database error creating mission: {str(e)}",
            )

    @staticmethod
    @staticmethod
    def get_missions(db: Session, current_user: UserModel) -> list[Mission]:
        stmt = select(Mission)

        if is_system_role(current_user):
            # system_admin / system_user -> see all
            pass
        elif is_mission_role(current_user):
            # mission_admin / mission_user -> only their mission
            if current_user.mission_id is None:
                return []
            stmt = stmt.where(Mission.id == current_user.mission_id)
        else:
            # any weird / unknown role: nothing
            return []

        return list(db.exec(stmt).all())

    @staticmethod
    def get_mission(db: Session, mission_id: int) -> Mission:
        mission = db.get(Mission, mission_id)
        if not mission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Mission with id {mission_id} not found",
            )
        return mission

    @staticmethod
    def update_mission(
        db: Session, mission_id: int, mission_in: MissionUpdateModel
    ) -> Mission:
        mission = MissionService.get_mission(db, mission_id)

        update_data = mission_in.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(mission, key, value)

        try:
            db.add(mission)
            db.commit()
            db.refresh(mission)
            return mission
        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Database error updating mission: {str(e)}",
            )

    @staticmethod
    def delete_mission(db: Session, mission_id: int) -> None:
        mission = MissionService.get_mission(db, mission_id)
        try:
            db.delete(mission)
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Database error deleting mission: {str(e)}",
            )
