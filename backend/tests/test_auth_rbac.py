from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.database import get_db
from app.main import app
from app.security.auth import hash_password, seed_default_users
from app.db.models.user import User


def test_auth_login_and_rbac_permissions() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        with test_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        # Seed default users
        with test_session() as session:
            seed_default_users(session)

        # 1. Login success - Investigator
        login_res = client.post(
            "/api/auth/login",
            json={"email": "investigator@forensecure.local", "password": "Investigator@123"},
        )
        assert login_res.status_code == 200
        inv_data = login_res.json()
        assert "access_token" in inv_data
        assert inv_data["user"]["role"] == "investigator"
        inv_token = inv_data["access_token"]

        # 2. Login success - Officer
        off_res = client.post(
            "/api/auth/login",
            json={"email": "officer1@forensecure.local", "password": "Officer@123"},
        )
        assert off_res.status_code == 200
        off_data = off_res.json()
        assert off_data["user"]["role"] == "authorized_officer"
        off_token = off_data["access_token"]

        # 3. Login failure - wrong password
        fail_res = client.post(
            "/api/auth/login",
            json={"email": "investigator@forensecure.local", "password": "WrongPassword!"},
        )
        assert fail_res.status_code == 401

        # 4. Inactive user blocked
        with test_session() as session:
            inactive_user = User(
                name="Inactive",
                email="inactive@forensecure.local",
                password_hash=hash_password("Pass@123"),
                role="investigator",
                active=False,
            )
            session.add(inactive_user)
            session.commit()

        inactive_res = client.post(
            "/api/auth/login",
            json={"email": "inactive@forensecure.local", "password": "Pass@123"},
        )
        assert inactive_res.status_code == 401

        # 5. /api/auth/me with valid token
        me_res = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {inv_token}"},
        )
        assert me_res.status_code == 200
        assert me_res.json()["email"] == "investigator@forensecure.local"

        # 6. Logout endpoint
        logout_res = client.post("/api/auth/logout")
        assert logout_res.status_code == 200

        # 7. Signup endpoint - creates real user & returns token
        signup_res = client.post(
            "/api/auth/signup",
            json={
                "name": "Detective Miller",
                "email": "miller@police.gov",
                "password": "MillerPassword@2026",
                "role": "investigator",
            },
        )
        assert signup_res.status_code == 201
        signup_data = signup_res.json()
        assert "access_token" in signup_data
        assert signup_data["user"]["name"] == "Detective Miller"
        assert signup_data["user"]["role"] == "investigator"

        # 8. Signup conflict check
        dup_res = client.post(
            "/api/auth/signup",
            json={
                "name": "Duplicate",
                "email": "miller@police.gov",
                "password": "Password123!",
                "role": "investigator",
            },
        )
        assert dup_res.status_code == 409

        # 9. Supabase sync endpoint - syncs user profile and produces JWT
        sync_res = client.post(
            "/api/auth/supabase-sync",
            json={
                "supabase_id": "supabase-uuid-12345678",
                "email": "agent.smith@supa.gov",
                "name": "Agent Smith",
                "role": "authorized_officer",
            },
        )
        assert sync_res.status_code == 200
        sync_data = sync_res.json()
        assert "access_token" in sync_data
        assert sync_data["user"]["id"] == "supabase-uuid-12345678"
        assert sync_data["user"]["email"] == "agent.smith@supa.gov"
        assert sync_data["user"]["role"] == "authorized_officer"

    finally:
        app.dependency_overrides.clear()

