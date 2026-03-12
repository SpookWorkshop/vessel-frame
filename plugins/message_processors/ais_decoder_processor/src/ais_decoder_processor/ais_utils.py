VESSEL_TYPES: dict[int, str] = {
    -1: "Unknown",
    0: "Unknown",
    20: "Wing in Ground",
    30: "Fishing",
    31: "Towing",
    32: "Towing (Large)",
    33: "Dredge",
    34: "Diving Vessel",
    35: "Military Ops",
    36: "Sailing",
    37: "Pleasure Craft",
    40: "High Speed Craft",
    50: "Pilot Vessel",
    51: "Search & Rescue",
    52: "Tug",
    53: "Port Tender",
    54: "Anti-pollution Equip.",
    55: "Law Enforcement",
    56: "Local",
    57: "Local",
    58: "Medical Transport",
    59: "Non-combatant Ship",
    60: "Passenger Ship",
    70: "Cargo Ship",
    80: "Tanker",
    90: "Other",
}

VESSEL_SUBCATS: dict[int, str] = {
    1: "Hazardous (High)",
    2: "Hazardous",
    3: "Hazardous (Low)",
    4: "Non-hazardous",
}


def get_vessel_type_name(type_code: int | None) -> str:
    """
    Return a descriptive vessel type name for a given AIS type code.

    Args:
        type_code (int | None): The AIS vessel type code. Can be `None` if unknown.

    Returns:
        str: A human-readable vessel type description, or:
            - "Unknown" if `type_code` is `None`
            - "Reserved" if the code doesn’t match any known type or base category
    """
    if type_code is None:
        return "Unknown"

    # Check exact match first
    vessel_type = VESSEL_TYPES.get(type_code)
    if vessel_type:
        return vessel_type

    # Try base category (first digit * 10)
    base_cat = (type_code // 10) * 10
    vessel_type = VESSEL_TYPES.get(base_cat)

    if vessel_type is None:
        return "Reserved"

    return vessel_type


def get_vessel_subtype_name(type_code: int | None) -> str | None:
    """
    Return the vessel subtype description for a given AIS type code.

    Subtypes indicate potential cargo type or level of hazardousness.

    Args:
        type_code (int | None): The AIS vessel type code. Can be `None` if unknown.

    Returns:
        str | None: A descriptive vessel subtype name if applicable, otherwise `None`.
    """
    if type_code is None:
        return None

    # If there's an exact match in VESSEL_TYPES, no subtype applies
    if type_code in VESSEL_TYPES:
        return None

    # Subtype only applies when using base category fallback
    sub_cat = type_code % 10
    return VESSEL_SUBCATS.get(sub_cat)


def get_vessel_full_type_name(type_code: int | None) -> str:
    """
    Return the combined vessel type and subtype description for a given AIS type code.

    The result includes both the main vessel type and, if applicable, the subtype
    (indicating cargo type or hazardousness).

    Args:
        type_code (int | None): The AIS vessel type code. Can be `None` if unknown.

    Returns:
        str: A human-readable vessel type description. Examples:
            - "Port Tender" (no subtype)
            - "Cargo Ship - Hazardous (High)" (with subtype)
    """
    main_type = get_vessel_type_name(type_code)
    sub_type = get_vessel_subtype_name(type_code)

    if sub_type is None:
        return main_type

    return f"{main_type} - {sub_type}"
