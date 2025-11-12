from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select, Session
from app.entities.ExclusionCone import ExclusionCone
from app.models.ground_station import (
    GroundStationCreateModel,
    GroundStationUpdateModel,
)
from app.entities.GroundStation import GroundStation
from app.entities.Visibility import Visibility  # <-- ABSOLUTE import
from datetime import datetime, timedelta



class GroundStationService:
    @staticmethod
    def create_ground_station(
        db: Session, ground_station: GroundStationCreateModel
    ) -> GroundStation:
        # TODO: Before we service the request in the future we must first validate that request is legitimate (token validation)
        # TODO: Check user permissions to allow ground station creation
        try:
            gs = GroundStation(**ground_station.model_dump())
            db.add(gs)
            db.commit()
            db.refresh(gs)
            return gs

        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(
                status_code=503,
                detail=f"Database error while creating ground station: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while creating ground station: {str(e)}",
            )

    @staticmethod
    def update_ground_station(
        db: Session, gs_id: int, request: GroundStationUpdateModel
    ) -> GroundStation:
        # TODO: Before we service the request in the future we must first validate that request is legitimate (token validation)
        # TODO: Check user permissions to allow update
        try:
            existing_gs = GroundStationService.get_ground_station(db, gs_id)

            if not existing_gs:
                raise HTTPException(
                    status_code=404, detail=f"Ground station with ID {gs_id} not found"
                )

            update_data = request.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(existing_gs, key, value)

            db.commit()
            db.refresh(existing_gs)
            print(existing_gs)
            return existing_gs

        except HTTPException as http_e:
            raise http_e
        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(
                status_code=503,
                detail=f"Database error while updating ground station {gs_id}: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while updating ground station {gs_id}: {str(e)}",
            )

    @staticmethod
    def get_ground_stations(db: Session) -> list[GroundStation]:
        # TODO: Before we service the request in the future we must first validate that request is legitimate (token validation)
        # TODO: Check user permissions to return ground station
        try:
            statement = select(GroundStation)
            ground_stations = db.exec(statement).all()
            return list(ground_stations)

        except SQLAlchemyError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Database error while fetching ground stations: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while fetching ground stations: {str(e)}",
            )

    @staticmethod
    def get_ground_station(db: Session, gs_id: int) -> GroundStation:
        # TODO: Before we service the request in the future we must first validate that request is legitimate (token validation)
        # TODO: Check user permissions to return ground station
        try:
            statement = select(GroundStation).where(GroundStation.id == gs_id)
            ground_station = db.exec(statement).first()

            if ground_station is None:
                raise HTTPException(
                    status_code=404, detail=f"Ground station with ID {gs_id} not found"
                )
            return ground_station

        except HTTPException as http_e:
            raise http_e
        except SQLAlchemyError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Database error while fetching ground station {gs_id}: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while fetching ground station {gs_id}: {str(e)}",
            )

    @staticmethod
    def delete_ground_station(db: Session, gs_id: int) -> GroundStation:
        # TODO: Before we service the request in the future we must first validate that request is legitimate (token validation)
        # TODO: Check user permissions to delete ground station
        try:
            ground_station = GroundStationService.get_ground_station(db, gs_id)

            if not ground_station:
                raise HTTPException(
                    status_code=404, detail=f"Ground station with ID {gs_id} not found"
                )

            statement_ex = select(ExclusionCone).where(ExclusionCone.gs_id == gs_id)
            ex_cones = db.exec(statement_ex).all()

            if len(ex_cones) > 0:
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot delete ground station with the following exclusion cones attached: {[str(ex_cone.id) for ex_cone in ex_cones]}",
                )

            db.delete(ground_station)
            db.commit()
            return ground_station

        except HTTPException as http_e:
            raise http_e
        except SQLAlchemyError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Database error while deleting ground station {gs_id}: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while deleting ground station {gs_id}: {str(e)}",
            )
    #Added by MD
    def get_visibilities(self, satellite, gs, start: datetime, end: datetime) -> list[Visibility]:
        # TODO: call your real pass computation if available
        return [Visibility(gs=gs, sat=satellite, start=start, end=end)]
