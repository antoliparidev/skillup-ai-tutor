---
corso: "Corso inventato - Moka DevOps"
sezione: "GIORNO 1 - LA MOKA"
pagina: "La moka in container"
tipo: "pagina"
link: "https://esempio.invalid/moka/1"
allegati: []
---

# La moka in container

## Perché mettere la moka in un container

La moka aziendale funziona solo sulla scrivania di Gino. Metterla in un container significa
che chiunque la avvia ottiene lo stesso caffè: stessa miscela, stessa macinatura, stessa
pressione. È il principio «sul mio PC funziona» applicato al caffè.

## Il Mokafile

Il Mokafile descrive come si prepara la moka. Ogni istruzione è uno strato:

```text
FROM moka:3-tazze
COPY miscela-arabica /caldaia
## questo commento resta dentro il blocco di codice
RUN accendi-fuoco --fiamma bassa
```

La fiamma va tenuta bassa: con la fiamma alta il caffè brucia e diventa amaro.