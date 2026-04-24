# Log refaktoringu cro-dl (24. dubna 2026 - odpoledne)

## 🎯 Cíl: Service Layer / Fasáda (Bod 3)
Vytvořit jednotné rozhraní pro ovládání knihovny, oddělit logiku od CLI a připravit půdu pro budoucí GUI.

## 🚧 Provedené změny

### 1. Implementace `CroDL` Fasády
*   Vytvořen nový modul `crodl/facade.py` s třídou `CroDL`.
*   Fasáda nyní centrálně řeší:
    *   Validaci domén (`is_domain_supported`).
    *   Rozpoznávání typu obsahu (`get_content`).
    *   Orchestraci stahování s podporou externího progress baru.

### 2. Refaktoring `main.py`
*   CLI je nyní "tenkým klientem". Veškerá složitá logika (if-else pro Show/Series) byla přesunuta do fasády.
*   Zlepšena čitelnost a údržba kódu.

### 3. Sjednocení exportů
*   Třída `CroDL` je nyní dostupná přímo z balíčku: `from crodl import CroDL`.

## 🏆 Výsledek a ověření
*   **Verifikace:** Funkčnost CLI ověřena na reálných příkladech.
*   **Stabilita:** Opraveny testy (`test_crodl.py`), které závisely na staré struktuře. Všech 107 testů je zelených.

## ⚡ Co nás čeká příště
1.  **Persistence:** Implementace `SQLModel` pro ukládání historie a metadat (Bod 4).

---
*Hotovo. Architektura je teď krásně čistá a připravená na další rozšiřování!* 🏛️


