from app.database.database import create_tables


if __name__ == "__main__":

    create_tables()

    print(
        "VDSS database initialized successfully."
    )