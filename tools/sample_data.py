"""Believable made-up drawing history for the picture-taking tools, so none of them ever touch the user's own data"""

from __future__ import annotations

import random
from datetime import date, timedelta

SAMPLE_SEED = 11


def fill_sample_history(store, seed: int = SAMPLE_SEED) -> None:
    """Ten weeks of plausible drawing sessions: most weekdays, some weekends, an hour or three at a time, then a
    session in progress today. The same seed always gives the same history"""
    rng = random.Random(seed)
    today = date.today()
    with store.connection:
        for days_ago in range(1, 71):
            day = today - timedelta(days=days_ago)
            if rng.random() < (0.45 if day.weekday() >= 5 else 0.2):
                continue
            start_hour = rng.choice((9, 10, 13, 14, 19, 20))
            minutes = rng.choice((35, 50, 75, 90, 110, 140, 170, 205))
            hour, remaining = start_hour, minutes * 60
            while remaining > 0 and hour < 24:
                seconds = min(remaining, rng.randint(2400, 3600))
                store.connection.execute(
                    "INSERT OR REPLACE INTO activity (day, slot, seconds, application) VALUES (?, ?, ?, 'Photoshop')", (day.isoformat(), hour, seconds)
                )
                remaining -= seconds
                hour += 1
            store.connection.execute(
                "INSERT OR IGNORE INTO session_starts (day, application, started_at) VALUES (?, 'Photoshop', ?)",
                (day.isoformat(), f"{start_hour:02d}:{rng.choice((5, 10, 20, 30, 40)):02d}"),
            )
            if rng.random() < 0.4:
                store.connection.execute("INSERT OR REPLACE INTO productivity_ratings (day, rating) VALUES (?, ?)", (day.isoformat(), rng.randint(5, 9)))
        # Today so far: a session in progress
        for hour, seconds in ((9, 2900), (10, 3400), (11, 1750)):
            store.connection.execute(
                "INSERT OR REPLACE INTO activity (day, slot, seconds, application) VALUES (?, ?, ?, 'Photoshop')", (today.isoformat(), hour, seconds)
            )
        store.connection.execute("INSERT OR IGNORE INTO session_starts (day, application, started_at) VALUES (?, 'Photoshop', '09:10')", (today.isoformat(),))
