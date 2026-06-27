from db.schema import init_db
from services.auth import bootstrap_admin
from ui.app import run_app


def main():
    init_db()
    bootstrap_admin()
    run_app()


if __name__ == "__main__":
    main()
