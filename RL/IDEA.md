# Reinforcement Learning – Battery Energy Optimization
## Plan de lucru – Roberto & Mihai

## 1. Obiectivul componentei

Dezvoltarea unui agent bazat pe Reinforcement Learning care învață să optimizeze încărcarea și descărcarea bateriilor conectate la un parc fotovoltaic.

Agentul trebuie să decidă în mod autonom când este mai avantajos să:
- Încarce bateria folosind energia disponibilă.
- Descarce bateria pentru a acoperi cererea sau pentru a valorifica energia stocată.
- Păstreze energia pentru intervale viitoare mai avantajoase.

Obiectivul principal este maximizarea valorii energiei utilizate și reducerea costurilor și a pierderilor, respectând constrângerile tehnice ale bateriei.

## 2. Definirea problemei

Vom considera un parc fotovoltaic conectat la:
- O sursă de producție solară.
- Un consumator sau o cerere de energie.
- O baterie pentru stocarea surplusului.
- Rețeaua electrică, din care putem cumpăra sau în care putem livra energie.

Agentul va analiza situația energetică la intervale regulate și va lua decizii privind utilizarea bateriei.

### Obiectivele agentului

1. Să valorifice cât mai multă energie regenerabilă.
2. Să reducă energia cumpărată din rețea atunci când este avantajos.
3. Să maximizeze valoarea energiei livrate în rețea.
4. Să evite încărcarea și descărcarea inutilă.
5. Să respecte limitele tehnice ale bateriei.

## 3. Modelarea problemei RL

### A. Environment – Mediul simulat

Vom construi un simulator care reproduce funcționarea unui parc fotovoltaic și a unei baterii.

Parametri inițiali propuși:
- Capacitate baterie: 10 MWh.
- Putere maximă de încărcare: 2 MW.
- Putere maximă de descărcare: 2 MW.
- SoC minim: 10%.
- SoC maxim: 90%.
- Eficiență încărcare: 95%.
- Eficiență descărcare: 95%.
- Durata unui interval: 15 minute.
- Durata unui episod: 24 de ore.

Vom folosi inițial date sintetice pentru producție, consum și prețuri, urmând să le înlocuim sau completăm cu date reale.

### B. State – Informațiile observate de agent

Agentul va primi la fiecare interval:

| Variabilă | Descriere |
|---|---|
| Battery SoC | Nivelul actual de încărcare |
| Solar Production | Producția fotovoltaică actuală |
| Energy Demand | Consumul actual |
| Energy Price | Prețul actual al energiei |
| Solar Forecast | Producția estimată în următoarele ore |
| Demand Forecast | Consumul estimat în următoarele ore |
| Time of Day | Ora și intervalul zilei |

Scopul este ca agentul să ia decizii nu doar pe baza situației actuale, ci și anticipând evoluția următoarelor intervale.

### C. Actions – Acțiunile posibile

Pentru prima versiune vom folosi un spațiu discret de acțiuni:

- **CHARGE:** încarcă bateria.
- **DISCHARGE:** descarcă bateria.
- **HOLD:** păstrează nivelul actual de energie.

Într-o versiune ulterioară putem introduce acțiuni continue, prin care agentul decide și puterea de încărcare sau descărcare.

### D. Reward Function – Funcția de recompensă

Agentul trebuie să învețe să maximizeze o recompensă cumulativă.

Vom urmări:
- Reducerea costurilor de achiziție a energiei.
- Valorificarea surplusului de producție solară.
- Creșterea valorii energiei livrate în rețea.
- Reducerea energiei regenerabile irosite.
- Evitarea ciclurilor inutile ale bateriei.

Vom penaliza:
- Încălcarea limitelor bateriei.
- Încărcarea sau descărcarea inutilă.
- Degradarea excesivă a bateriei.
- Energia care nu poate fi valorificată.

Funcția de recompensă va trebui să reflecte obiectivul economic real, fără să recompenseze de două ori aceeași cantitate de energie.

## 4. Algoritmul RL

Vom începe cu PPO (Proximal Policy Optimization), folosind Stable-Baselines3.

Motive:
- Este potrivit pentru probleme de control secvențial.
- Poate fi utilizat cu acțiuni discrete.
- Permite extinderea ulterioară către acțiuni continue.
- Are o implementare disponibilă și documentată.

Vom lua în calcul și DQN pentru comparație, dacă timpul permite.

## 5. Strategii de referință (Baseline)

Pentru a demonstra că RL aduce valoare, vom compara agentul cu două strategii:

### Strategy 1 – Fără optimizare

Bateria nu este utilizată strategic sau urmează o politică foarte simplă.

### Strategy 2 – Rule-Based

Folosim reguli prestabilite:
- Dacă există surplus solar și bateria nu este plină, încarcă.
- Dacă există deficit și bateria are energie, descarcă.
- Altfel, păstrează energia.

### Strategy 3 – RL Agent

Agentul învață să ia decizii în funcție de:
- Situația energetică actuală.
- Prognoza producției și consumului.
- Prețurile energiei.
- Nivelul bateriei.
- Oportunitățile viitoare.

## 6. Evaluarea performanței

Vom compara strategiile folosind următoarele metrici:

| Metrică | Ce măsoară |
|---|---|
| Total Energy Cost | Costul total al energiei |
| Energy Revenue | Venitul din energia livrată |
| Renewable Energy Utilization | Procentul de energie regenerabilă valorificat |
| Wasted Energy | Energia care nu a putut fi utilizată sau stocată |
| Battery Degradation | Degradarea estimată prin utilizare |
| Constraint Violations | Încălcarea limitelor tehnice |

Evaluarea se va realiza pe zile și scenarii diferite, inclusiv date care nu au fost utilizate în antrenare.