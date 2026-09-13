"""Общий бюджет: доступ как у привычек, одна книга операций на всех."""

from httpx import AsyncClient


async def _register_login(client: AsyncClient, email: str) -> dict[str, str]:
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password99", "display_name": "B"},
    )
    assert r.status_code == 201, r.text
    r = await client.post("/api/auth/login", json={"email": email, "password": "password99"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _user_id(client: AsyncClient, admin: dict[str, str], email: str) -> str:
    users = await client.get("/api/admin/users", headers=admin)
    assert users.status_code == 200, users.text
    return next(u["id"] for u in users.json() if u["email"] == email)


async def test_budget_forbidden_when_admin_revokes(client: AsyncClient) -> None:
    admin = await _register_login(client, "tagtest@example.com")
    guest = await _register_login(client, "budget.guest@example.com")
    guest_id = await _user_id(client, admin, "budget.guest@example.com")
    patched = await client.patch(
        f"/api/admin/users/{guest_id}",
        headers=admin,
        json={"can_use_budget": False},
    )
    assert patched.status_code == 200, patched.text
    denied = await client.get("/api/budget/health", headers=guest)
    assert denied.status_code == 403


async def test_budget_shared_ledger_for_granted_users(client: AsyncClient) -> None:
    admin = await _register_login(client, "tagtest@example.com")
    ok = await client.get("/api/budget/health", headers=admin)
    assert ok.status_code == 200, ok.text

    created = await client.post(
        "/api/budget/transactions",
        headers=admin,
        json={"kind": "expense", "amount": 120.5, "note": "хлеб", "occurred_on": "2026-09-12"},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["kind"] == "expense"
    assert body["amount"] == 120.5
    assert body["note"] == "хлеб"

    guest = await _register_login(client, "budget.viewer@example.com")
    shared = await client.get("/api/budget/transactions", headers=guest)
    assert shared.status_code == 200, shared.text
    notes = [t["note"] for t in shared.json()]
    assert "хлеб" in notes

    totals = await client.get("/api/budget/stats/totals-all-time", headers=guest)
    assert totals.status_code == 200, totals.text
    assert totals.json()["total_expense"] == 120.5
