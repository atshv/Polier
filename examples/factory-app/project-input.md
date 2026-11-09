# Project Input: Fault Codes

> Station 1 (idea) of the factory line. The block is what Polier reads; the sections below are background in the owner's words.

```text
PROJECT:        A phone app for heat-pump service technicians that finds the meaning of a
                fault code and the first checks to do, also in a basement without signal.
                For technicians on site who today search PDF manuals. Success: a code is
                explained in under ten seconds, offline. Out of scope: ordering parts,
                customer data, a web version, chat.
PLATFORMS:      ios, android
TRAITS:         offline, i18n, cross_platform
MODE:           greenfield
PROFILE:        S
LANGUAGE:       docs and code in English; UI in German and English
BUDGET:         evenings over two months; store fees only
EXISTING REPO:  none
```

## Problem

Fault codes are spread over several manufacturer PDFs. On site there is often no signal, and searching a 300-page PDF on a phone with gloves takes minutes.

## Users

Service technicians, on site, one hand free, often in a basement or a boiler room.

## Success signal

After four weeks, a technician finds any code of the supported models in under ten seconds without network.

## Non-goals

Ordering parts, customer or job data, accounts, a web version, chat. Team sharing may come later.

## Platforms

iOS and Android from one codebase; Android first because most company phones are Android.

## Budget and time

Evenings over two months. Apple Developer Program (yearly) and Google Play Console (one-off) are the only costs.
