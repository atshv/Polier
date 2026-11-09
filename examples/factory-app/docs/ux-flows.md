# UX Flows: Fault Codes

## Flows

### F1 — Find a code (US1, US2)

1. Search: the field has focus on start; the user types `E123` or a word.
2. Results update per keystroke; one tap opens the detail.
3. Detail: meaning, causes, first checks; back returns to the results with the text kept.
4. No match: the empty state suggests checking the model generation.

## Screens

| Screen | Purpose | Main elements | States | Wireframe |
| --- | --- | --- | --- | --- |
| Search | find a code | search field, result list | empty, results, no match | below |
| Detail | explain a code | title, meaning, causes, checks | content, missing data | below |

```text
+---------------------------+   +---------------------------+
| [ E123____________ ] (x)  |   | <  E123 Low pressure      |
|---------------------------|   |---------------------------|
| E123  Low pressure        |   | Meaning                   |
| E124  High pressure       |   | Causes  1. … 2. …         |
| E130  Sensor fault        |   | First checks  1. … 2. …   |
+---------------------------+   +---------------------------+
```
