def test_get_cloned_voices_lists_discovered_wavs_excluding_presets(client, app_env):
    voice_samples_dir = app_env / "voice_samples"
    voice_samples_dir.mkdir(parents=True, exist_ok=True)
    (voice_samples_dir / "ryan.wav").write_bytes(b"x")  # a preset - excluded
    (voice_samples_dir / "rosa.wav").write_bytes(b"x")

    response = client.get("/api/voices/cloned")

    assert response.status_code == 200
    assert response.json() == {"voices": ["rosa"]}


def test_get_cloned_voices_empty_when_no_samples_dir(client, app_env):
    response = client.get("/api/voices/cloned")

    assert response.status_code == 200
    assert response.json() == {"voices": []}
