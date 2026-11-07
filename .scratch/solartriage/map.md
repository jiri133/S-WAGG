# Harta SolarTriage

Type: map

## Destination

SolarTriage construit și gata de demo la H24, conform `docs/DESIGN_SPEC.md`: agent cap-coadă în **FastAPI**, UI în **React (Vite)**, model antrenat și evaluat față de 2 baseline-uri, `evaluate.py` reproductibil, repo public cu commit-uri în cele 24 h.

## Notes

- **Execuția e inclusă în hartă** (excepție de la regula Wayfinder „plan, don't do”). Tichetele `task` sunt bucăți de implementare cu proprietar și oră-țintă. Deciziile de design sunt deja luate în `docs/DESIGN_SPEC.md` §16; nu le redeschide fără omul care le-a luat.
- **Echipa:** Tu (ML + decizie + plan) și Alina (simulator + pipeline + stare + UI). Agenții scriu codul, omul verifică și face merge.
- **Regulile obligatorii sunt în `AGENTS.md`:** doar FastAPI + React, nicio bibliotecă în afara listei, niciun fișier sursă peste 30 KB.
- **Skill-uri de folosit:** pentru întrebări deschise, `grilling` + `domain-modeling`; pentru fapte, `research`; pentru „cum arată/cum se comportă”, `prototype`. Vocabularul e în `GLOSSARY.md`.
- **Agenți ECC utili:** `ecc:fastapi-reviewer`, `ecc:python-reviewer`, `ecc:react-reviewer`, `ecc:typescript-reviewer`, `ecc:mle-reviewer`, `ecc:e2e-runner`, `ecc:build-error-resolver`.
- **Puncte de control:** H2 contracte · H5 date Raptor · H8 cap-coadă pe baseline · H12 model v1 + ordine de lucru · H17 funcții de bază · H20 code freeze · H21–24 README, slide-uri, video, repetiție.
- **Somn, niciodată simultan:** Alina H10–12:30, Tu H13–15:30.
- **La ratare:** H8 ratat cu > 1 h → Grad-CAM devine opțional. H17 ratat → TicketInbox și consistency check-ul devin opționale.
- **Cum iei un tichet:** în Claude, `/wayfinder .scratch/solartriage/map.md`, sau „ia următorul tichet deblocat cu Owner: <numele tău>”. Setează `Status: claimed` înainte de orice lucru.

## Decisions so far

<!-- o linie per tichet închis: [titlu](issues/NN-slug.md): rezumat -->

- [Python 3.15 merge cu PyTorch, ONNX Runtime și numpy?](issues/01-python-compat.md): nu, pentru onnxruntime și PyYAML. Fixăm Python 3.14 prin uv, care îl descarcă singur.
- [Formatul exact al dataset-ului InfraredSolarModules](issues/02-raptor-format.md): zip de 15,5 MB, JSON id → clasă, imagini 24×40 gri; numărătorile reale diferă de paper; 6 perechi de duplicate conflictuale de eliminat; licență MIT.

## Not yet specified

- **Factorul `k` din conversia intensitate → temperatură aparentă:** se poate fixa doar după ce vedem distribuția reală a crop-urilor (tichetele 2 și 6) și pragul de alertă de 20 K pe ea.
- **Conținutul exact al celor 3 scenarii demo** (ce defecte, unde, care injectări): se fixează după ce simulatorul și modelul rulează (tichetele 16 și 10).
- **Narațiunea slide-urilor și cifrele-cheie:** după `eval.json`.

## Out of scope

- Agentul RL pentru baterii de pe branch-ul `feat/rl-agent`: alt proiect, neatins.
- YOLO / detecție de panouri, clasificator RGB și fuziune, PDF, ServiceNow, retrain sau ajustarea pragurilor live, orice stack în afară de FastAPI + React.
