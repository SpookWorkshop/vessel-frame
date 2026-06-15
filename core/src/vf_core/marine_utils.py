"""AIS data and formatting helpers."""
from __future__ import annotations

import math
from typing import NamedTuple

__all__ = [
    "mmsi_country", "compass", "compass_full", "nav_status_label",
    "nav_status_short", "fmt_lat", "fmt_lon", "range_bearing",
]

# Nautical mile radius of the earth, for great-circle distances.
_EARTH_RADIUS_NM = 3440.065


class _NavStatus(NamedTuple):
    """Display labels for an AIS navigation status code."""
    label: str  # full label, eg: "Under Way Using Engine"
    short: str  # compact label for dense rows, eg: "under way"


# AIS navigation status codes that carry a meaningful display label. Reserved
# and undefined codes (9, 10, 13, 15) are intentionally omitted so both lookups
# fall back to "" for them, just as they do for None or any unknown code.
_NAV_STATUS: dict[int, _NavStatus] = {
    0: _NavStatus("Under Way Using Engine", "under way"),
    1: _NavStatus("At Anchor", "at anchor"),
    2: _NavStatus("Not Under Command", "not under command"),
    3: _NavStatus("Restricted Manoeuvrability", "restricted"),
    4: _NavStatus("Constrained By Draught", "constrained"),
    5: _NavStatus("Moored", "moored"),
    6: _NavStatus("Aground", "aground"),
    7: _NavStatus("Engaged In Fishing", "fishing"),
    8: _NavStatus("Under Way Sailing", "sailing"),
    11: _NavStatus("Towing Astern", "towing"),
    12: _NavStatus("Pushing Ahead", "pushing"),
    14: _NavStatus("AIS-SART Active", "SART"),
}


class _CompassPoint(NamedTuple):
    """A 16-point compass heading."""
    abbr: str  # abbreviation, eg: "ENE"
    name: str  # full name, eg: "EAST-NORTHEAST"


# Ordered N->NNW so headings map to points by index (see _compass_point).
_COMPASS: tuple[_CompassPoint, ...] = (
    _CompassPoint("N", "NORTH"),
    _CompassPoint("NNE", "NORTH-NORTHEAST"),
    _CompassPoint("NE", "NORTHEAST"),
    _CompassPoint("ENE", "EAST-NORTHEAST"),
    _CompassPoint("E", "EAST"),
    _CompassPoint("ESE", "EAST-SOUTHEAST"),
    _CompassPoint("SE", "SOUTHEAST"),
    _CompassPoint("SSE", "SOUTH-SOUTHEAST"),
    _CompassPoint("S", "SOUTH"),
    _CompassPoint("SSW", "SOUTH-SOUTHWEST"),
    _CompassPoint("SW", "SOUTHWEST"),
    _CompassPoint("WSW", "WEST-SOUTHWEST"),
    _CompassPoint("W", "WEST"),
    _CompassPoint("WNW", "WEST-NORTHWEST"),
    _CompassPoint("NW", "NORTHWEST"),
    _CompassPoint("NNW", "NORTH-NORTHWEST"),
)

_MID_COUNTRY: dict[str, str] = {
    "201": "Albania", "203": "Austria", "205": "Belgium", "206": "Belarus",
    "207": "Bulgaria", "209": "Cyprus", "210": "Cyprus", "211": "Germany",
    "212": "Cyprus", "213": "Georgia", "214": "Moldova", "215": "Malta",
    "216": "Armenia", "218": "Germany", "219": "Denmark", "220": "Denmark",
    "224": "Spain", "225": "Spain", "226": "France", "227": "France",
    "228": "France", "229": "Malta", "230": "Finland", "231": "Faroe Islands",
    "232": "United Kingdom", "233": "United Kingdom", "234": "United Kingdom",
    "235": "United Kingdom", "236": "Gibraltar", "237": "Greece",
    "239": "Greece", "240": "Greece", "241": "Greece", "244": "Netherlands",
    "245": "Netherlands", "246": "Netherlands", "247": "Italy",
    "248": "Malta", "249": "Malta", "250": "Ireland", "251": "Iceland",
    "253": "Luxembourg", "254": "Monaco", "255": "Portugal",
    "257": "Norway", "258": "Norway", "259": "Norway", "261": "Poland",
    "262": "Montenegro", "263": "Portugal", "264": "Romania",
    "265": "Sweden", "266": "Sweden", "267": "Slovakia", "268": "San Marino",
    "269": "Switzerland", "270": "Czech Republic", "271": "Turkey",
    "272": "Ukraine", "273": "Russia", "274": "North Macedonia",
    "275": "Latvia", "276": "Estonia", "277": "Lithuania",
    "278": "Slovenia", "279": "Serbia",
    "303": "United States", "305": "Antigua & Barbuda", "308": "Bahamas",
    "309": "Bahamas", "311": "Bahamas", "312": "Belize", "316": "Canada",
    "319": "Cayman Islands", "321": "Cuba", "338": "United States",
    "351": "Panama", "352": "Panama", "353": "Panama", "354": "Panama",
    "355": "Panama", "356": "Panama", "357": "Panama",
    "362": "Trinidad & Tobago", "366": "United States", "367": "United States",
    "368": "United States", "369": "United States", "370": "Panama",
    "371": "Panama", "372": "Panama", "373": "Panama", "374": "Panama",
    "375": "St Vincent & Grenadines", "376": "St Vincent & Grenadines",
    "377": "St Vincent & Grenadines",
    "403": "Saudi Arabia", "412": "China", "413": "China", "414": "China",
    "416": "Taiwan", "419": "India", "422": "Iran", "423": "Israel",
    "431": "Japan", "432": "Japan", "440": "South Korea", "441": "South Korea",
    "451": "Kuwait", "470": "United Arab Emirates", "477": "Hong Kong",
    "525": "Indonesia", "533": "Malaysia", "538": "Marshall Islands",
    "548": "Philippines", "557": "Singapore", "563": "Singapore",
    "564": "Singapore", "565": "Singapore", "566": "Singapore",
    "574": "Vietnam",
    "503": "Australia", "512": "New Zealand", "542": "New Zealand",
    "601": "South Africa", "606": "Somalia", "612": "Nigeria",
    "616": "Kenya", "620": "Egypt", "625": "Tanzania",
    "636": "Liberia", "638": "Ethiopia", "642": "Angola",
    "710": "Brazil", "720": "Argentina", "725": "Chile",
    "730": "Colombia", "735": "Ecuador", "745": "Peru",
    "750": "Uruguay", "760": "Venezuela",
}


def mmsi_country(mmsi: str) -> str:
    """Flag state for an MMSI from its Maritime Identification Digits, or empty string."""
    if not mmsi or len(mmsi) < 3:
        return ""
    return _MID_COUNTRY.get(mmsi[:3], "")


def _compass_point(deg: float) -> _CompassPoint:
    """The 16-point compass point nearest to a heading in degrees."""
    return _COMPASS[round(deg / 22.5) % 16]


def compass(deg: float) -> str:
    """16-point compass abbreviation (eg: "ENE") for a heading in degrees."""
    return _compass_point(deg).abbr


def compass_full(deg: float) -> str:
    """16-point compass name (eg: "EAST-NORTHEAST") for a heading."""
    return _compass_point(deg).name


def nav_status_label(status: int | None) -> str:
    """Full label for an AIS navigation status, or empty string if absent/reserved."""
    entry = _NAV_STATUS.get(status)
    return entry.label if entry else ""


def nav_status_short(status: int | None) -> str:
    """Short label for an AIS navigation status, or empty string if absent/reserved."""
    entry = _NAV_STATUS.get(status)
    return entry.short if entry else ""


def _format_coordinate(value: float, degree_digits: int, positive: str, negative: str) -> str:
    """Degrees-decimal-minutes string, eg: "53 27.51 N".

    degree_digits zero-pads the degrees field (2 for latitude, 3 for longitude);
    positive/negative are the hemisphere letters for the sign of value.
    """
    degrees = int(abs(value))
    minutes = (abs(value) - degrees) * 60
    hemisphere = positive if value >= 0 else negative
    return f"{degrees:0{degree_digits}d}° {minutes:05.2f}′ {hemisphere}"


def fmt_lat(lat: float) -> str:
    """Format a latitude as degrees-decimal-minutes, eg: "53 27.51 N."""
    return _format_coordinate(lat, 2, "N", "S")


def fmt_lon(lon: float) -> str:
    """Format a longitude as degrees-decimal-minutes, eg: "003 01.29 W"."""
    return _format_coordinate(lon, 3, "E", "W")


def range_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float]:
    """Great-circle distance (nautical miles) and initial bearing (degrees) from 1 to 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    d = 2 * _EARTH_RADIUS_NM * math.asin(min(1.0, math.sqrt(a)))
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    brg = (math.degrees(math.atan2(y, x)) + 360) % 360
    return d, brg
