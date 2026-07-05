"""Realtime: owner-scoped channel naming + subscription-token scoping."""

import uuid

import jwt
from shared.realtime import channels
from shared.realtime.payloads import GradingResult, JobUpdate

from pycil.config import settings
from pycil.realtime import client


def test_every_private_channel_embeds_owner_uid():
    uid = uuid.uuid4()
    assert channels.user_notifications(uid) == f"users:{uid}"
    assert channels.user_jobs(uid, "job1") == f"users:{uid}:jobs:job1"
    assert channels.user_grading(uid, "resp1") == f"users:{uid}:grading:resp1"


def test_channels_for_two_users_do_not_collide():
    a, b = uuid.uuid4(), uuid.uuid4()
    # Same enumerable job id, different owners → distinct, owner-prefixed channels.
    assert channels.user_jobs(a, "1") != channels.user_jobs(b, "1")
    assert channels.user_jobs(a, "1").startswith(f"users:{a}")
    assert channels.user_jobs(b, "1").startswith(f"users:{b}")


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


def test_user_a_token_scoped_away_from_user_b_channel():
    """A's token subject is A's uid; Centrifugo grants only users:{A}:* — B's
    channel carries B's uid, which A's token subject can never match."""
    a, b = uuid.uuid4(), uuid.uuid4()
    a_token = client.sign_subscription_token(a)
    a_sub = jwt.decode(
        a_token, settings.centrifugo_token_hmac_secret, algorithms=["HS256"]
    )["sub"]
    b_channel = channels.user_jobs(b, "1")
    # The channel A would be authorized for is users:{A}:* — B's channel is not.
    assert not b_channel.startswith(f"users:{a_sub}")


def test_payload_serialization():
    job = JobUpdate(job_id="j1", status="done", detail="ok")
    assert job.to_dict() == {"job_id": "j1", "status": "done", "detail": "ok"}
    grade = GradingResult(
        response_id="r1", sense_id=42, is_correct=True, grade_score=1.0
    )
    d = grade.to_dict()
    assert d["sense_id"] == 42 and d["is_correct"] is True
