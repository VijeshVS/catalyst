"""Flag-gated ranking for the Reelwise demo.

The ranking is intentionally readable: a baseline popularity score plus a
location boost and a genre-affinity boost, each of which only runs when its
Catalyst flag says yes. Every card carries the signals that moved it, so the
audience simulator explains itself instead of asking for trust.
"""

from __future__ import annotations

from typing import Any

from catalog import CATALOG, COUNTRY_LABELS

RAIL_SIZE = 8
SHELF_SIZE = 4
LOCATION_BOOST = 34.0
GENRE_BOOST = 30.0
POPULARITY_WEIGHT = 0.6


def _card(video: dict[str, Any], signals: list[str], score: float) -> dict[str, Any]:
    """Shape one catalogue row for the frontend, without internal weights."""
    return {
        "id": video["id"],
        "title": video["title"],
        "year": video["year"],
        "genres": video["genres"],
        "regions": video["regions"],
        "runtime": video["runtime"],
        "rating": video["rating"],
        "tagline": video["tagline"],
        "hue": video["hue"],
        "premium": video["premium"],
        # A presentation-friendly score. It is derived, never used to decide.
        "match": min(99, max(50, round(50 + score * 0.4))),
        "signals": signals,
    }


def rank_personalized(
    country: str,
    genre: str,
    *,
    use_location: bool,
    use_genre: bool,
) -> list[dict[str, Any]]:
    """Rank the catalogue for one viewer with the enabled signals."""
    scored: list[tuple[float, dict[str, Any], list[str]]] = []

    for video in CATALOG:
        score = video["popularity"] * POPULARITY_WEIGHT
        signals: list[str] = []

        if use_location and country and country in video["regions"]:
            score += LOCATION_BOOST
            signals.append(f"Popular in {COUNTRY_LABELS.get(country, country)}")

        if use_genre and genre and genre in video["genres"]:
            score += GENRE_BOOST
            signals.append(f"Matches your {genre} history")

        if not signals:
            signals.append("Trending worldwide")

        scored.append((score, video, signals))

    scored.sort(key=lambda row: (-row[0], row[1]["title"]))
    return [
        _card(video, signals, score)
        for score, video, signals in scored[:RAIL_SIZE]
    ]


def trending() -> list[dict[str, Any]]:
    """The fallback rail used when the master switch is off."""
    ordered = sorted(CATALOG, key=lambda video: (-video["popularity"], video["title"]))
    return [
        _card(video, ["Trending worldwide"], video["popularity"] * POPULARITY_WEIGHT)
        for video in ordered[:RAIL_SIZE]
    ]


def early_access_shelf(recommended_ids: set[str]) -> list[dict[str, Any]]:
    """Premium titles the main rail did not already show, newest first."""
    pool = [video for video in CATALOG if video["id"] not in recommended_ids]
    premium = sorted(
        (video for video in pool if video["premium"]),
        key=lambda video: (-video["popularity"], video["title"]),
    )
    newest = sorted(
        (video for video in pool if not video["premium"]),
        key=lambda video: (-video["year"], -video["popularity"]),
    )

    shelf: list[dict[str, Any]] = []
    for video in premium:
        shelf.append(
            _card(video, ["Early access for Premium"], video["popularity"] * 0.6)
        )
    for video in newest:
        if len(shelf) >= SHELF_SIZE:
            break
        shelf.append(_card(video, ["New this season"], video["popularity"] * 0.6))

    return shelf[:SHELF_SIZE]
