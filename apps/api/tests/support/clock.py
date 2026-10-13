from datetime import datetime


def frozen_datetime(moment):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment.astimezone(tz) if tz is not None else moment.replace(tzinfo=None)

    return FrozenDatetime
