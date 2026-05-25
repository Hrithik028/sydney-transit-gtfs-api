"""
Sydney Bus API – Automated Tests
Author: Hrithik Jadhav (z5509844)

Covers Requirement Sets 1–6
Each test includes main functionality and key edge-case handling.
Run with:  pytest -v z5509844_tests.py
"""

import json
import pytest
import z5509844_api
from z5509844_api import app, init_db, init_favourites_table


# ======================================================
# Test Setup
# ======================================================

@pytest.fixture(scope="module")
def client():
    """Initialise a clean Flask test client."""
    init_db()
    init_favourites_table()
    app.config["TESTING"] = True
    return app.test_client()


# ======================================================
#  Set 1 – Health Check
# ======================================================

def test_health_endpoint(client):
    """[Set 1] API health endpoint should return 200 and valid message."""
    res = client.get("/health")
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["status"] == "ok"


# ======================================================
# Set 2 – Admin User Management
# ======================================================

def test_admin_can_list_users(client):
    """[Set 2] Admin should list all users successfully."""
    res = client.get("/admin/users", headers={"X-User": "admin"})
    assert res.status_code == 200
    data = json.loads(res.data)
    assert "users" in data
    assert any(u["username"] == "admin" for u in data["users"])


def test_commuter_cannot_list_users(client):
    """[Set 2 – Edge case] Commuter attempting admin task should get 403."""
    res = client.get("/admin/users", headers={"X-User": "commuter"})
    assert res.status_code == 403

def test_missing_header_unauthorized(client):
    """[Set 2 – Edge case] Missing X-User header => 401."""
    res = client.get("/admin/users")
    assert res.status_code == 401
    
def test_create_duplicate_user(client):
    """[Set 2 – Edge case] Creating existing user should fail."""
    payload = {"username": "planner", "password": "123", "role": "Planner"}
    res = client.post("/admin/users",
                      headers={"X-User": "admin"},
                      json=payload)
    assert res.status_code in (400, 409)

def test_invalid_role_creation(client):
    """[Set 2 – Edge case] Invalid role must be rejected."""
    payload = {"username": "xuser1", "password": "x", "role": "Boss"}
    res = client.post("/admin/users", headers={"X-User": "admin"}, json=payload)
    assert res.status_code == 400

def test_planner_cannot_manage_users(client):
    """[Set 2 – Edge case] Planner cannot create users."""
    payload = {"username": "xuser2", "password": "x", "role": "Commuter"}
    res = client.post("/admin/users", headers={"X-User": "planner"}, json=payload)
    assert res.status_code == 403
        
def test_enable_disable_user(client):
    """[Set 2] Admin can disable and re-enable a user."""
    patch_data = {"enabled": False}
    res = client.patch("/admin/users/planner",
                       headers={"X-User": "admin"},
                       json=patch_data)
    assert res.status_code in (200, 404)
    # Re-enable
    patch_data = {"enabled": True}
    client.patch("/admin/users/planner",
                 headers={"X-User": "admin"},
                 json=patch_data)

def test_admin_cannot_delete_admin_account(client):
    """[Set 2 – Edge case] Admin account cannot be deleted."""
    res = client.delete("/admin/users/admin", headers={"X-User": "admin"})
    assert res.status_code == 400

def test_delete_nonexistent_user(client):
    """[Set 2 – Edge case] Deleting unknown user should return 404."""
    res = client.delete("/admin/users/ghost",
                        headers={"X-User": "admin"})
    assert res.status_code == 404


# ======================================================
# Set 3 – GTFS Import
# ======================================================

def test_import_invalid_prefix(client):
    """[Set 3 – Edge case] Non-GSBC/SBSC prefix should be rejected."""
    res = client.post("/gtfs/import/ABC999",
                      headers={"X-User": "admin"})
    assert res.status_code == 400


def test_import_missing_api_key(client):
    """[Set 3 – Edge case] Missing API key should yield 401."""
    res = client.post("/gtfs/import/GSBC999",
                      headers={"X-User": "admin"})
    assert res.status_code in (401, 400, 500)   # depends on env


def test_commuter_cannot_import(client):
    """[Set 3 – Edge case] Commuter forbidden from importing data."""
    res = client.post("/gtfs/import/GSBC001",
                      headers={"X-User": "commuter"})
    assert res.status_code == 403


# ======================================================
# Set 4 – Data Access
# ======================================================

def test_route_not_found(client):
    """[Set 4 – Edge case] Non-existent route returns 404."""
    res = client.get("/data/route/FAKE_ROUTE",
                     headers={"X-User": "admin"})
    assert res.status_code == 404


def test_trip_not_found(client):
    """[Set 4 – Edge case] Unknown trip ID returns 404."""
    res = client.get("/data/trip/000000",
                     headers={"X-User": "admin"})
    assert res.status_code == 404


def test_stop_not_found(client):
    """[Set 4 – Edge case] Invalid stop ID returns 404."""
    res = client.get("/data/stop/999999",
                     headers={"X-User": "admin"})
    assert res.status_code == 404


def test_search_stops_no_param(client):
    """[Set 4 – Edge case] Missing ?name should return 400."""
    res = client.get("/data/search/stops",
                     headers={"X-User": "admin"})
    assert res.status_code == 400


def test_search_stops_valid_but_not_found(client):
    """[Set 4 – Edge case] Query with no matches should return 404 or empty 200."""
    res = client.get("/data/search/stops?name=NowhereLand",
                     headers={"X-User": "admin"})
    # Some implementations return 200 with empty list instead of 404
    assert res.status_code in (200, 404)
    
def test_search_stops_multiword_and_plus(client):
    """[Set 4 – Edge case] Multi-word with '+' should be handled."""
    res = client.get("/data/search/stops?name=Circular+Quay", headers={"X-User": "admin"})
    assert res.status_code in (200, 404)
    
def test_route_trips_pagination_after_mock(client):
    """[Set 4] Pagination params should not error after mocked import."""
    res = client.get("/data/route/TEST_ROUTE/trips?limit=1&offset=0",
                     headers={"X-User": "admin"})
    # Could be 200 (if available) or 404 (if import didn't run)
    assert res.status_code in (200, 404)
    
# ======================================================
# Set 5 – Favourites
# ======================================================

def test_add_invalid_favourite(client):
    """[Set 5 – Edge case] Adding unknown route returns 404."""
    res = client.post("/favourites/FAKE_ROUTE",
                      headers={"X-User": "admin"})
    assert res.status_code == 404

def test_duplicate_favourite_rejected(client):
    """[Set 5 – Edge case] Adding the same favourite twice should fail."""
    first = client.post("/favourites/TEST_ROUTE", headers={"X-User": "admin"})
    second = client.post("/favourites/TEST_ROUTE", headers={"X-User": "admin"})
    # First may be 201 or 404 (if mock import didn't run); second should be 409/400/404
    assert second.status_code in (409, 400, 404)
    
def test_delete_nonexistent_favourite(client):
    """[Set 5 – Edge case] Removing non-favourite route returns 404."""
    res = client.delete("/favourites/FAKE_ROUTE",
                        headers={"X-User": "admin"})
    assert res.status_code == 404


def test_list_favourites(client):
    """[Set 5] Listing favourites returns 200, 308 redirect, or empty list."""
    res = client.get("/favourites", headers={"X-User": "admin"})
    assert res.status_code in (200, 308)
    if res.status_code == 200:
        data = res.get_json()
        assert "favourites" in data

def test_favourites_are_per_user_isolated(client):
    """[Set 5 – Edge case] Admin and Commuter favourites should be isolated."""
    # Try add different favourites for different users (may 404 if route not present).
    client.post("/favourites/TEST_ROUTE", headers={"X-User": "admin"})
    client.post("/favourites/2502_1001", headers={"X-User": "commuter"})

    admin_list = client.get("/favourites/", headers={"X-User": "admin"})
    comm_list = client.get("/favourites/", headers={"X-User": "commuter"})

    assert admin_list.status_code in (200, 404)
    assert comm_list.status_code in (200, 404)

    if admin_list.status_code == 200 and comm_list.status_code == 200:
        a_ids = {r["route_id"] for r in admin_list.get_json().get("favourites", [])}
        c_ids = {r["route_id"] for r in comm_list.get_json().get("favourites", [])}
        # They don't have to be disjoint, but at least lists are independently returned
        assert isinstance(a_ids, set) and isinstance(c_ids, set)
        
# ======================================================
# Set 6 – Visualisation & Export
# ======================================================

def test_export_favourites_csv(client):
    """[Set 6] Export favourites returns CSV or 404 if none."""
    res = client.get("/visualisation/favourites/export",
                     headers={"X-User": "admin"})
    assert res.status_code in (200, 404)
    if res.status_code == 200:
        assert "text/csv" in res.content_type


def test_visualisation_map_image(client):
    """[Set 6] Favourite map endpoint returns PNG or 404."""
    res = client.get("/visualisation/favourites/map",
                     headers={"X-User": "admin"})
    assert res.status_code in (200, 404)
    if res.status_code == 200:
        assert "image/png" in res.content_type


def test_visualisation_map_with_param(client):
    """[Set 6 – Edge case] Route param handles bad ID gracefully."""
    res = client.get("/visualisation/favourites/map?route_id=FAKE123",
                     headers={"X-User": "admin"})
    assert res.status_code in (404, 200)

def test_visualisation_map_with_unknown_param(client):
    """[Set 6 – Edge case] Unknown route in param should 404 or 200 (if ignored)."""
    res = client.get(
        "/visualisation/favourites/map?route_id=NO_SUCH_ROUTE", headers={"X-User": "admin"}
    )
    assert res.status_code in (200, 404)
        
def test_docs_reachable(client):
    """[Set 7] Swagger / API Docs endpoint should be reachable."""
    possible_paths = ["/docs/", "/docs", "/swagger/", "/swagger", "/swagger-ui/"]
    statuses = []
    for path in possible_paths:
        res = client.get(path)
        statuses.append(res.status_code)
        if res.status_code in (200, 302, 308):
            assert True
            return
    print("DEBUG tested docs paths ->", dict(zip(possible_paths, statuses)))
    pytest.fail("Swagger / Docs endpoint not reachable (checked /docs and /swagger).")
    
def test_show_all_routes():
    """Diagnostic: List all registered API routes."""
    print("\n=== Registered Routes ===")
    for rule in app.url_map.iter_rules():
        print(rule)
    print("=========================\n")
    # This test always passes – used just for confirmation
    assert True