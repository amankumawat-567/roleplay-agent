def test_list_skills_includes_registered_web_research_skill(client, app_env):
    response = client.get("/api/skills")

    assert response.status_code == 200
    body = response.json()
    ids = [s["id"] for s in body]
    assert "web_research" in ids

    web_research = next(s for s in body if s["id"] == "web_research")
    assert web_research["description"]  # non-empty, human-readable
    assert "\n" not in web_research["description"]  # collapsed to one line


def test_list_skills_includes_registered_schedule_followup_skill(client, app_env):
    response = client.get("/api/skills")

    ids = [s["id"] for s in response.json()]
    assert "schedule_followup" in ids
