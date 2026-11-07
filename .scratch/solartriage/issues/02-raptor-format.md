# Formatul exact al dataset-ului InfraredSolarModules

Type: research
Status: resolved
Owner: agent (AFK)
Țintă: H0
Blocked by: —

## Question

De pe GitHub-ul oficial Raptor Maps (`RaptorMaps/InfraredSolarModules`): URL-ul de descărcare, structura arhivei, fișierul de etichete (nume, format), numele exacte ale celor 12 clase, numărul de imagini pe clasă, dimensiunea și formatul imaginilor, licența.

**Gata când:** există o notă cu tabelul de clase, sursele și un exemplu de cum citești o etichetă.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

## Answer

- **Descărcare:** `https://raw.githubusercontent.com/RaptorMaps/InfraredSolarModules/master/2020-02-14_InfraredSolarModules.zip`. Are 15,5 MB, e un fișier normal (nu Git LFS) și se descarcă dintr-o singură comandă. SHA-256: `b82c706bc719b045ac4f8930570d81767a8a170d0998ca3e09283b585db05b5e`, de verificat în script.
- **Structura arhivei:** `InfraredSolarModules/module_metadata.json` și `InfraredSolarModules/images/0.jpg … 19999.jpg`. Se ignoră `__MACOSX/` și `.DS_Store`. Imaginile sunt JPEG gri pe 8 biți, **24 lățime × 40 înălțime**. Pixelii sunt nivele de gri, nu temperaturi.
- **Etichete:** `meta["0"] = {"image_filepath": "images/0.jpg", "anomaly_class": "Offline-Module"}`.
- **Număr de imagini pe clasa noastră (din arhivă, nu din paper):** ok 10.000 · shadow_vegetation 2.695 · hot_cell 2.126 · diode_substring 1.674 · multi_hot 1.534 · other 940 · module_offline 827 · soiling 204. Total 20.000. Tabelul din paper adună 20.006 și e greșit la 5 clase.
- **Duplicate:** există 22 de perechi de imagini identice. Din 16 perechi cu aceeași etichetă se păstrează o copie. Cele **6 perechi cu etichete conflictuale** se elimină complet: 1124/7387, 161/4518, 3915/7027, 450/7484, 483/6888, 543/5171. Aproape-duplicatele n-au fost verificate și rămân pentru hash-ul perceptual din tichetul 06.
- **Licență:** MIT (Raptor Maps, 2020). CSV-urile cu ID-uri sunt ok în repo. Creditul pentru repo și paper se pune în README.

Detalii și surse: branch-ul `research/raptor-format` (commit da6360d), fișierul `.scratch/solartriage/research/02-raptor-format.md`.