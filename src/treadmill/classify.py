"""Active segments and walking vs assumed-sitting labelling (spec §1, §2)."""

from dataclasses import dataclass
from datetime import datetime

WALKING = "walking"
SITTING = "sitting"


@dataclass(frozen=True)
class Segment:
    """A stretch of active (not-AFK) time in one app window."""

    start: datetime
    end: datetime
    app: str
    title: str

    @property
    def seconds(self) -> float:
        return (self.end - self.start).total_seconds()


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime


def clip(segments: list[Segment], start: datetime, end: datetime) -> list[Segment]:
    """Clip segments to [start, end) and drop zero-length ones."""
    out = []
    for s in segments:
        a, b = max(s.start, start), min(s.end, end)
        if b > a:
            out.append(Segment(a, b, s.app, s.title))
    return out


def label(segments: list[Segment], walks: list[Interval]) -> list[tuple[Segment, str]]:
    """Split segments at walk boundaries and label each piece walking or sitting (§2)."""
    out = []
    for s in segments:
        cuts = sorted(
            {t for w in walks for t in (w.start, w.end) if s.start < t < s.end} | {s.start, s.end}
        )
        for a, b in zip(cuts, cuts[1:]):
            walking = any(w.start <= a and b <= w.end for w in walks)
            out.append((Segment(a, b, s.app, s.title), WALKING if walking else SITTING))
    return out
