# Vergelijk Box 3 en AOW met je eigen berekening

[Open de browserdemo](https://simonvanlierde.com/vuurtoren/) en begin met het
fictieve voorbeeldhuishouden. De berekening draait in je browser. Je hoeft je eigen
gegevens niet te delen om een verschil te melden.

We zoeken onafhankelijke vergelijkingen van minstens drie gebruikers. Een werkende
demo of geslaagde test is nog geen bevestiging door een gebruiker. Vergelijk Box 3
en de AOW-leeftijd apart; overeenstemming in één geval bewijst niet dat het hele
model klopt.

## Maak dezelfde vergelijking

1. Noteer de versie of commit van Vuurtoren en de datum van je vergelijking.
   Bekijk de modelbeperkingen in Plan en de bronstatus in Belastingcijfers.
2. Gebruik voor Box 3 hetzelfde belastingjaar, dezelfde peildatum, hetzelfde regime
   en dezelfde partnerverdeling. Houd banktegoeden, overige bezittingen en schulden
   uit elkaar. Noteer of je forfaitair rendement of tegenbewijs vergelijkt, en of
   het resultaat voor één persoon of het hele huishouden geldt.
3. Gebruik een gedateerde officiële bron, bijvoorbeeld de
   [berekening voor de voorlopige aanslag 2026 van de Belastingdienst](https://www.belastingdienst.nl/wps/wcm/connect/nl/box-3/content/berekening-box-3-inkomen-2026).
   Een voorlopige aanslag en een berekening met werkelijk rendement beantwoorden
   verschillende vragen. Noteer ook hoe de bron afrondt; vergelijk tussenstappen
   voordat je een afwijkend eindbedrag als fout aanmerkt.
4. Vergelijk voor AOW de leeftijd en ingangsdatum met het
   [overzicht van de SVB](https://www.svb.nl/nl/aow/aow-leeftijd/uw-aow-leeftijd).
   Maak onderscheid tussen vastgestelde en verwachte leeftijden. Vuurtoren gebruikt
   na zijn schema tot en met 2031 een eigen groeiaanname; die kan afwijken van de
   verwachting van de SVB. Deze controle bevestigt geen persoonlijke AOW-uitkering
   of verzekeringsopbouw.
5. Houd bij een meerjarenprojectie ook startdatum, rendement, inflatie en eventuele
   handmatige aanpassingen gelijk. Een belastingaanpassing geldt alleen voor het
   geselecteerde jaar. Een toekomstscenario is geen vastgesteld belastingstelsel:
   het model bevat nog het eerdere voorstel voor werkelijk rendement vanaf 2028.
   Nieuwere beleidswijzigingen zijn daarmee niet automatisch verwerkt.

De officiële pagina's hierboven zijn geraadpleegd op 7 november 2026. De SVB-pagina
vermeldt 1 oktober 2026 als laatste controle. Controleer bij je eigen vergelijking
opnieuw welke bronversie en status gelden.

## Meld een overeenkomst of verschil zonder privégegevens

[Open een issue](https://github.com/simonvanlierde/vuurtoren/issues/new) met een
nieuwe fictieve casus. Bereken de referentie ook opnieuw voor die fictieve invoer;
alleen je eigen bedragen afronden is geen bruikbare anonimisering.

Deel geen werkelijke geboortedata, posities, rekeningnummers, ISINs, aangiften,
screenshots met persoonsgegevens of huishoudexports. Je eigen vergelijking kan
privé blijven. Voor een reproduceerbare melding volstaat dit:

```text
Onderwerp: Box 3 of AOW
Vuurtoren-versie/commit en datum:
Officiële bron, datum bekeken, vastgesteld/voorlopig/verwacht:
Fictieve invoer en gebruikte aannames:
Verwachte uitkomst en berekening:
Uitkomst van Vuurtoren, inclusief eenheid/periode/persoon of huishouden:
Overeenkomst of verschil, met afronding toegelicht:
```

Gebruik voor een fictieve AOW-casus een verzonnen geboortedatum. Voor Box 3 staan
bestaande voorbeelden in [tests/golden/box3](../tests/golden/box3), met de velden
`source`, `retrieved`, `tax_year`, `fiscal_partners`, `share`, `inputs` en
`published`. [Het spaargeldvoorbeeld](../tests/golden/box3/2026-savings-single.yaml)
laat dat formaat zien. De bestandsdatum zegt wanneer die bron is gecontroleerd;
controleer hem opnieuw voordat je het voorbeeld overneemt.

## Van vergelijking naar regressietest

Een maintainer controleert de bron en de fictieve reproductie voordat een melding
als bevestiging telt. Leg iedere geaccepteerde casus vast als test: een Box 3-casus
bij de bestaande [golden tests](../tests/test_box3_golden.py), een AOW-casus in
[tests/test_aow.py](../tests/test_aow.py). Leg ook een verklaard verschil vast als
dat een modelgrens bewaakt. Pas verwachte cijfers niet aan om een test groen te
maken; bespreek een verschil met de bron eerst in het issue.

De vergelijking is afgerond wanneer minstens drie onafhankelijke gebruikers hun
vergelijking hebben bevestigd en iedere geaccepteerde fictieve casus een geslaagde
test heeft. Alleen de gedekte gevallen zijn dan bevestigd.
