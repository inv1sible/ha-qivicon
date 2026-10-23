"""Constants for the QIVICON integration."""

DOMAIN = "qivicon"

PLATFORMS = [
    "binary_sensor",
    "climate",
    "datetime",
    "light",
    "number",
    "select",
    "sensor",
    "switch",
    "text",
]

NULL_STATES = {None, "NULL", "UNDEF", "UNINITIALIZED"}
