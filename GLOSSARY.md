# SolarTriage

Limbajul comun pentru inspecția termică a unui parc fotovoltaic și transformarea ei în mentenanță. Agenții și oamenii folosesc exact acești termeni în cod, UI și discuții.

## Parcul

**Parc**:
Instalația fotovoltaică inspectată: 480 de module grupate în blocuri, rânduri și mese.
_Avoid_: centrală, fermă, site

**Masă**:
Structura care susține 2×6 module; o captură acoperă exact o masă.
_Avoid_: table (în text), rack, panou

**Modul**:
Un singur panou fotovoltaic, identificat ca `B1-R2-T3-M07`; unitatea pe care se fac finding-urile.
_Avoid_: panou, panel (în text)

**Substring**:
Una din cele 3 grupe de celule ale unui modul, protejată de o diodă de bypass.
_Avoid_: secțiune, zonă

**String**:
Șirul de 24 de module (2 mese) conectate în serie.
_Avoid_: lanț, rând

**Invertor**:
Echipamentul la care se leagă string-urile unui rând.
_Avoid_: invertor central, PCS

## Inspecția

**Misiune**:
O inspecție completă: setări, zbor, verificare, analiză, review.
_Avoid_: sesiune, run, simulare

**Trecere**:
Unul din cele două cadre luate pe aceeași masă din poziții puțin diferite.
_Avoid_: pass (în text), overlap

**Cadru**:
O imagine termică a unei mese, cu metadatele ei de captură.
_Avoid_: frame (în text), poză

**Crop**:
Imaginea 24×40 a unui singur modul, decupată dintr-un cadru.
_Avoid_: patch, tăietură

**Neinspectat**:
Starea unui modul fără date valide; nu înseamnă niciodată „sănătos”.
_Avoid_: lipsă, ok, necunoscut

**Reflexie probabilă**:
O anomalie văzută într-o singură trecere, tratată ca glare până confirmă omul.
_Avoid_: glare (ca verdict), fals pozitiv

**ΔT aparent**:
Diferența de temperatură aparentă a unui modul față de mediana mesei lui.
_Avoid_: delta, temperatura defectului

## Decizia

**Finding**:
O anomalie detectată pe un modul, cu clasă, încredere, dovezi și urgență.
_Avoid_: defect (înainte de confirmare), alarmă, observație

**Clasă de defect**:
Una din cele 8 categorii: ok, hot_cell, multi_hot, diode_substring, module_offline, soiling, shadow_vegetation, other.
_Avoid_: tip, label

**Nesigur**:
Un finding a cărui încredere e sub prag: e semnalizat inginerului, nu blocat; primește ordin „verifică și repară”.
_Avoid_: low confidence, incert

**Urgență**:
Cât de repede trebuie tratat un finding: critical, high, medium, low.
_Avoid_: prioritate, severitate

**Alertă**:
Notificarea imediată pentru un finding critical, cu risc de incendiu.
_Avoid_: warning, notificare

**Review**:
Decizia inginerului asupra unui finding: confirmat, respins sau neconcludent.
_Avoid_: validare, aprobare

**Ordin de lucru**:
Sarcina de mentenanță emisă automat pentru orice finding nerespins, cu echipă, piesă, durată și dovadă.
_Avoid_: tichet, work order (în text), task

**Echipă**:
Grupul care execută ordinele de lucru: electricieni sau curățenie.
_Avoid_: crew (în text), tehnicieni

**Plan**:
Repartizarea ordinelor de lucru pe zile și echipe, fiecare cu motivul ei.
_Avoid_: program, schedule

**Adevăr de teren**:
Defectele plantate de simulator, cunoscute doar în modul demo.
_Avoid_: ground truth (în text), etichete reale
