# MiroFish — Swarm Intelligence Prediction Engine

A Claude Code reimplementation of [MiroFish](https://github.com/666ghj/MiroFish). Predict anything by simulating AI agents interacting on social platforms.

## Trigger

Activate when user:
- Types `/mirofish`
- Asks to "predict", "simulate future", "run social simulation", "agent simulation"
- Wants to analyze how agents would react to a scenario
- Mentions "MiroFish" by name

## Prerequisites

- Python 3.11+ installed
- MiroFish package installed: `pip install -e tools/mirofish-cc` (a partir da raiz do repositório)
- Seed materials ready (PDF, MD, or TXT files)

## Quick Start

Ask the user for:
1. **Project name** — a short descriptive name
2. **Seed materials** — file paths to PDF, Markdown, or TXT files containing background information
3. **Prediction requirement** — what they want to predict (natural language question)

Then follow the full workflow below step by step.

---

## Full Workflow

### Step 1: Create Project

```bash
python -m mirofish project create "<project_name>" -r "<prediction requirement/question>"
```

Save the returned `project_id` — you need it for ALL subsequent commands.

### Step 2: Process Seed Materials

```bash
python -m mirofish seed process <file1> <file2> ... -p <project_id>
```

This parses files (PDF/MD/TXT), extracts text, and chunks it for processing.

### Step 3: Generate Ontology

First, get the seed text preview:
```bash
python -m mirofish seed preview -p <project_id>
```

Read the preview. Now generate an **ontology** — a schema of entity types and relationship types present in the seed material.

Load the ontology prompt template:
```bash
python -m mirofish ontology prompt -p <project_id>
```

Using the prompt and preview, generate a JSON ontology with:
- Up to **10 entity types** (domain-specific + Person + Organization fallbacks)
- **6-10 relationship types** describing how entities connect
- Each type has: `name` (English), `description`, and for entities `attributes` list

Output format:
```json
{
  "entity_types": [
    {"name": "Person", "description": "An individual person", "attributes": [{"name": "role", "type": "string", "description": "Their role"}]}
  ],
  "relationship_types": [
    {"name": "WORKS_FOR", "description": "Employment relationship"}
  ]
}
```

Save it:
```bash
python -m mirofish ontology save -p <project_id> --data '<ontology_json>'
```

### Step 4: Build Knowledge Graph

Loop through text chunks, extracting entities and relationships:

```bash
python -m mirofish graph get-batch -p <project_id> -b 0
```

For each batch, read the chunks and extract entities/relationships matching the ontology. The output from `get-batch` includes the extraction prompt template.

Output format for extraction:
```json
{
  "entities": [
    {"name": "Entity Name", "type": "Person", "attributes": {"role": "CEO"}, "summary": "Brief description"}
  ],
  "relationships": [
    {"source": "Entity A", "target": "Entity B", "type": "WORKS_FOR", "fact": "A works for B since 2020", "valid_at": "2020-01-01"}
  ]
}
```

Save extracted data:
```bash
python -m mirofish graph add -p <project_id> --data '<extracted_json>'
```

**Repeat** with incrementing batch index (`-b 1`, `-b 2`, ...) until the response shows `"has_more": false`.

Finalize the graph:
```bash
python -m mirofish graph finalize -p <project_id>
```

Check stats:
```bash
python -m mirofish graph stats -p <project_id>
```

### Step 5: Generate Agent Personas

Get entities needing personas:
```bash
python -m mirofish persona list -p <project_id>
```

For each entity (or in batches), generate a detailed social media persona. Each persona needs:
- `name`, `bio` (under 160 chars), `persona` (2-3 paragraph personality description)
- `age`, `gender`, `mbti` (one of 16 types), `country`, `profession`
- `interested_topics` (list of 3-5 topics)
- `source_entity_uuid` (from the entity list)
- `source_entity_type` (from the entity list)

Use the prompt templates from `mirofish.prompts.persona` for guidance.

Save each persona:
```bash
python -m mirofish persona save -p <project_id> --data '<profile_json>'
```

Or save multiple at once:
```bash
python -m mirofish persona save-batch -p <project_id> --data '<profiles_array_json>'
```

Check progress:
```bash
python -m mirofish persona status -p <project_id>
```

### Step 6: Run Simulation

#### 6a. Initialize

```bash
python -m mirofish sim init -p <project_id> --rounds 20 --batch-size 6
```

Adjust `--rounds` (default 20) and `--batch-size` (default 6, range 5-8) as needed.

#### 6b. Generate Seed Posts

Get context for initial posts:
```bash
python -m mirofish sim seed-context -p <project_id>
```

Generate 2-3 seed posts per platform (Twitter + Reddit) to kickstart discussion. Format:
```json
[
  {"agent_id": "<agent_id>", "platform": "twitter", "content": "Initial post about the topic..."},
  {"agent_id": "<agent_id>", "platform": "reddit", "content": "Another perspective..."}
]
```

Apply seed posts:
```bash
python -m mirofish sim apply-seeds -p <project_id> --data '<seed_posts_json>'
```

#### 6c. Simulation Loop (MAIN LOOP)

For each round (1 to total_rounds):

**1. Get round data:**
```bash
python -m mirofish sim get-round -p <project_id>
```

This returns batched agent data with personas, feeds, and available actions for both Twitter and Reddit.

**2. Decide agent actions:**

For each batch, read the agent personas and their current feeds. Decide ONE action per agent based on their personality, interests, and what they see. Use the prompt template from `mirofish.prompts.simulation`.

**Available Twitter actions:** CREATE_POST, LIKE_POST, REPOST, FOLLOW, DO_NOTHING, QUOTE_POST
**Available Reddit actions:** LIKE_POST, DISLIKE_POST, CREATE_POST, CREATE_COMMENT, LIKE_COMMENT, DISLIKE_COMMENT, SEARCH_POSTS, SEARCH_USER, TREND, REFRESH, DO_NOTHING, FOLLOW, MUTE

Output format:
```json
[
  {
    "agent_id": "...",
    "platform": "twitter",
    "action": "CREATE_POST",
    "args": {"content": "My thoughts on this topic..."}
  },
  {
    "agent_id": "...",
    "platform": "reddit",
    "action": "LIKE_POST",
    "args": {"target_post_id": "post-uuid-here"}
  }
]
```

**3. Apply actions:**
```bash
python -m mirofish sim apply -p <project_id> --round <N> --data '<actions_json>'
```

**4. (Optional) Update agent memories:**
```bash
python -m mirofish sim update-memories -p <project_id> --round <N> --data '<memories_json>'
```

**5. Check progress:**
```bash
python -m mirofish sim status -p <project_id>
```

**Repeat** until all rounds complete.

**PARALLELISM TIP:** Use Claude Code subagents (`task()`) to process Twitter and Reddit batches simultaneously. Each batch is independent.

### Step 7: Generate Prediction Report

#### 7a. Plan Report Outline

Get planning context:
```bash
python -m mirofish report plan-context -p <project_id>
```

Generate a report outline with 2-5 sections. Each section should focus on a distinct analytical angle of the prediction.

```json
{
  "title": "Prediction Report: [Topic]",
  "summary": "Executive summary of the prediction...",
  "sections": [
    {"title": "Section Title", "description": "What this section analyzes"}
  ]
}
```

Save:
```bash
python -m mirofish report save-outline -p <project_id> --data '<outline_json>'
```

#### 7b. Write Sections (ReACT Pattern)

For each section:

1. **Think:** What information do I need for this section?
2. **Search:** Query the knowledge graph and simulation data:
```bash
python -m mirofish search insight -p <project_id> -q "<your query>"
python -m mirofish search posts -p <project_id> --platform twitter --limit 10
python -m mirofish search quick -p <project_id> -q "<specific fact>"
```
3. **Write:** Draft 300-600 words of analytical content. Cite data. Quote agent posts using `>` blockquotes.
4. **Save:**
```bash
python -m mirofish report save-section -p <project_id> --index <N> --content '<markdown_content>'
```

#### 7c. Assemble Final Report

```bash
python -m mirofish report assemble -p <project_id>
```

View it:
```bash
python -m mirofish report view -p <project_id>
```

### Step 8: Interactive Mode

After report generation, offer the user these options:

#### A) View the full report
```bash
python -m mirofish report view -p <project_id>
```

#### B) Interview a specific agent
```bash
python -m mirofish chat list-agents -p <project_id>
python -m mirofish chat agent-context -p <project_id> -a "<agent_name>"
```
Then role-play as that agent, staying in character based on their persona, memories, and simulation history.

#### C) Ask about the report
```bash
python -m mirofish chat report-context -p <project_id>
```
Answer questions about the prediction using the report and underlying data.

#### D) Batch interview multiple agents
```bash
python -m mirofish chat batch-context -p <project_id> --agents "name1,name2,name3" -t "<interview topic>"
```
Generate responses from each agent's perspective on the topic.

---

## Error Recovery

- **Seed processing fails:** Check file paths and formats. Only PDF, MD, TXT supported.
- **Graph building fails:** Re-run the failed batch (`-b N`). Already-added entities won't duplicate.
- **Simulation interrupted:** Resume from last completed round — state is saved per-round.
- **Report section fails:** Re-generate just the failed section by index.
- **General errors:** All commands output JSON with `"error"` field on failure.

## Configuration

| Parameter | Default | Flag | Description |
|-----------|---------|------|-------------|
| Rounds | 20 | `--rounds` | Total simulation rounds |
| Batch size | 6 | `--batch-size` | Agents per prompt (5-8 recommended) |
| Chunk size | 500 | `--chunk-size` | Text chunk size in characters |
| Chunk overlap | 50 | `--chunk-overlap` | Overlap between chunks |

## Data Storage

All data stored locally as JSON files:
```
data/projects/<project_id>/
├── project.json          # Project metadata and status
├── seed/
│   ├── extracted_text.txt    # Full extracted text
│   ├── chunks.json           # Text chunks
│   └── seed_meta.json        # Processing metadata
├── graph/
│   ├── ontology.json         # Entity and relationship types
│   └── graph.json            # Knowledge graph (nodes + edges)
├── agents/
│   ├── <agent_id>.json       # Agent profiles
│   └── <agent_id>_memories.jsonl  # Agent memories
├── simulation/
│   ├── state.json            # Simulation state
│   ├── twitter_platform.json # Twitter platform state
│   ├── reddit_platform.json  # Reddit platform state
│   └── actions.jsonl         # Action log (all rounds)
└── reports/
    ├── outline.json          # Report outline
    ├── section_0.md          # Section content
    ├── section_1.md
    ├── report.md             # Final assembled report
    └── report_meta.json      # Report metadata
```

## Architecture Note

**Claude Code IS the LLM.** The Python package handles data plumbing only (file parsing, JSON storage, platform mechanics, state management). All intelligence — entity extraction, persona generation, agent decisions, report writing, chat — is provided by Claude Code directly. No external API keys needed.
