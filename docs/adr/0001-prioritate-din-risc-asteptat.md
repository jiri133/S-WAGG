# Prioritatea vine din probabilitățile modelului, iar agentul emite ordinele singur

Status: accepted (2026-11-07, decizia omului: „ML și pentru urgență/scor”)

Până acum scorul era `pondere(urgența clasei argmax) × pierdere_kWh/zi`, iar un finding **nesigur** nu primea ordin de lucru până nu îl confirma inginerul. Asta arunca informația din probabilitățile calibrate (un modul 60% ok / 40% diodă conta ca ok sau ca diodă, nu la mijloc) și bloca agentul pe review. Am decis ca **scorul să fie riscul așteptat**, `Σ_c p(c) × pondere(urgența de bază a lui c) × pierdere_kWh/zi(c)` (ok contribuie 0), iar **urgența să vină din clasa cu cea mai mare contribuție**. **Toate finding-urile primesc ordin de lucru automat**; cele nesigure primesc un ordin „verifică și repară” (`ticket_status = verify_and_repair`) cu încrederea modelului în motivul din plan. Review-ul rămâne o suprascriere: respins scoate ordinul, confirmat îl face `pending`, neconcludent → reinspecție. **Regula de siguranță ΔT ≥ 20 K rămâne plasă de siguranță** și dă critical + alertă indiferent de clasa prezisă (chiar și pe ok), cu ordinul la electricieni.

## Considered Options

- **Scor pe clasa argmax, nesigur blocat până la review** (DESIGN_SPEC Q10, varianta veche): simplu, dar agentul nu acționează singur și ignoră incertitudinea.
- **Siguranța doar pe clasele de risc** (hot_cell / multi_hot / diode_substring): respins, pentru că un ΔT ≥ 20 K e risc de incendiu chiar dacă modelul greșește clasa.

## Consequences

- Echipa, piesa și durata ordinului urmează clasa prezisă de model; doar urgența urmează contribuția maximă. Un modul 93% `other` cu 1% `module_offline` poate primi urgență high (pierderea offline e de 20 de ori mai mare). E efectul dorit al riscului așteptat, dar merită urmărit pe probabilitățile reale.
- Scorul unui finding critic poate fi mic (riscul așteptat nu folosește ponderea critical), așa că lista de priorități pune criticele primele explicit, apoi sortează după scor; planner-ul le pune tot în ziua 1.
- Webhook-ul primește un ordin și pentru fiecare finding nesigur (5 ordine în misiunea mock, nu 4).

## Amendament: lista „de urmărit” (decizia omului: „da mult prea multe probleme … ar trebui mai multe filtrate”)

- Pe 10 misiuni simulate, 334 din 446 de findings erau false: module sănătoase pe care modelul le confundă mai ales cu `module_offline` și `hot_cell`. Un finding la care modelul mai dă `p(ok) ≥ watch.min_p_ok` (0,10, în `decision_rules.yaml`) și care nu e critic **nu primește ordin de lucru** până nu îl confirmă inginerul. Apare în lista „de urmărit” din tab-ul Plan.
- Pragul de 0,10 ține 107 din 112 defecte reale în plan și scoate din plan 254 din 334 de findings false. Criticele (ΔT ≥ 20 K) nu ajung niciodată în listă.
- Confirmarea face ordinul `pending`, respingerea îl lasă fără ordin, ca înainte.
