# MiroFish-CC

**A Claude Code reimplementation of [MiroFish](https://github.com/666ghj/MiroFish) — the multi-agent swarm intelligence prediction engine.**

> Predict anything by simulating thousands of AI agents interacting on social platforms.

## What Is This?

MiroFish-CC brings the full power of MiroFish's swarm intelligence engine into Claude Code as a skill/command. Instead of a web UI + Flask server + Zep Cloud + OASIS, everything runs locally through Claude Code:

- **Claude Code IS the LLM** — no external API keys needed
- **Local JSON files** replace Zep Cloud for knowledge graphs and memory
- **Custom simulation engine** replaces OASIS for social platform simulation
- **CLI interface** replaces the Vue.js frontend

## How It Works

```
Seed Materials (PDF/MD/TXT)
    ↓
Entity & Relationship Extraction (Claude)
    ↓
Knowledge Graph (local JSON)
    ↓
Agent Persona Generation (Claude)
    ↓
Multi-Round Social Simulation (Twitter + Reddit)
    ↓
Prediction Report (Claude ReACT analysis)
    ↓
Interactive Chat (with any agent or the report)
```

## Quick Start

### 1. Install

```bash
cd tools/mirofish-cc
pip install -e .
```

### 2. Use via Claude Code Skill

Just tell Claude Code what you want to predict:

```
> /mirofish
> "Predict how the public will react to [event X] based on this report..."
```

Claude Code will guide you through the full workflow.

### 3. Use via CLI (manual)

```bash
# Create a project
python -m mirofish project create "My Prediction" -r "How will markets react to the Fed rate hike?"

# Process seed materials
python -m mirofish seed process report.pdf news.md -p <project_id>

# ... follow the workflow (see SKILL.md for full steps)
```

## Architecture

```
┌─────────────────────────────────────────┐
│         Claude Code (the LLM)           │
│  Entity extraction, persona generation, │
│  agent decisions, report writing, chat  │
└────────────────┬────────────────────────┘
                 │ runs CLI commands
┌────────────────▼────────────────────────┐
│      Python Package (mirofish/)         │
│  File parsing, JSON storage, platform   │
│  mechanics, state management, search    │
└────────────────┬────────────────────────┘
                 │ reads/writes
┌────────────────▼────────────────────────┐
│       Local JSON Files (data/)          │
│  projects, graphs, agents, simulations  │
└─────────────────────────────────────────┘
```

## Features

| Feature | Description |
|---------|-------------|
| **Seed Ingestion** | PDF, Markdown, TXT with encoding detection |
| **Ontology Generation** | Entity types + relationship types from seed text |
| **Knowledge Graph** | Local JSON-based graph with temporal edges |
| **Agent Personas** | Individual + group personas with MBTI, interests, profession |
| **Dual-Platform Sim** | Twitter (6 actions) + Reddit (13 actions) |
| **Configurable Batching** | 5-8 agents per prompt for efficiency |
| **Graph Search** | Quick, Panorama, and Insight search modes |
| **ReACT Reports** | Multi-section prediction reports with evidence |
| **Agent Interviews** | Chat with any simulated agent in character |
| **Batch Interviews** | Query multiple agents simultaneously |

## Project Structure

```
mirofish-cc/
├── .claude/skills/mirofish/SKILL.md   # Claude Code skill
├── mirofish/                           # Python package
│   ├── cli.py                          # Click CLI
│   ├── config.py                       # Configuration
│   ├── models/                         # Data models
│   │   ├── project.py                  # Project state
│   │   ├── agent.py                    # Agent profiles
│   │   ├── graph.py                    # Knowledge graph
│   │   ├── simulation.py              # Simulation state
│   │   └── platform.py               # Social platforms
│   ├── services/                       # Business logic
│   │   ├── seed_processor.py          # File processing
│   │   ├── graph_builder.py           # Graph construction
│   │   ├── persona_generator.py       # Persona generation
│   │   ├── simulation_engine.py       # Simulation engine
│   │   ├── graph_search.py            # Graph retrieval
│   │   ├── report_generator.py        # Report generation
│   │   └── chat_service.py           # Chat/interviews
│   ├── prompts/                        # LLM prompt templates
│   └── utils/                          # Utilities
├── data/projects/                      # Runtime data
├── pyproject.toml
└── README.md
```

## Requirements

- Python 3.11+
- Claude Code Max plan
- Seed materials (any topic you want to predict)

## License

AGPL-3.0 (same as original MiroFish)

## Credits

Based on [MiroFish](https://github.com/666ghj/MiroFish) by 666ghj, powered by Shanda Group.
Original simulation engine by [CAMEL-AI OASIS](https://github.com/camel-ai/oasis).
