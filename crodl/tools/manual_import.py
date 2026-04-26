import asyncio
import os
import hashlib
from pathlib import Path
from datetime import datetime

from crodl.persistence.repository import LibraryRepository
from crodl.persistence.models import Episode, Show, Series, Station
from crodl.persistence.database import init_db
from crodl.settings import DOWNLOAD_PATH

# Knowledge base for manual/AI metadata injection
METADATA_KNOWLEDGE = {
    "cervotoci": {
        "title": "Alexandr Kliment: Červotoči",
        "desc": "Rozhlasová hra z roku 1990 o manželské krizi v kulisách pozdní normalizace. Hrají: Jiří Adamíra, Josef Kemr, Boris Rösner.",
        "show": "Hra na sobotu"
    },
    "vrazdy-v-ulici-morgue": {
        "title": "Edgar Allan Poe: Vraždy v ulici Morgue",
        "desc": "Klasická detektivka, ve které C. Auguste Dupin řeší záhadu brutální vraždy v uzavřeném pokoji.",
        "show": "Hry a povidky"
    },
    "doktor-skrtikocka": {
        "title": "Jean Paul: Doktor Škrtikočka jede do lázní",
        "desc": "Humoristické vyprávění o výstředním lékaři a jeho dobrodružstvích na cestách.",
        "series": "Radiokniha"
    },
    "bily-samum": {
        "title": "Karel Klostermann: Bílý samum",
        "desc": "Baladický příběh ze Šumavy o síle přírody a lidském osudu v kruté zimě.",
        "show": "Čtení na pokračování"
    },
    "nezvestna-slechticna": {
        "title": "A. C. Doyle: Nezvěstná šlechtična",
        "desc": "Další z případů Sherlocka Holmese a doktora Watsona.",
        "show": "Hra na sobotu"
    },
    "studie-v-sarlatove": {
        "title": "A. C. Doyle: Studie v šarlatové",
        "desc": "První román o Sherlocku Holmesovi. Hrají Oldřich Kaiser a Jiří Lábus.",
        "show": "Hra na sobotu"
    },
    "odporuj-zlu": {
        "title": "Miloš Doležal: Odporuj zlu, aby se necítilo pánem světa!",
        "desc": "Příběh o životě a tragické smrti malíře a spisovatele Josefa Čapka.",
        "series": "Radiokniha"
    }
}

async def manual_import():
    await init_db()
    repo = LibraryRepository()
    
    print("Starting AI-assisted manual import...")
    
    # Iterate through all audio files
    for root, _, files in os.walk(DOWNLOAD_PATH):
        if ".chunks" in root: continue
        for file in files:
            if not file.lower().endswith((".mp3", ".aac", ".m4a")): continue
            
            path = Path(root) / file
            filename_slug = file.lower().replace(" ", "-")
            
            # Look for a match in knowledge base
            match = None
            for key, data in METADATA_KNOWLEDGE.items():
                if key in filename_slug:
                    match = data
                    break
            
            if match:
                # Generate a local ID based on path if UUID unknown
                local_id = hashlib.sha256(str(path).encode()).hexdigest()[:16]
                
                show = None
                if "show" in match:
                    show = Show(id=hashlib.md5(match["show"].encode()).hexdigest()[:8], title=match["show"])
                
                series = None
                if "series" in match:
                    series = Series(id=hashlib.md5(match["series"].encode()).hexdigest()[:8], title=match["series"])
                
                episode = Episode(
                    id=local_id,
                    title=file.split(".")[0], # Use filename as title if not specified
                    short_title=match["title"],
                    description=match["desc"],
                    local_path=str(path),
                    is_manual=True,
                    audio_format=path.suffix.lstrip("."),
                    show_id=show.id if show else None,
                    series_id=series.id if series else None
                )
                
                await repo.save_episode(episode, show_data=show, series_data=series)
                print(f"✓ Imported: {file}")
            else:
                # Basic import for unknown files
                local_id = hashlib.sha256(str(path).encode()).hexdigest()[:16]
                episode = Episode(
                    id=local_id,
                    title=file.split(".")[0],
                    local_path=str(path),
                    is_manual=True,
                    audio_format=path.suffix.lstrip(".")
                )
                await repo.save_episode(episode)
                print(f"? Generic import: {file}")

if __name__ == "__main__":
    asyncio.run(manual_import())
