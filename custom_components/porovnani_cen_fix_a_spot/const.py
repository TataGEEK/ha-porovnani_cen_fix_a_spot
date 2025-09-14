# custom_components/porovnani_cen_fix_a_spot/const.py
DOMAIN = "porovnani_cen_fix_a_spot"
DEFAULT_SOURCE_ENTITY_ID = "switch.shellyplus1pm_308398098f40"

ATTR_SOURCE_ENTITY_ID = "source_entity_id"
ATTR_SOURCE_STATE = "source_state"
ATTR_IS_LOW_TARIFF = "is_low_tariff"

# ==== klíče pro fixní obchodní cenu ====
CONF_FIX_OBCHODNI_CENA_VT = "fix_obchodni_cena_vt"
CONF_FIX_OBCHODNI_CENA_NT = "fix_obchodni_cena_nt"

DEFAULT_FIX_OBCHODNI_CENA_VT = 3.9809
DEFAULT_FIX_OBCHODNI_CENA_NT = 3.9809

# ==== FIX paušály [Kč/měs] ====
CONF_FIX_STALA_PLATBA = "fix_stala_platba"
CONF_FIX_ZA_JISTIC = "fix_za_jistic"
CONF_FIX_PROVOZ_INFRASTRUKTURY = "fix_provoz_infrastruktury"

DEFAULT_FIX_STALA_PLATBA = 523.5
DEFAULT_FIX_ZA_JISTIC = 227.48
DEFAULT_FIX_PROVOZ_INFRASTRUKTURY = 11.18

# ==== SPOT ====
CONF_SPOT_MARZE = "spot_marze"
CONF_SPOT_STALA_PLATBA = "spot_stala_platba"
CONF_SPOT_ZA_JISTIC = "spot_za_jistic"
CONF_SPOT_PROVOZ_INFRASTRUKTURY = "spot_provoz_infrastruktury"

DEFAULT_SPOT_MARZE = 0.48279
DEFAULT_SPOT_STALA_PLATBA = 154.88
DEFAULT_SPOT_ZA_JISTIC = 272.25
DEFAULT_SPOT_PROVOZ_INFRASTRUKTURY = 13.12

# ==== POZE (Kč/kWh) ====
CONF_POZE = "poze"
DEFAULT_POZE = 0.59895

# ==== DISTRIBUCE (Kč/kWh) ====
CONF_DISTRIBUCE_VT = "distribuce_vt"
CONF_DISTRIBUCE_NT = "distribuce_nt"
CONF_DISTRIBUCE_DAN = "distribuce_dan"
CONF_DISTRIBUCE_SLUZBY = "distribuce_sluzby"

DEFAULT_DISTRIBUCE_VT = 2.7432
DEFAULT_DISTRIBUCE_NT = 0.24926
DEFAULT_DISTRIBUCE_DAN = 0.03424
DEFAULT_DISTRIBUCE_SLUZBY = 0.20681

# ==== SPOTŘEBA – zdrojové entity ====
CONF_CONS_TOTAL_ENERGY = "cons_total_energy_entity_id"   # preferovaný jediný senzor energie (kWh)
CONF_CONS_PHASE1 = "cons_phase1_entity_id"               # fáze 1 (energy nebo power)
CONF_CONS_PHASE2 = "cons_phase2_entity_id"               # fáze 2 (volitelné)
CONF_CONS_PHASE3 = "cons_phase3_entity_id"               # fáze 3 (volitelné)

# prázdný default = nezadáno
DEFAULT_CONS_TOTAL_ENERGY = ""
DEFAULT_CONS_PHASE1 = ""
DEFAULT_CONS_PHASE2 = ""
DEFAULT_CONS_PHASE3 = ""

# Senzor hodinové spotové ceny (mění se každou hodinu)
CONF_SPOT_PRICE_SENSOR = "spot_price_sensor"
DEFAULT_SPOT_PRICE_SENSOR = "sensor.current_spot_electricity_buy_price"

# název profilu (volitelné)
CONF_PROFILE_NAME = "profile_name"
DEFAULT_PROFILE_NAME = "Porovnání cen"
