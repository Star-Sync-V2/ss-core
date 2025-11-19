import uuid
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select, Session
from sqlalchemy.orm import joinedload
from app.models.satellite import (
    SatelliteCreateModel,
    SatelliteUpdateModel,
)
from app.entities.Satellite import Satellite


class SatelliteService:
    @staticmethod
    def create_satellite(
        db: Session,
        satellite: SatelliteCreateModel,
        current_user,
    ) -> Satellite:
        # RBAC:
        # - system_admin: can create any satellite
        # - system_user: no create
        # - mission_admin: can create only for their mission_id
        # - mission_user: no create
        role = getattr(current_user, "role", None)

        if role in ("system_user", "mission_user"):
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to create satellites.",
            )

        # If mission-admin, enforce mission_id
        if role == "mission_admin":
            sat_mission_id = getattr(satellite, "mission_id", None)
            user_mission_id = getattr(current_user, "mission_id", None)
            if sat_mission_id is None or user_mission_id is None:
                raise HTTPException(
                    status_code=403,
                    detail="Mission admins can only create satellites for their own mission.",
                )
            if sat_mission_id != user_mission_id:
                raise HTTPException(
                    status_code=403,
                    detail="Mission admins can only create satellites for their own mission.",
                )

        try:
            sat = Satellite(**satellite.model_dump())
            db.add(sat)
            db.commit()
            db.refresh(sat)
            return sat

        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(
                status_code=503,
                detail=f"Database error while creating satellite: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while creating satellite: {str(e)}",
            )

    @staticmethod
    def update_satellite(
        db: Session,
        sat_id: uuid.UUID,
        satellite: SatelliteUpdateModel,
        current_user,
    ) -> Satellite:
        # RBAC:
        # - system_admin: can update any satellite
        # - system_user: no update
        # - mission_admin: can update satellites in their mission,
        #                  but cannot change mission_id to a different mission
        # - mission_user: no update
        role = getattr(current_user, "role", None)

        if role in ("system_user", "mission_user"):
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to update satellites.",
            )

        try:
            existing_sat = SatelliteService.get_satellite(db, sat_id, current_user)

            if not existing_sat:
                raise HTTPException(
                    status_code=404, detail=f"Satellite with ID {sat_id} not found"
                )

            # Mission admin can only touch satellites in their mission
            if role == "mission_admin":
                user_mission_id = getattr(current_user, "mission_id", None)
                if getattr(existing_sat, "mission_id", None) != user_mission_id:
                    raise HTTPException(
                        status_code=403,
                        detail="Mission admins can only update satellites in their own mission.",
                    )

            update_data = satellite.model_dump(exclude_unset=True)

            # Mission admin cannot reassign satellites to other missions
            if role == "mission_admin" and "mission_id" in update_data:
                new_mission_id = update_data["mission_id"]
                if new_mission_id != getattr(existing_sat, "mission_id", None):
                    raise HTTPException(
                        status_code=403,
                        detail="Mission admins cannot reassign satellites to a different mission.",
                    )

            for key, value in update_data.items():
                setattr(existing_sat, key, value)

            db.commit()
            db.refresh(existing_sat)
            return existing_sat

        except HTTPException as http_e:
            raise http_e
        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(
                status_code=503,
                detail=f"Database error while updating satellite {sat_id}: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while updating satellite {sat_id}: {str(e)}",
            )

    @staticmethod
    def get_satellites(db: Session, current_user) -> list[Satellite]:
        # RBAC:
        # - system_admin, system_user: can see all satellites
        # - mission_admin, mission_user: can only see satellites with their mission_id
        role = getattr(current_user, "role", None)
        user_mission_id = getattr(current_user, "mission_id", None)

        try:
            statement = select(Satellite).options(joinedload(Satellite.ex_cones))

            if role in ("mission_admin", "mission_user"):
                statement = statement.where(Satellite.mission_id == user_mission_id)

            satellites = db.exec(statement).unique().all()
            return list(satellites)

        except SQLAlchemyError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Database error while fetching satellites: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while fetching satellites: {str(e)}",
            )

    @staticmethod
    def get_satellite(
        db: Session,
        sat_id: uuid.UUID,
        current_user,
    ) -> Satellite:
        # RBAC:
        # - system_admin, system_user: can read any satellite
        # - mission_admin, mission_user: can read only satellites in their mission
        role = getattr(current_user, "role", None)
        user_mission_id = getattr(current_user, "mission_id", None)

        try:
            statement = (
                select(Satellite)
                .where(Satellite.id == sat_id)
                .options(joinedload(Satellite.ex_cones))
            )
            satellite = db.exec(statement).unique().first()

            if satellite is None:
                raise HTTPException(
                    status_code=404, detail=f"Satellite with ID {sat_id} not found"
                )

            if role in ("mission_admin", "mission_user"):
                if getattr(satellite, "mission_id", None) != user_mission_id:
                    raise HTTPException(
                        status_code=403,
                        detail="You do not have access to this satellite.",
                    )

            return satellite

        except HTTPException as http_e:
            raise http_e
        except SQLAlchemyError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Database error while fetching satellite {sat_id}: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while fetching satellite {sat_id}: {str(e)}",
            )

    @staticmethod
    def delete_satellite(
        db: Session,
        sat_id: uuid.UUID,
        current_user,
    ) -> Satellite:
        # RBAC:
        # - system_admin: can delete any satellite (if no exclusion cones)
        # - system_user: no delete
        # - mission_admin: can delete satellites in their mission (if no exclusion cones)
        # - mission_user: no delete
        role = getattr(current_user, "role", None)

        if role in ("system_user", "mission_user"):
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to delete satellites.",
            )

        try:
            satellite = SatelliteService.get_satellite(db, sat_id, current_user)

            if not satellite:
                raise HTTPException(
                    status_code=404, detail=f"Satellite with ID {sat_id} not found"
                )

            if role == "mission_admin":
                user_mission_id = getattr(current_user, "mission_id", None)
                if getattr(satellite, "mission_id", None) != user_mission_id:
                    raise HTTPException(
                        status_code=403,
                        detail="Mission admins can only delete satellites in their own mission.",
                    )

            if len(satellite.ex_cones) > 0:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Cannot delete satellite with the following exclusion cones attached: "
                        f"{[str(ex_cone.id) for ex_cone in satellite.ex_cones]}"
                    ),
                )

            db.delete(satellite)
            db.commit()
            return satellite

        except HTTPException as http_e:
            raise http_e
        except SQLAlchemyError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Database error while deleting satellite {sat_id}: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while deleting satellite {sat_id}: {str(e)}",
            )

