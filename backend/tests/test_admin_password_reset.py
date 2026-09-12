from httpx import AsyncClient


async def test_admin_can_reset_password_and_old_one_stops_working(client: AsyncClient) -> None:
    admin = await client.post(
        "/api/auth/register",
        json={"email": "tagtest@example.com", "password": "password99", "display_name": "Admin"},
    )
    assert admin.status_code == 201, admin.text
    login = await client.post(
        "/api/auth/login", json={"email": "tagtest@example.com", "password": "password99"}
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    other = await client.post(
        "/api/auth/register",
        json={"email": "forgot@example.com", "password": "oldpass99", "display_name": "Forgot"},
    )
    assert other.status_code == 201, other.text
    uid = other.json()["id"]

    denied = await client.post(f"/api/admin/users/{uid}/reset-password")
    assert denied.status_code == 401

    reset = await client.post(f"/api/admin/users/{uid}/reset-password", headers=headers)
    assert reset.status_code == 200, reset.text
    body = reset.json()
    assert body["email"] == "forgot@example.com"
    new_pw = body["temporary_password"]
    assert len(new_pw) >= 8
    assert new_pw != "oldpass99"

    old = await client.post(
        "/api/auth/login", json={"email": "forgot@example.com", "password": "oldpass99"}
    )
    assert old.status_code == 401
    fresh = await client.post(
        "/api/auth/login", json={"email": "forgot@example.com", "password": new_pw}
    )
    assert fresh.status_code == 200, fresh.text

    token = fresh.json()["access_token"]
    uh = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/auth/me", headers=uh)
    assert me.status_code == 200
    assert me.json()["must_change_password"] is True

    same = await client.post(
        "/api/auth/change-password",
        headers=uh,
        json={"current_password": new_pw, "new_password": new_pw},
    )
    assert same.status_code == 400

    changed = await client.post(
        "/api/auth/change-password",
        headers=uh,
        json={"current_password": new_pw, "new_password": "ownpass99"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["must_change_password"] is False

    after = await client.post(
        "/api/auth/login", json={"email": "forgot@example.com", "password": "ownpass99"}
    )
    assert after.status_code == 200
