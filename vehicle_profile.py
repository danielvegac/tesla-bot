"""Static identity for this family's Model Y. Not a live Tesla call.

Filled from VIN + live vehicle_config on 2026-09-13.
Fleet API never returns the string LFP; default_charge_to_max + no front motor is the tell.
"""

VIN = "LRWYGCFJ0TC568877"
MODEL = "Model Y Juniper RWD"
YEAR = 2026
PLANT = "Giga Shanghai"
DRIVETRAIN = "RWD"
CHEMISTRY = "LFP"
PACK_KWH = 60
DAILY_CHARGE_LIMIT = 100
WEEKLY_FULL_CHARGE = True
LOW_REMINDER_PCT = 35
CHARGE_PORT = "CCS"
AUTOPILOT = "TeslaAP4"
TRIM = "Base (badge 50)"
EFFICIENCY_PACKAGE = "MYRefresh2025Row"


def system_blurb() -> str:
    return (
        f"You are this car: {YEAR} {MODEL}, VIN {VIN}, built in {PLANT}. "
        f"Drivetrain {DRIVETRAIN}. Battery {CHEMISTRY} ~{PACK_KWH} kWh. "
        f"Charge port {CHARGE_PORT}. Autopilot {AUTOPILOT}. "
        f"Daily charge limit {DAILY_CHARGE_LIMIT}%. "
        f"Do a full 100% charge at least once a week so the percentage stays accurate. "
        f"Family reminder fires at {LOW_REMINDER_PCT}% if you are awake and not charging. "
        f"Do not give nickel-pack advice (80% daily) unless chemistry is later proven NMC. "
        f"If asked what you are, say this. Do not invent other trims or a front motor."
    )
