<div align="center">

<br>

# Prompt Generator

**Turn a project idea into a clear plan your AI coding agent can actually follow.**

<br>

![version](https://img.shields.io/badge/version-0.4-1e293b?style=flat-square&labelColor=0f172a)
![license](https://img.shields.io/badge/license-MIT-1e293b?style=flat-square&labelColor=0f172a)
![price](https://img.shields.io/badge/price-free-1e293b?style=flat-square&labelColor=0f172a)
![format](https://img.shields.io/badge/format-markdown-1e293b?style=flat-square&labelColor=0f172a)

<br>

</div>

> **The short version.** You don't get code from this. You get a plan, a task list and clear instructions, so the AI that writes your code stays on track.

<br>

## The big picture

```mermaid
flowchart TB
    subgraph IN ["You bring"]
        I1["An idea<br><i>3–6 sentences</i>"]
    end

    subgraph GEN ["The generator does"]
        direction LR
        G1["Asks questions"] --> G2["Drafts a plan"] --> G3["Waits for your OK"] --> G4["Writes the files"]
    end

    subgraph OUT ["You get"]
        direction LR
        O1["Architecture<br><i>1 page</i>"]
        O2["Task board<br><i>with dependencies</i>"]
        O3["Next 3–5 tasks<br><i>ready to run</i>"]
        O1 ~~~ O2 ~~~ O3
    end

    IN --> GEN --> OUT

    style IN fill:#f8fafc,stroke:#94a3b8,color:#0f172a
    style GEN fill:#eff6ff,stroke:#3b82f6,color:#1e3a8a
    style OUT fill:#f0fdf4,stroke:#22c55e,color:#14532d
```

<br>

## A typical session

```mermaid
sequenceDiagram
    autonumber
    actor You
    participant G as Generator
    participant B as Builder AI
    participant R as Reviewer AI

    You->>G: Here is my idea
    G->>You: A few questions
    You->>G: Answers
    G->>You: Plan and task list
    You->>G: Looks good, go
    G-->>B: Task M01
    B-->>R: Finished work
    R-->>You: Review result
    Note over You,R: Repeat with the next 3–5 tasks
```

<br>

## Get started in 5 minutes

- [ ] **Download** this repo. Green **Code** button, then **Download ZIP**.
- [ ] **Open a new chat** with your AI coding tool.
- [ ] **Add these files** to the chat.
  ```
  generator.md   rubric.md   templates/   tools/
  ```
- [ ] **Fill in** the input block at the top of `generator.md`.
- [ ] **Answer** the questions and approve the plan.
- [ ] **Build** with the first task, `tasks/M01.md`.

> [!NOTE]
> The prompts are currently written in **German**. Your project can still be in any language. An English version is planned.

<br>

## What lands in your project

```
my-project/
│
├─ ARCHITECTURE.md ····· the key decisions, one page
├─ AGENTS.md ··········· rules the AI must follow
├─ board.json ·········· every task and what it depends on
├─ STATUS.md ··········· progress, generated from the board
│
├─ tasks/
│   └─ M01.md … M05.md · only the next few tasks
│
└─ docs/ ··············· extra details, only when needed
```

Every task gets its own Git branch and exactly one commit, so your history stays easy to read.

```mermaid
gitGraph
    commit id: "scaffold"
    branch task/M01
    commit id: "M01: Setup"
    checkout main
    merge task/M01
    branch task/M02
    commit id: "M02: Data model"
    checkout main
    merge task/M02
    branch task/M03
    commit id: "M03: Add and list"
    checkout main
    merge task/M03
```

<br>

## How big is your project?

The generator suggests a size for you. Most projects are **S**.

```mermaid
flowchart LR
    Q1{"Can two tasks run<br>at the same time<br>without touching<br>the same files?"}
    Q1 -- no --> S["<b>S</b><br>1 builder<br>1 reviewer"]
    Q1 -- yes --> Q2{"Several services<br>or repos?"}
    Q2 -- no --> M["<b>M</b><br>1 lead<br>2–3 builders<br>1 reviewer"]
    Q2 -- yes --> L["<b>L</b><br>full team<br>plus integrator"]

    style S fill:#dcfce7,stroke:#22c55e,color:#14532d
    style M fill:#dbeafe,stroke:#3b82f6,color:#1e3a8a
    style L fill:#ede9fe,stroke:#6366f1,color:#312e81
```

<br>

## Six rules it never breaks

| | | |
|:---|:---|:---|
| **1 · Short plan**<br>One page, not a book. | **2 · One file, one job**<br>Rules, plan and progress stay apart. | **3 · Only what's next**<br>3–5 tasks at a time, not 25. |
| **4 · Few agents**<br>One builder and one reviewer is usually enough. | **5 · Tests first**<br>Code must pass checks before anyone reviews it. | **6 · One writer per file**<br>Two agents never edit the same file at once. |

<br>

## Inside this repo

| | |
|---|---|
| [`generator.md`](generator.md) | **The main prompt.** Start here. |
| [`cheatsheet.md`](cheatsheet.md) | Quick guide for you, with checklists |
| [`rubric.md`](rubric.md) | Quality checks before you approve anything |
| [`dsh.md`](dsh.md) | Setup for sizes M and L |
| [`templates/`](templates/) | Blank templates the generator fills in |
| [`tools/`](tools/) | Python scripts that check a project |
| [`examples/minimal-cli/`](examples/minimal-cli/) | A finished example with 6 tasks |

<details>
<summary><b>Run the checks on the example</b></summary>
<br>

```bash
python3 tools/check.py examples/minimal-cli
python3 tools/render_status.py examples/minimal-cli --out STATUS.md
```

</details>

<br>

## Built on good ideas

[BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) ·
[GitHub Spec Kit](https://github.com/github/spec-kit) ·
[Claude Code Agent Teams](https://code.claude.com/docs/en/agent-teams) ·
[Cognition](https://cognition.com/blog/dont-build-multi-agents) ·
[Anthropic](https://www.anthropic.com/engineering/building-effective-agents) ·
[AGENTS.md](https://agents.md/)

<br>

<div align="center">
<sub><a href="LICENSE">MIT License</a> · Free to use, change and share</sub>
</div>
