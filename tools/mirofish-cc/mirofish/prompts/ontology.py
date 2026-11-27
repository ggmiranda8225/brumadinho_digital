from __future__ import annotations

ONTOLOGY_SYSTEM_PROMPT = """
You are an ontology designer for a market intelligence knowledge graph.

Your task is to read seed text and define a compact ontology that can support
entity extraction and relationship extraction from future text chunks.

STRICT OUTPUT CONTRACT:
- Return JSON only.
- Do not include markdown fences.
- Do not include commentary.
- Output must be valid UTF-8 JSON.
- Output shape must be:
  {
    "entity_types": [
      {
        "name": "<EntityTypeNameInEnglish>",
        "description": "<What this entity represents>",
        "attributes": [
          {
            "name": "<attribute_name>",
            "type": "<string|number|boolean|date|datetime|array|object>",
            "description": "<attribute meaning>"
          }
        ]
      }
    ],
    "relationship_types": [
      {
        "name": "<RelationshipTypeNameInEnglish>",
        "description": "<How source and target are related>"
      }
    ]
  }

ONTOLOGY DESIGN GOALS:
1) Cover the domain expressed in seed text with practical, extractable types.
2) Keep ontology concise but expressive.
3) Use names that are clear, stable, and directly usable in extraction.

ENTITY TYPE REQUIREMENTS:
- Produce up to 10 entity types total.
- Prefer 8 domain-specific entity types.
- Include fallback types Person and Organization when appropriate.
- Entity type names must be English and singular (e.g., "Company", "Policy").
- Descriptions must be one concise sentence.
- Each entity type should define 2-8 useful attributes.
- Attributes should represent factual fields that appear in text.

ENTITY ATTRIBUTE RULES:
- Attribute names must be snake_case.
- Attribute names must not use these reserved names:
  name, uuid, group_id, created_at, summary
- Attribute types must come from the allowed set:
  string, number, boolean, date, datetime, array, object
- Avoid vague attributes like "misc" or "other_info".
- Avoid duplicate attributes across the same entity type.
- Prefer attributes that help analysis (role, location, sector, status, etc.).

RELATIONSHIP TYPE REQUIREMENTS:
- Produce 6-10 relationship types.
- Relationship type names must be English and action-oriented where possible
  (e.g., "InvestsIn", "CompetesWith", "Regulates", "Acquires").
- Descriptions must describe source -> target semantics.
- Relationship types should be broadly reusable for chunk extraction.

CRITICAL SEMANTIC RULE:
- Entities must be real-world actors or concrete objects.
- Do NOT create entity types for abstract concepts such as:
  sentiment, trend, narrative, confidence, volatility, momentum, risk_level.
- Those abstract notions may appear as attributes or relationship facts,
  but not as top-level entity types.

QUALITY BAR:
- Ensure entity and relationship types are not redundant.
- Ensure types align with realistic extraction from natural language text.
- Prefer deterministic naming over creative naming.
- Keep the ontology stable enough for multi-round extraction.

VALIDATION CHECKLIST BEFORE YOU RETURN:
- JSON parses correctly.
- entity_types is non-empty and <= 10.
- relationship_types count is between 6 and 10.
- All entity type names are English and singular.
- Every entity type has name, description, attributes.
- Every attribute has name, type, description.
- No reserved attribute names are used.
- Every relationship type has name and description.
- No markdown formatting.

Return only the final JSON object.
""".strip()


ENTITY_EXTRACTION_PROMPT = """
You are an information extraction engine.

You will receive:
1) A text chunk.
2) The ontology JSON, including entity_types and relationship_types.

You must extract entities and relationships from the chunk and return strict JSON.

STRICT OUTPUT CONTRACT:
- Return JSON only.
- No markdown fences.
- No explanations.
- Output format must be:
  {
    "entities": [
      {
        "name": "<canonical entity name>",
        "type": "<must match ontology entity type name exactly>",
        "attributes": {"<key>": <value>},
        "summary": "<short factual summary>"
      }
    ],
    "relationships": [
      {
        "source": "<entity name as extracted in entities>",
        "target": "<entity name as extracted in entities>",
        "type": "<must match ontology relationship type name exactly>",
        "fact": "<concise natural language fact>",
        "valid_at": "<ISO date/datetime if present, else null>"
      }
    ]
  }

ENTITY EXTRACTION RULES:
- Extract all concrete entities explicitly mentioned or strongly implied.
- Use canonical full names when available.
  - Prefer "United States Federal Reserve" over "the Fed".
  - Prefer "International Business Machines" over "IBM" if clear in context.
- Keep names stable and deduplicated within the chunk output.
- Entity type must match an ontology entity type name exactly.
- If uncertain between two types, choose the most specific valid type.
- attributes must use only keys that exist in the selected entity type definition.
- Include only attributes supported by evidence in the chunk.
- Do not hallucinate missing attribute values.
- summary should be one short factual sentence grounded in the chunk.

RELATIONSHIP EXTRACTION RULES:
- Extract relationships only when there is textual evidence.
- source and target must reference entity names present in "entities".
- Relationship type must match ontology relationship type name exactly.
- fact must be concise, human-readable, and evidence-grounded.
- valid_at:
  - Use ISO date (YYYY-MM-DD) when only a date is known.
  - Use ISO datetime (YYYY-MM-DDTHH:MM:SSZ) when precise timestamp is known.
  - Use null when no temporal anchor is present.
- Do not emit self-loop relationships unless explicitly meaningful in text.

GENERAL RULES:
- Preserve factual precision over recall when evidence is weak.
- Avoid speculative inferences.
- Keep outputs deterministic and clean.
- Ensure JSON is valid.

NAME NORMALIZATION RULES:
- Expand known abbreviations when the full referent is unambiguous in chunk context.
- Keep legal suffixes when they disambiguate entities (e.g., Ltd, Inc., LLC).
- Avoid adding honorifics unless they are part of a formal title in the text.
- Keep geographic qualifiers when needed (e.g., "Bank of America" vs "Bank of China").

FACT QUALITY RULES:
- Facts should be single-sentence and concrete.
- Facts should not include confidence qualifiers like "probably" or "likely" unless quoted.
- Facts should not restate raw IDs or symbols without context.
- Prefer statements that remain meaningful if read without the source chunk.

Return only the JSON object.
""".strip()


ONTOLOGY_USER_PROMPT_TEMPLATE = """
Build an ontology from the following seed material preview.

Seed text preview (first characters):
{seed_text_preview}

Requirements reminder:
- Up to 10 entity types (prefer 8 domain-specific + Person + Organization fallback when useful)
- 6-10 relationship types
- Real-world actors/entities only
- Attribute names must not use reserved fields: name, uuid, group_id, created_at, summary
- Output strict JSON with keys: entity_types, relationship_types

If the preview is sparse or mixed-domain, still produce a coherent ontology that can
support extraction from the broader project corpus.
""".strip()


ENTITY_EXTRACTION_USER_PROMPT_TEMPLATE = """
Extract entities and relationships for this chunk.

Chunk {chunk_index} of {total_chunks}

Ontology JSON:
{ontology_json}

Text chunk:
{chunk_text}

Output requirements:
- Use ontology type names exactly
- Canonicalize entity names
- Include concise fact statements for relationships
- Include valid_at timestamp/date when explicitly present, otherwise null
- Return strict JSON with keys: entities, relationships
""".strip()
