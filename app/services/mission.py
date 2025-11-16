# app/services/mission.py
from typing import List

from fastapi import HTTPException, status
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError

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
    def get_missions(db: Session) -> list[Mission]:
        statement = select(Mission)
        missions = db.exec(statement).all()
        return list(missions)

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
