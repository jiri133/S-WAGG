# Setup complet pentru Alina (laptop cu Windows, pe care e instalat doar Claude)

Urmează pașii în ordine. Fiecare comandă se rulează în **PowerShell** (Start → scrie „PowerShell” → Enter). Comenzile se copiază pe rând.

Durează ~20 de minute, cea mai mare parte e descărcare.

---

## 1. Acceptă invitația pe GitHub

1. Dacă nu ai cont, fă-ți unul pe https://github.com și spune-i colegului numele de utilizator.
2. El te adaugă în repo (Settings → Collaborators). Primești un email „invited you to collaborate on jiri133/S-WAGG” → **Accept invitation**.

## 2. Instalează uneltele (o singură dată)

```powershell
winget install --id Git.Git -e
```
```powershell
winget install --id OpenJS.NodeJS.LTS -e
```
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Închide PowerShell și deschide-l din nou**, ca să fie găsite comenzile noi. Apoi verifică:

```powershell
git --version; node -v; npm -v; uv --version
```

Trebuie să vezi patru versiuni, cu Node **≥ 22**. Python nu trebuie instalat separat: `uv` îl descarcă singur.

## 3. Spune-i lui git cine ești

```powershell
git config --global user.name "Alina <Nume>"
```
```powershell
git config --global user.email "emailul-tau-de-pe-github@exemplu.com"
```

## 4. Clonează repo-ul

```powershell
mkdir $HOME\Hackathons -Force; cd $HOME\Hackathons
```
```powershell
git clone https://github.com/jiri133/S-WAGG.git
```
```powershell
cd S-WAGG
```

La prima comandă `git` care cere acces, se deschide o fereastră de login GitHub. Te loghezi acolo.

## 5. Instalează dependențele proiectului

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Instalează pachetele FastAPI (cu `uv`) și pe cele React (cu `npm`) și creează fișierele `.env`. La final apare „Setup done”.

## 6. Pornește aplicația o dată, ca test

```powershell
powershell -ExecutionPolicy Bypass -File .\dev.ps1
```

- Backend-ul FastAPI pornește într-o fereastră nouă, pe http://localhost:8000/api/docs
- Frontend-ul React rulează în fereastra curentă, pe http://localhost:5173

Dacă ambele pagini se deschid, setup-ul e gata. Oprești cu `Ctrl+C` în ambele ferestre.

## 7. Deschide proiectul în Claude

1. Deschide aplicația **Claude** → tab-ul **Code**.
2. Alege folderul `C:\Users\<tu>\Hackathons\S-WAGG`.
3. Când te întreabă dacă ai încredere în folder → **Trust**.
4. Când te întreabă de serverul MCP **playwright** (din `.mcp.json`) → **Allow**. Agenții îl folosesc ca să testeze aplicația în browser.

Claude citește automat `CLAUDE.md` și `AGENTS.md`, unde scrie că se lucrează **doar cu FastAPI și React**. Skill-urile proiectului (`wayfinder`, `grilling`, `domain-modeling`, `research`, `prototype`) sunt în `.claude/skills/` și vin odată cu repo-ul.

## 8. Instalează pluginul ECC (agenți de review și teste)

În chat-ul Claude, în folderul proiectului, scrie pe rând:

```
/plugin marketplace add https://github.com/affaan-m/ECC.git
```
```
/plugin install ecc@ecc
```

Dacă aplicația nu acceptă `/plugin`, folosește meniul de plugin-uri din setările aplicației: adaugi marketplace-ul cu URL-ul de mai sus și instalezi `ecc`. După instalare, repornește sesiunea.

## 9. Verifică faptul că agentul are tot

Scrie în chat:

```
Ce skill-uri și agenți ecc ai disponibili în acest repo, și ce reguli de stack scrie în AGENTS.md?
```

Răspunsul trebuie să conțină: skill-urile `wayfinder`, `grilling`, `domain-modeling`, `research` și `prototype`; agenți `ecc:` (de exemplu `ecc:fastapi-reviewer`, `ecc:react-reviewer`, `ecc:e2e-runner`); regula „doar FastAPI + React” și limita de 30 KB pe fișier. Dacă lipsește ceva, reia pasul 7 sau 8.

---

## Cum lucrezi zilnic

### Ia un tichet

Taskurile sunt în `.scratch/solartriage/`: harta e `map.md`, tichetele sunt în `issues/`. Ale tale au `Owner: Alina`. Primele sunt: **04** (setup, adică pașii de mai sus), **05** (contractele, împreună cu colegul, până la H2), apoi **16** (simulator), **18** (stare + SSE) și **19** (harta în React).

1. Fă un branch pentru tichet:
   ```powershell
   git switch main; git pull; git switch -c feat/alina-16-simulator
   ```
2. În Claude, scrie:
   ```
   /wayfinder .scratch/solartriage/map.md — ia următorul tichet deblocat cu Owner: Alina
   ```
   Agentul marchează tichetul `Status: claimed`, îl implementează după `docs/DESIGN_SPEC.md` și respectă `AGENTS.md`.
3. La final cere-i:
   ```
   Rulează testele și un review cu ecc:fastapi-reviewer (sau ecc:react-reviewer pentru frontend), apoi marchează tichetul resolved.
   ```
4. Verifică și tu că trec testele:
   ```powershell
   cd backend; uv run pytest -q; cd ..\frontend; npm run build; cd ..
   ```
5. Trimite lucrul pe GitHub:
   ```powershell
   git add -A; git commit -m "feat: simulator (tichet 16)"; git push -u origin HEAD
   ```
   Apoi deschide un Pull Request pe GitHub spre `main`. Colegul îl revizuiește și face merge.

### Mai mulți agenți în paralel

În aplicația Claude poți porni mai multe sesiuni, fiecare pe **un tichet deblocat diferit**. Bifează să lucreze **într-un worktree separat**, ca să nu-și strice fișierele unul altuia. Două sesiuni nu se ating niciodată de aceleași fișiere.

### Sincronizare cu colegul

- `git pull` pe `main` la fiecare punct de control (H2, H5, H8, H12, H17, H20).
- Schemele din `backend/app/schemas/` se schimbă doar dacă vă înțelegeți amândoi. După o schimbare, regenerezi tipurile React:
  ```powershell
  cd frontend; npm run gen:types
  ```

---

## Probleme frecvente

| Problemă | Rezolvare |
|---|---|
| `node`, `uv` sau `git` „is not recognized” | Închide și redeschide PowerShell, sau repornește laptopul |
| „running scripts is disabled” | Rulează scripturile cu `powershell -ExecutionPolicy Bypass -File .\setup.ps1` |
| Portul 8000 sau 5173 e ocupat | Închide celelalte ferestre `dev.ps1`, sau repornește |
| Serverul MCP `playwright` nu se conectează în Claude | Node lipsește sau e sub 22: pasul 2, apoi repornești aplicația Claude |
| `uv sync` cere altă versiune de Python | `uv` o descarcă singur. Dacă nu, `uv python install` în `backend/` |
| Agentul propune Flask, Django, Next.js, Vue etc. | Răspunde-i: „Nu. Doar FastAPI și React, vezi AGENTS.md.” |
