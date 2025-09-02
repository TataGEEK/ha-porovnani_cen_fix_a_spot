# Porovnání cen fix a spot

Vzdělávací custom integrace pro Home Assistant, která vytváří senzor **HDO Tarif**
na základě stavu přepínače (např. `switch.shellyplus1pm_308398098f40`).

- Pokud je zdrojový přepínač **ON**, senzor ukazuje `nízký`.
- Pokud je **OFF**, senzor ukazuje `vysoký`.
- Atributy: `source_entity_id`, `source_state`, `is_low_tariff` (bool).

> Pozn.: Doména integrace je ASCII (`porovnani_cen_fix_a_spot`), protože Python/HA domény nesmí obsahovat diakritiku.

## Instalace (rychlý start)
1. Zkopíruj složku `custom_components/porovnani_cen_fix_a_spot` do tvého HA config adresáře.
2. Restartuj Home Assistant.
3. V **Nastavení → Zařízení a služby → Přidat integraci** vyhledej `Porovnání cen fix a spot`.
4. Zadej entity_id zdrojového přepínače (default: `switch.shellyplus1pm_308398098f40`).

## Instalace přes HACS (Custom repository)
1. Vytvoř GitHub repo s obsahem tohoto balíčku.
2. V HA otevři **HACS → ⋮ → Custom repositories** a přidej URL tvého repa, typ **Integration**.
3. Nainstaluj, restartuj HA a přidej integraci přes UI.

## Co dál
- Na tento senzor navážou výpočty ceny (fix vs. spot).
- Můžeš přidat další entity (senzory pro ceny, statistiky, atd.).
