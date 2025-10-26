VESSEL_TYPES = {
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
    90: "Other"
}

VESSEL_SUBCATS = {
    1: "Hazardous (High)",
    2: "Hazardous",
    3: "Hazardous (Low)",
    4: "Non-hazardous"
}

def get_vessel_type_name(type_code: int | None) -> str:
    """
    Get vessel type from AIS type code.
    
    Args:
        type_code: AIS vessel type code
        
    Returns:
        Vessel type description
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
    Get vessel subtype from AIS type code. Subtypes can indicate the potential cargo and level of hazardousness
    
    Args:
        type_code: AIS vessel type code
        
    Returns:
        Vessel type description
    """
    if type_code is None:
        return None

    sub_cat = type_code % 10
    sub_cat_type = VESSEL_SUBCATS.get(sub_cat)

    return sub_cat_type

def get_vessel_full_type_name(type_code: int | None) -> str:
     """
    Get vessel main and subtype from AIS type code.
    
    Args:
        type_code: AIS vessel type code
        
    Returns:
        Vessel type and subtype description if available
        eg:
         "Port Tender" [without subtype]
         "Cargo Ship - Hazardous (High)" [with subtype]
    """
    main_type = get_vessel_type_name(type_code)
    sub_type = get_vessel_subtype_name(type_code)

    if sub_type is None:
        return main_type

    return f"{main_type} - {sub_type}"