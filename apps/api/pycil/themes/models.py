"""Theme identity; themed lexical and study content remain in their domains."""

from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pycil.infrastructure.database import Base


class Theme(Base):
    __tablename__ = "themes"
    __table_args__ = (CheckConstraint("id > 0 AND length(btrim(key)) > 0", name="identity"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(Text)
    voice: Mapped[str] = mapped_column(Text)
    diction: Mapped[str] = mapped_column(Text)
