"""See docs/ARCHITECTURE.md's "SPA fallback route" - a client-side route
like /explore has no matching file on disk,
so a hard refresh/bookmark 404s without a fallback to index.html. Verified
live (not just designed) that the naive "mount StaticFiles(html=True) at
'/', then add a catch-all route after it" approach doesn't actually work:
a Mount("/") matches every path first and Starlette commits to it, so a
route registered after it is never reached even for a path the mount
itself 404s on - main.py's single combined catch-all route is what
actually has to do both jobs."""

from roleplay_agent.main import UI_DIST_DIR


def test_root_serves_index_html(client, app_env):
    response = client.get("/")
    assert response.status_code == 200
    assert "<html" in response.text.lower()


def test_client_side_route_falls_back_to_index_html(client, app_env):
    response = client.get("/explore")
    assert response.status_code == 200
    assert response.text == (UI_DIST_DIR / "index.html").read_text()


def test_nested_client_side_route_falls_back_to_index_html(client, app_env):
    response = client.get("/games/some-id/edit")
    assert response.status_code == 200
    assert response.text == (UI_DIST_DIR / "index.html").read_text()


def test_real_static_asset_is_served_as_is(client, app_env):
    assets = list((UI_DIST_DIR / "assets").glob("*.js"))
    assert assets, "expected at least one built JS asset under dev-ui/dist/assets"
    asset = assets[0]

    response = client.get(f"/assets/{asset.name}")

    assert response.status_code == 200
    assert response.content == asset.read_bytes()
    assert "javascript" in response.headers["content-type"]


def test_top_level_static_file_is_served_as_is(client, app_env):
    response = client.get("/profile-avatar.svg")
    assert response.status_code == 200
    assert response.content == (UI_DIST_DIR / "profile-avatar.svg").read_bytes()


def test_api_routes_are_unaffected_by_the_catch_all(client, app_env):
    response = client.get("/api/games")
    assert response.status_code == 200
    assert response.json() == []


def test_missing_api_route_still_404s_not_index_html(client, app_env):
    # /api/* is claimed by the real routers registered before the
    # catch-all, so an unmatched path under /api should still be a normal
    # 404, not silently served the SPA shell.
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404


def test_path_traversal_cannot_escape_ui_dist_dir(client, app_env):
    response = client.get("/..%2f..%2f..%2fetc%2fpasswd")
    assert response.status_code == 200
    assert response.text == (UI_DIST_DIR / "index.html").read_text()
