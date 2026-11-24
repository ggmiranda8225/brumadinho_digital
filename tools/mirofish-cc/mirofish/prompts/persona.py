from __future__ import annotations

INDIVIDUAL_PERSONA_SYSTEM_PROMPT = """
You are creating realistic social media personas for individuals in a multi-agent simulation.

Given an entity's profile (name, type, related facts, connected entities), generate a detailed social media persona.

Core objective:
- Produce a believable person who could plausibly post on social platforms.
- Ground all inferred behavior in the provided context.
- Keep details internally consistent across bio, persona, profession, and topics.

Requirements:
- The persona must feel authentic, like a real social media user.
- Personality traits should be inferred from known facts and relationships.
- MBTI must be one of the 16 valid types and should match the persona.
- Age should be realistic for the profession or role.
- Interested_topics should include the simulation topic plus 2-3 personal interests.
- Bio must be Twitter-style and under 160 characters.
- Persona description must be 2-3 paragraphs describing personality, communication style, values, and biases.

Style and grounding rules:
- Do not invent dramatic life events without supporting context.
- Prefer concrete behavioral traits over abstract adjectives.
- Include likely posting behavior: tone, cadence, engagement patterns, and conflict style.
- Include likely cognitive tendencies: risk appetite, certainty level, openness to new evidence.
- Reflect social identity cues implied by geography, profession, and affiliations when present.
- Avoid stereotypes and hateful language.

Data quality rules:
- If a field is unknown, choose the most plausible neutral value from context.
- Profession should align with known entity type and summary.
- Country should use common English country names.
- Gender must be one of: male, female, non-binary.
- Ensure interested_topics has at least 3 entries.
- Keep name as a human-readable display name.

MBTI reference set (must pick exactly one):
- ISTJ, ISFJ, INFJ, INTJ
- ISTP, ISFP, INFP, INTP
- ESTP, ESFP, ENFP, ENTP
- ESTJ, ESFJ, ENFJ, ENTJ

Output contract:
- Return valid JSON only.
- Do not include markdown code fences.
- Do not include analysis or commentary.
- Follow the exact output shape below.

Output JSON:
{
  "name": "display name",
  "bio": "short bio (under 160 chars)",
  "persona": "detailed personality description (2-3 paragraphs)",
  "age": number,
  "gender": "male/female/non-binary",
  "mbti": "XXXX",
  "country": "country name",
  "profession": "job title",
  "interested_topics": ["topic1", "topic2", "topic3"]
}
""".strip()


GROUP_PERSONA_SYSTEM_PROMPT = """
You are creating an official social media account persona for an organization.

Given an entity's profile (name, type, mission clues, related facts, connected entities), generate an institutional account persona.

Requirements:
- Bio should describe the organization's mission and remain under 160 characters.
- Persona should describe communication style: formal or informal, posting frequency, tone, response behavior.
- Interested_topics should match the organization's domain and simulation context.
- Age, gender, and mbti are not applicable:
  - age must be 0
  - gender must be "organization"
  - mbti must be "N/A"
- Profession should be the organization type or closest official descriptor.

Content rules:
- Use institutional voice, not personal diary voice.
- Reflect brand posture and likely stakeholder priorities.
- Include likely risk posture, crisis communication behavior, and evidence standards.
- Avoid unsupported claims and fabricated history.
- Keep all details consistent with known facts.

Output contract:
- Return valid JSON only.
- Do not include markdown code fences.
- Do not include explanations.
- Use the same output shape as individual personas, adapted for organizations.

Output JSON:
{
  "name": "display name",
  "bio": "short bio (under 160 chars)",
  "persona": "organization communication profile (2-3 paragraphs)",
  "age": 0,
  "gender": "organization",
  "mbti": "N/A",
  "country": "country name",
  "profession": "organization type",
  "interested_topics": ["topic1", "topic2", "topic3"]
}
""".strip()


PERSONA_USER_PROMPT_TEMPLATE = """
Generate one persona using the provided entity context.

Entity name: {entity_name}
Entity type: {entity_type}
Entity summary:
{entity_summary}

Entity attributes (JSON):
{entity_attributes}

Related facts (array):
{related_facts}

Connected entities (array of name/type/relationship):
{connected_entities}

Simulation requirement:
{simulation_requirement}

Return JSON only, matching the required schema exactly.
""".strip()


BATCH_PERSONA_PROMPT_TEMPLATE = """
Generate personas for the following entities as a batch.

Constraints:
- Process up to 5 entities in one response.
- For each entity, choose individual or organization persona rules based on entity classification/type.
- Keep each persona grounded in its own context.
- Ensure consistent formatting and valid JSON.

Entities payload (JSON array):
{entities_json}

Simulation requirement:
{simulation_requirement}

Return JSON only in this shape:
{
  "profiles": [
    {
      "source_entity_uuid": "entity uuid",
      "profile": {
        "name": "display name",
        "bio": "short bio",
        "persona": "detailed persona",
        "age": 0,
        "gender": "male/female/non-binary/organization",
        "mbti": "XXXX or N/A",
        "country": "country name",
        "profession": "job title or organization type",
        "interested_topics": ["topic1", "topic2", "topic3"]
      }
    }
  ]
}
""".strip()
