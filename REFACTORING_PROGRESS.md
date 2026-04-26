# Log refaktoringu cro-dl (Duben 2026)

## 🏁 Celkový přehled
Projekt prošel transformací z procedurálního/synchronního přístupu na moderní asynchronní architekturu založenou na principech Clean Code a OOP. Je plně připraven pro webovou nadstavbu a lokální správu audio knihovny.

---

## 📅 23. dubna 2026: Abstrakce stahovačů (Bod 1)
**Cíl:** Sjednotit logiku stahování a převést ji do asynchronního režimu.
(Detaily v předchozích verzích logu...)

---

## 📅 24. dubna 2026: Paralelní stahování a Fasáda (Bod 2 & 3)
**Cíl:** Zrychlit stahování a vytvořit jednotné rozhraní pro ovládání knihovny.
(Detaily v předchozích verzích logu...)

---

## 📅 25. dubna 2026: Webová knihovna a Persistence (Bod 4 & 5)
**Cíl:** Implementace SQLite databáze a FastAPI rozhraní pro prohlížení archivu.

### Provedené změny:
*   **SQLModel Integration:** Zavedena asynchronní persistence metadat.
*   **Webové rozhraní:** Vytvořen přehled pořadů a detail s přehrávačem.
*   **Robustní Synchronizace:** Implementován nástroj pro import stávajících souborů z disku do DB.
    *   Využívá "slug guessing" pro párování s API.
    *   Podporuje generický import pro soubory, které již v ČRo archivu nejsou.
*   **Unikátní identifikace:** Každý soubor na disku má vlastní ID (hash cesty), což řeší konflikty u vícedílných děl.

---

## 🏆 Aktuální stav
Projekt je stabilní, asynchronní a umí spravovat lokální archiv i pro historicky stažené kousky. 

---

## ⚡ Co nás čeká příště
1.  **Hierarchická knihovna:** Rozdělení webu na úroveň Autor -> Dílo -> Epizoda.
2.  **Editace metadat:** Možnost ručně upravit popisy a názvy přímo přes web.
3.  **Kategorizace:** Menu s žánry (Krimi, Horory, Komedie).

---
*Hotovo. Čas na zasloužený odpočinek!* 🚀😴
