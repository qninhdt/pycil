"""Realtime: owner-scoped user-limited channel naming and connection tokens."""

import uuid
from pathlib import Path

import jwt
from shared.realtime import channels
from shared.realtime.payloads import GradingResult, JobUpdate

from pycil.config import settings
from pycil.realtime import client


def test_every_private_channel_embeds_owner_uid():
    uid = uuid.uuid4()
    assert channels.user_notifications(uid) == f"users:{uid}#{uid}"
    assert channels.user_jobs(uid, "job1") == f"users:{uid}:jobs:job1#{uid}"
    assert channels.user_grading(uid, "resp1") == f"users:{uid}:grading:resp1#{uid}"


def test_channels_for_two_users_do_not_collide():
    a, b = uuid.uuid4(), uuid.uuid4()
    # Same enumerable job id, different owners → distinct, owner-prefixed channels.
    assert channels.user_jobs(a, "1") != channels.user_jobs(b, "1")
    assert channels.user_jobs(a, "1").startswith(f"users:{a}:")
    assert channels.user_jobs(b, "1").startswith(f"users:{b}:")
    assert channels.user_jobs(a, "1").endswith(f"#{a}")


def test_subscription_token_subject_is_the_user():
    uid = uuid.uuid4()
    token = client.sign_subscription_token(uid)
    claims = jwt.decode(
        token, settings.centrifugo_token_hmac_secret, algorithms=["HS256"]
    )
    assert claims["sub"] == str(uid)
    assert "exp" in claims and "iat" in claims


def test_token_signed_with_centrifugo_secret_not_api_jwt_secret():
    uid = uuid.uuid4()
    token = client.sign_subscription_token(uid)
    # Must NOT verify against the API's JWT secret — different key domain.
    import pytest

    with pytest.raises(jwt.PyJWTError):
        jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def test_user_a_channel_is_limited_to_user_a():
    """The native # boundary carries the identity Centrifugo checks at subscribe."""
    a, b = uuid.uuid4(), uuid.uuid4()
    a_token = client.sign_subscription_token(a)
    a_sub = jwt.decode(
        a_token, settings.centrifugo_token_hmac_secret, algorithms=["HS256"]
    )["sub"]
    b_channel = channels.user_jobs(b, "1")
    # A's channel boundary cannot be forged by changing the readable prefix.
    assert not b_channel.startswith(f"users:{a_sub}")
    assert b_channel.endswith(f"#{b}")


def test_centrifugo_config_denies_open_user_namespace_subscriptions():
    config = Path(__file__).parents[4] / "centrifugo-config.json"
    assert '"name": "users"' in config.read_text()
    assert '"allow_subscribe_for_client": false' in config.read_text()
    assert '"allow_user_limited_channels": true' in config.read_text()


def test_payload_serialization():
    job = JobUpdate(job_id="j1", status="done", detail="ok")
    assert job.to_dict() == {"job_id": "j1", "status": "done", "detail": "ok"}
    grade = GradingResult(
        response_id="r1", sense_id=42, is_correct=True, grade_score=1.0,
        mastery_before=10, mastery_after=20,
    )
    d = grade.to_dict()
    assert d["sense_id"] == 42 and d["is_correct"] is True
    assert d["mastery_before"] == 10 and d["mastery_after"] == 20
