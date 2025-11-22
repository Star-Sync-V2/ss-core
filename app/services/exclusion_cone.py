# app/services/exclusion_cone.py
import uuid
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
from sqlmodel import select, Session

from app.models.exclusion_cone import (
    ExclusionConeCreateModel,
    ExclusionConeUpdateModel,
)
from app.entities.ExclusionCone import ExclusionCone
from app.services.ground_station import GroundStationService
from app.services.satellite import SatelliteService
from app.models.user import UserModel
from app.services.permissions import (
    is_system_role,
    is_mission_role,
    SYSTEM_ADMIN,
    MISSION_ADMIN,
)


class ExclusionConeService:
    @staticmethod
    def create_exclusion_cone(
        db: Session,
        exclusion_cone: ExclusionConeCreateModel,
        current_user: UserModel,
    ) -> ExclusionCone:
        try:
            # --- RBAC: only system_admin or mission_admin can create ---
            if current_user.role not in (SYSTEM_ADMIN, MISSION_ADMIN):
                raise HTTPException(
                    status_code=403,
                    detail="Only system_admin or mission_admin can create exclusion cones",
                )

            # Check satellite (mission-scoped)
            sat = SatelliteService.get_satellite(
                db,
                exclusion_cone.satellite_id,
                current_user,
            )
            if sat is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Satellite with ID {exclusion_cone.satellite_id} not found",
                )

            # Check Ground Station exists
            gs = GroundStationService.get_ground_station(db, exclusion_cone.gs_id)
            if gs is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Ground Station with ID {exclusion_cone.gs_id} not found",
                )

            # Mission scoping
            mission_id_to_use = sat.mission_id

            if is_mission_role(current_user):
                if current_user.mission_id is None:
                    raise HTTPException(
                        status_code=400,
                        detail="Current user has no mission_id assigned",
                    )
                if sat.mission_id != current_user.mission_id:
                    raise HTTPException(
                        status_code=403,
                        detail="Mission roles can only create cones for their own mission's satellites",
                    )

            ex_cone = ExclusionCone(
                mission=exclusion_cone.mission,
                mission_id=mission_id_to_use,
                angle_limit=exclusion_cone.angle_limit,
                interfering_satellite=exclusion_cone.interfering_satellite,
                satellite_id=exclusion_cone.satellite_id,
                gs_id=exclusion_cone.gs_id,
            )
            db.add(ex_cone)
            db.commit()
            db.refresh(ex_cone)
            return ex_cone

        except HTTPException as http_e:
            raise http_e
        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(
                status_code=503,
                detail=f"Database error while creating exclusion cone: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while creating exclusion cone: {str(e)}",
            )

    @staticmethod
    def get_exclusion_cones(
        db: Session,
        current_user: UserModel,
    ) -> list[ExclusionCone]:
        try:
            stmt = select(ExclusionCone)

            if is_system_role(current_user):
                # system_admin / system_user → see everything
                pass
            elif is_mission_role(current_user):
                # mission_admin / mission_user → only their mission's cones
                if current_user.mission_id is None:
                    return []
                stmt = stmt.where(ExclusionCone.mission_id == current_user.mission_id)
            else:
                # other roles → no visibility
                return []

            ex_cones = db.exec(stmt).all()
            return list(ex_cones)

        except SQLAlchemyError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Database error while fetching exclusion cones: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while fetching exclusion cones: {str(e)}",
            )

    @staticmethod
    def get_exclusion_cone(
        db: Session,
        ex_cone_id: uuid.UUID,
        current_user: UserModel,
    ) -> ExclusionCone:
        try:
            stmt = select(ExclusionCone).where(ExclusionCone.id == ex_cone_id)
            ex_cone = db.exec(stmt).first()

            if not ex_cone:
                raise HTTPException(
                    status_code=404,
                    detail=f"Exclusion cone with ID {ex_cone_id} not found",
                )

            # Mission scoping for mission roles
            if is_mission_role(current_user):
                if (
                    current_user.mission_id is None
                    or ex_cone.mission_id != current_user.mission_id
                ):
                    raise HTTPException(
                        status_code=403,
                        detail="Not allowed to view this exclusion cone",
                    )

            return ex_cone

        except HTTPException as http_e:
            raise http_e
        except SQLAlchemyError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Database error while fetching exclusion cone {ex_cone_id}: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while fetching exclusion cone {ex_cone_id}: {str(e)}",
            )

    @staticmethod
    def update_exclusion_cone(
        db: Session,
        cone_id: uuid.UUID,
        exclusion_cone: ExclusionConeUpdateModel,
        current_user: UserModel,
    ) -> ExclusionCone:
        try:
            existing_ex_cone = ExclusionConeService.get_exclusion_cone(
                db, cone_id, current_user
            )

            # Only system_admin or mission_admin (for their mission) can update
            if current_user.role not in (SYSTEM_ADMIN, MISSION_ADMIN):
                raise HTTPException(
                    status_code=403, detail="Not allowed to update exclusion cones"
                )

            if (
                current_user.role == MISSION_ADMIN
                and current_user.mission_id is not None
                and existing_ex_cone.mission_id != current_user.mission_id
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Not allowed to update cones for other missions",
                )

            update_data = exclusion_cone.model_dump(exclude_unset=True)

            # If satellite_id changes, re-check mission scoping
            if "satellite_id" in update_data:
                sat = SatelliteService.get_satellite(
                    db, update_data["satellite_id"], current_user
                )
                if sat is None:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Satellite with ID {update_data['satellite_id']} not found",
                    )
                if (
                    current_user.role == MISSION_ADMIN
                    and current_user.mission_id is not None
                    and sat.mission_id != current_user.mission_id
                ):
                    raise HTTPException(
                        status_code=403,
                        detail="Mission admins can only update cones for their own mission's satellites",
                    )
                existing_ex_cone.mission_id = sat.mission_id

            for key, value in update_data.items():
                setattr(existing_ex_cone, key, value)

            db.commit()
            db.refresh(existing_ex_cone)
            return existing_ex_cone

        except HTTPException as http_e:
            raise http_e
        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(
                status_code=503,
                detail=f"Database error while updating exclusion cone {cone_id}: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while updating exclusion cone {cone_id}: {str(e)}",
            )

    @staticmethod
    def delete_exclusion_cone(
        db: Session,
        ex_cone_id: uuid.UUID,
        current_user: UserModel,
    ) -> ExclusionCone:
        try:
            exclusion_cone = ExclusionConeService.get_exclusion_cone(
                db, ex_cone_id, current_user
            )

            if current_user.role not in (SYSTEM_ADMIN, MISSION_ADMIN):
                raise HTTPException(
                    status_code=403, detail="Not allowed to delete exclusion cones"
                )

            if (
                current_user.role == MISSION_ADMIN
                and current_user.mission_id is not None
                and exclusion_cone.mission_id != current_user.mission_id
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Not allowed to delete cones for other missions",
                )

            db.delete(exclusion_cone)
            db.commit()
            return exclusion_cone

        except HTTPException as http_e:
            raise http_e
        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(
                status_code=503,
                detail=f"Database error while deleting exclusion cone {ex_cone_id}: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while deleting exclusion cone {ex_cone_id}: {str(e)}",
            )
