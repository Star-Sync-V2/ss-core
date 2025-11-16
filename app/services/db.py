import logging
from sqlmodel import SQLModel, Field, Session, create_engine
from ..entities import *
from dotenv import load_dotenv
import os

load_dotenv()
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    #"postgresql://root:password@localhost:5432/ss_database" #used for testing
    "postgresql://root:password@ss-db:5432/ss_database"
)

engine = create_engine(DATABASE_URL)


def get_db():
    """
    Dependency to provide a database session.
    Ensures the session is properly closed after use.
    """
    with Session(engine, expire_on_commit=False) as session:
        yield session


def create_db_and_tables():
    """
    Create the database and tables.
    """
    # drop all tables first
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    print("Database and tables created")
    check_db()


def check_db():
    # select all tables from the database
    from sqlalchemy import text

    query = text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public';"
    )
    with Session(engine) as session:
        result = session.execute(query)
        print(result)
        for row in result:
            print(row)


def create_demo_data():
    from app.services.satellite import SatelliteService
    from app.services.ground_station import GroundStationService
    from app.models.satellite import SatelliteCreateModel
    from app.models.ground_station import GroundStationCreateModel

    """
    Create some demo data for the database.
    """
    with Session(engine) as session:
        # Create some satellites with real TLEs
        SatelliteService.create_satellite(
            session,
            SatelliteCreateModel(
                name="SCISAT 1",
                tle="1 27858U 03036A   24271.51787419  .00002340  00000+0  31635-3 0  9999\n2 27858  73.9336 337.0907 0007403 194.1129 165.9841 14.79656508138550",
                uplink=1,
                telemetry=1,
                science=1,
                priority=1,
            ),
        )

        SatelliteService.create_satellite(
            session,
            SatelliteCreateModel(
                name="NEOSSAT",
                tle="1 39089U 13009D   24271.52543360  .00000662  00000+0  24595-3 0  9997\n2 39089  98.4054  96.2203 0010420 322.4732  37.5725 14.35304192606691",
                uplink=2,
                telemetry=2,
                science=2,
                priority=2,
            ),
        )

        GroundStationService.create_ground_station(
            session,
            GroundStationCreateModel(
                name="Inuvik NorthWest",
                lat=68.3195,
                lon=-133.549,
                height=102.5,
                mask=5,
                uplink=40,
                downlink=100,
                science=100,
            ),
        )

        GroundStationService.create_ground_station(
            session,
            GroundStationCreateModel(
                name="Prince Albert",
                lat=53.2124,
                lon=-105.934,
                height=490.3,
                mask=5,
                uplink=40,
                downlink=100,
                science=100,
            ),
        )

        GroundStationService.create_ground_station(
            session,
            GroundStationCreateModel(
                name="Gatineau Quebec",
                lat=45.5846,
                lon=-75.8083,
                height=240.1,
                mask=5,
                uplink=40,
                downlink=100,
                science=100,
            ),
        )

        print("Demo data created successfully")
