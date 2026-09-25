"""Status codes from Status Description.xlsx and the default calculation mapping."""

# code: (meaning, event status)
STATUS_CODES = {
    'RS': ('Reserve Shutdown', 'Reserve Shutdown order by Dispatcher'),
    'NC': ('Non Curtailing', 'Non Curtailing'),
    'PO': ('Planned Outage', 'Planned Outage'),
    'MO': ('Maintenance Outage', 'Maintenance Outage'),
    'PE': ('Planned Outage Extension', 'Planned Outage Extension'),
    'ME': ('Maintenance Outage Extension', 'Maintenance Outage Extension'),
    'FO': ('Forced Outage', 'Forced Outage'),
    'FO.OS': ('Forced Outage.Outage Slip', 'Outage Slip'),
    'FO.SYS': ('Forced Outage.System', 'Forced Outage due to Grid (System)'),
    'FO.ENV': ('Forced Outage.Environment', 'Forced Outage due to Environment'),
    'FO.FUEL': ('Forced Outage.Fuel', 'Forced Outage due to Lack of Fuel'),
    'FO.FM': ('Forced Outage.Force Majeure', 'Forced Outage due to Force Majeure'),
    'FO.OTH': ('Forced Outage.Others', 'Forced Outage due to Others External'),
    'SF': ('Startup Failure', 'Startup Failure'),
    'PD': ('Planned Derated', 'Planned Derated'),
    'MD': ('Maintenance Derated', 'Maintenance Derated'),
    'PDE': ('Planned Derated Extension', 'Planned Derated Extension'),
    'MDE': ('Maintenance Derated Extension', 'Maintenance Derated Extension'),
    'FD': ('Forced Derated', 'Forced Derated'),
    'FD.DS': ('Forced Derated.Derating Slip', 'Derating Slip'),
    'FD.SYS': ('Forced Derated.System', 'Forced Derated due to Grid (System)'),
    'FD.ENV': ('Forced Derated.Environment', 'Forced Derated due to Environment'),
    'FD.FUEL': ('Forced Derated.Fuel', 'Forced Derated due to Lack of Fuel'),
    'FD.MP': ('Forced Derated.Major Problem', 'Forced Derated due to Major Problem'),
    'FD.OTH': ('Forced Derated.Others', 'Forced Derated due to Others External'),
    'FDRS': ('Forced Derated Reserve Shutdown', 'Forced Derated Reserve Shutdown'),
    'SED': ('Seasonal Derated', 'Seasonal Derated'),
    'SUD': ('Start Up Derating', 'Start Up Derating'),
    'SHD': ('Shutdown Derating', 'Shutdown Derating'),
}

# Default category and inclusion (same defaults as Failure_Data_highlighted.xlsx)
DEFAULT_INCLUDED = {"FO": "FO", "FO.OS": "OS", "MO": "MO", "PE": "SE", "ME": "SE",
                    "FD": "FD", "MD": "MD", "PD": "PD"}
CATEGORIES = ["FO", "OS", "MO", "SE", "FD", "MD", "PD"]


def default_category(code: str) -> str:
    if code in DEFAULT_INCLUDED:
        return DEFAULT_INCLUDED[code]
    if code.startswith("FO."):
        return "FO"
    if code.startswith("FD.") or code == "FDRS":
        return "FD"
    return {"PDE": "PD", "MDE": "MD"}.get(code, "")
