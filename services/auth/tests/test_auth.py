import pytest
from httpx import AsyncClient


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"

VALID_USER = {
    "email": "test@example.com",
    "password": "StrongPass1",
    "full_name": "Test User",
    "role": "candidate",
}


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    response = await client.post(REGISTER_URL, json=VALID_USER)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == VALID_USER["email"]
    assert data["role"] == "candidate"
    assert "id" in data
    assert "hashed_password" not in data  # никогда не возвращаем хеш


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    await client.post(REGISTER_URL, json=VALID_USER)
    response = await client.post(REGISTER_URL, json=VALID_USER)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    payload = {**VALID_USER, "email": "weak@example.com", "password": "weakpass"}
    response = await client.post(REGISTER_URL, json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await client.post(REGISTER_URL, json=VALID_USER)
    response = await client.post(LOGIN_URL, json={
        "email": VALID_USER["email"],
        "password": VALID_USER["password"],
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post(REGISTER_URL, json=VALID_USER)
    response = await client.post(LOGIN_URL, json={
        "email": VALID_USER["email"],
        "password": "WrongPass1",
    })
    assert response.status_code == 401
    # Не раскрываем что именно неверно
    assert "Invalid email or password" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient):
    await client.post(REGISTER_URL, json=VALID_USER)
    login_resp = await client.post(LOGIN_URL, json={
        "email": VALID_USER["email"],
        "password": VALID_USER["password"],
    })
    token = login_resp.json()["access_token"]

    response = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == VALID_USER["email"]


@pytest.mark.asyncio
async def test_get_me_no_token(client: AsyncClient):
    response = await client.get(ME_URL)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    await client.post(REGISTER_URL, json=VALID_USER)
    login_resp = await client.post(LOGIN_URL, json={
        "email": VALID_USER["email"],
        "password": VALID_USER["password"],
    })
    refresh_token = login_resp.json()["refresh_token"]

    response = await client.post(REFRESH_URL, json={"refresh_token": refresh_token})
    assert response.status_code == 200
    new_data = response.json()
    assert "access_token" in new_data
    # Новый refresh токен должен отличаться (rotation)
    assert new_data["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_logout(client: AsyncClient):
    await client.post(REGISTER_URL, json=VALID_USER)
    login_resp = await client.post(LOGIN_URL, json={
        "email": VALID_USER["email"],
        "password": VALID_USER["password"],
    })
    tokens = login_resp.json()

    # Logout
    logout_resp = await client.post(LOGOUT_URL, json={
        "refresh_token": tokens["refresh_token"]
    })
    assert logout_resp.status_code == 204

    # Используем отозванный токен
    response = await client.post(REFRESH_URL, json={
        "refresh_token": tokens["refresh_token"]
    })
    assert response.status_code == 401
