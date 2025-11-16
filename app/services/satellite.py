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
from app.models.user import UserModel


class SatelliteService:
    @staticmethod
    def create_satellite(
        db: Session,
        satellite: SatelliteCreateModel,
        current_user: UserModel,
    ) -> Satellite:
        """
        Create a satellite with mission-aware RBAC:

        - system_admin: can create satellites for any mission (mission_id from request)
        - mission_admin: can create satellites ONLY for their own mission_id
        - others: 403
        """
        # RBAC: who can create?
        if current_user.role == "system_admin":
            effective_mission_id = satellite.mission_id
        elif current_user.role == "mission_admin":
            if current_user.mission_id is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Mission admin has no mission_id configured",
                )
            # ignore whatever was sent in body, force their mission
            effective_mission_id = current_user.mission_id
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to create satellites",
            )

        try:
            data = satellite.model_dump()
            data["mission_id"] = effective_mission_id

            sat = Satellite(**data)
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
        current_user: UserModel,
    ) -> Satellite:
        """
        Update a satellite with mission-aware RBAC:

        - system_admin: can update any satellite
        - mission_admin: can update satellites ONLY in their mission
        - others: 403
        """
        try:
            existing_sat = SatelliteService.get_satellite(db, sat_id)

            if not existing_sat:
                raise HTTPException(
                    status_code=404, detail=f"Satellite with ID {sat_id} not found"
                )

            # RBAC check
            if current_user.role == "system_admin":
                pass
            elif current_user.role == "mission_admin":
                if current_user.mission_id != existing_sat.mission_id:
                    raise HTTPException(
                        status_code=403,
                        detail="You cannot modify satellites from another mission",
                    )
            else:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have permission to modify satellites",
                )

            update_data = satellite.model_dump(exclude_unset=True)

            # mission_admin cannot move satellites to other missions
            if current_user.role == "mission_admin":
                if "mission_id" in update_data and update_data["mission_id"] != current_user.mission_id:
                    raise HTTPException(
                        status_code=403,
                        detail="Mission admin cannot change mission_id",
                    )
                # force mission_id to their mission if they try to send None or something else
                update_data["mission_id"] = existing_sat.mission_id or current_user.mission_id

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
    def get_satellites(db: Session, current_user: UserModel) -> list[Satellite]:
        """
        List satellites with mission-aware RBAC:

        - system_admin / system_user: see all satellites
        - mission_admin / mission_user: only satellites in their mission_id
        """
        try:
            statement = select(Satellite).options(joinedload(Satellite.ex_cones))

            if current_user.role in ("mission_admin", "mission_user"):
                if current_user.mission_id is None:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Mission-scoped user has no mission_id configured",
                    )
                statement = statement.where(
                    Satellite.mission_id == current_user.mission_id
                )

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
        current_user: UserModel,
    ) -> Satellite:
        """
        Get one satellite with mission-aware RBAC:

        - system_admin / system_user: can see any satellite
        - mission_admin / mission_user: only if satellite.mission_id == their mission_id
        """
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

            if current_user.role in ("mission_admin", "mission_user"):
                if current_user.mission_id is None or satellite.mission_id != current_user.mission_id:
                    raise HTTPException(
                        status_code=403,
                        detail="You cannot view satellites from another mission",
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
        current_user: UserModel,
    ) -> Satellite:
        """
        Delete a satellite with mission-aware RBAC:

        - system_admin: can delete any
        - mission_admin: can delete satellites ONLY in their mission
        - others: 403
        """
        try:
            satellite = SatelliteService.get_satellite(db, sat_id)

            if not satellite:
                raise HTTPException(
                    status_code=404, detail=f"Satellite with ID {sat_id} not found"
                )

            # RBAC
            if current_user.role == "system_admin":
                pass
            elif current_user.role == "mission_admin":
                if current_user.mission_id != satellite.mission_id:
                    raise HTTPException(
                        status_code=403,
                        detail="You cannot delete satellites from another mission",
                    )
            else:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have permission to delete satellites",
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
