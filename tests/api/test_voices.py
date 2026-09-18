import io
import wave


def _wav_bytes(*, channels=1, sample_rate=24000, sample_width=2, duration=2.0) -> bytes:
    n_frames = int(sample_rate * duration)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00" * n_frames * channels * sample_width)
    return buf.getvalue()


def test_get_cloned_voices_lists_discovered_wavs_excluding_presets(client, app_env):
    voice_samples_dir = app_env / "voice_samples"
    voice_samples_dir.mkdir(parents=True, exist_ok=True)
    (voice_samples_dir / "ryan.wav").write_bytes(b"x")  # a preset - excluded
    (voice_samples_dir / "rosa.wav").write_bytes(b"x")

    response = client.get("/api/voices/cloned")

    assert response.status_code == 200
    assert response.json() == {"voices": [{"id": "rosa", "name": "Rosa", "image": None}]}


def test_get_cloned_voices_empty_when_no_samples_dir(client, app_env):
    response = client.get("/api/voices/cloned")

    assert response.status_code == 200
    assert response.json() == {"voices": []}


def test_get_cloned_voices_uses_sidecar_name_and_image(client, app_env):
    voice_samples_dir = app_env / "voice_samples"
    voice_samples_dir.mkdir(parents=True, exist_ok=True)
    (voice_samples_dir / "rosa.wav").write_bytes(b"x")
    (voice_samples_dir / "rosa.json").write_text('{"name": "Rosa Diaz"}')
    (voice_samples_dir / "rosa.png").write_bytes(b"x")

    response = client.get("/api/voices/cloned")

    assert response.json() == {"voices": [{"id": "rosa", "name": "Rosa Diaz", "image": "rosa.png"}]}


def test_create_cloned_voice_saves_wav_and_returns_info(client, app_env):
    response = client.post(
        "/api/voices/cloned",
        data={"name": "Nova Prime"},
        files={"wav": ("sample.wav", _wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 201
    assert response.json() == {"id": "nova-prime", "name": "Nova Prime", "image": None}
    assert (app_env / "voice_samples" / "nova-prime.wav").exists()
    assert (app_env / "voice_samples" / "nova-prime.json").exists()


def test_create_cloned_voice_with_profile_image(client, app_env):
    response = client.post(
        "/api/voices/cloned",
        data={"name": "Nova"},
        files={
            "wav": ("sample.wav", _wav_bytes(), "audio/wav"),
            "image": ("avatar.png", b"fake-png-bytes", "image/png"),
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["image"] == "nova.png"
    assert (app_env / "voice_samples" / "nova.png").read_bytes() == b"fake-png-bytes"


def test_create_cloned_voice_disambiguates_slug_on_name_collision(client, app_env):
    client.post("/api/voices/cloned", data={"name": "Nova"}, files={"wav": ("a.wav", _wav_bytes(), "audio/wav")})
    response = client.post("/api/voices/cloned", data={"name": "Nova"}, files={"wav": ("b.wav", _wav_bytes(), "audio/wav")})

    assert response.status_code == 201
    assert response.json()["id"] == "nova-2"


def test_create_cloned_voice_requires_a_name(client, app_env):
    response = client.post(
        "/api/voices/cloned",
        data={"name": "   "},
        files={"wav": ("sample.wav", _wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 422
    assert "Name is required" in response.json()["detail"]


def test_create_cloned_voice_rejects_stereo_with_reason(client, app_env):
    response = client.post(
        "/api/voices/cloned",
        data={"name": "Stereo Sam"},
        files={"wav": ("sample.wav", _wav_bytes(channels=2), "audio/wav")},
    )

    assert response.status_code == 422
    assert "mono" in response.json()["detail"].lower()


def test_create_cloned_voice_rejects_non_wav_with_reason(client, app_env):
    response = client.post(
        "/api/voices/cloned",
        data={"name": "Not Wav"},
        files={"wav": ("sample.wav", b"not a real wav file", "audio/wav")},
    )

    assert response.status_code == 422
    assert "valid wav" in response.json()["detail"].lower()


def test_create_cloned_voice_rejects_too_short_clip_with_reason(client, app_env):
    response = client.post(
        "/api/voices/cloned",
        data={"name": "Too Short"},
        files={"wav": ("sample.wav", _wav_bytes(duration=0.2), "audio/wav")},
    )

    assert response.status_code == 422
    assert "too short" in response.json()["detail"].lower()


def test_create_cloned_voice_rejects_unsupported_image_type(client, app_env):
    response = client.post(
        "/api/voices/cloned",
        data={"name": "Bad Image"},
        files={
            "wav": ("sample.wav", _wav_bytes(), "audio/wav"),
            "image": ("avatar.bmp", b"x", "image/bmp"),
        },
    )

    assert response.status_code == 422
    assert "Unsupported image type" in response.json()["detail"]
