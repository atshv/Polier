# Concept: Fault Codes

## Personas

| Name | Situation | Goal | Frustration today |
| --- | --- | --- | --- |
| Marco, 41, service technician | basement, no signal, gloves | understand a code and know the first check | PDF manuals, slow search |
| Lea, 26, apprentice | on site with a senior colleague | learn what the codes mean | does not know which manual applies |

## Features

| Feature | Priority | Why |
| --- | --- | --- |
| Search a code by number or text | MVP | core of the success signal |
| Code detail: meaning, causes, first checks | MVP | the answer the technician needs |
| Works fully offline | MVP | basements have no signal |
| German and English | MVP | both languages in the team |
| Favourites and recent codes | next | faster after a week of use |
| Photo of the type plate to pick the model | later | needs camera and recognition |

## User stories

- **US1** As Marco I want to type a fault code so that I see its meaning at once.
  - WHEN Marco enters `E 123` THEN the matching code opens in under one second.
- **US2** As Marco I want the first checks for a code so that I know where to start.
  - WHEN a code is open THEN the causes and checks are listed in order of likelihood.
- **US3** As Lea I want the app to work without network so that it helps in every basement.
  - WHEN the phone is offline THEN search and detail work as online.

## Alternatives

| Alternative | What it does well | Why this project anyway |
| --- | --- | --- |
| Manufacturer PDFs | complete and official | slow on a phone, no cross-manual search |
| Manufacturer service apps | official data | one brand each, often online only |

## Costs

| Item | Per month | Source/date |
| --- | --- | --- |
| Apple Developer Program | yearly fee [VERIFY: current price] | developer.apple.com, to check at the release station |
| Google Play Console | one-off fee [VERIFY: current price] | play.google.com/console, to check at the release station |
| Hosting | none (data ships with the app) | — |

## Risks

| Risk | Effect | How the plan reduces it |
| --- | --- | --- |
| Manual content may not be redistributed | app cannot ship the data | check terms per manufacturer before the plan station; own wording of checks |
| Codes differ between model generations | wrong advice | model generation is part of every code entry |
| Store review rejects a thin app | release delayed | clear value, offline data, no web wrapper |
