"""Evidence-bounded four-stage conversational workflow."""

import json
import os
import re
from typing import Any, TypedDict

from groq import Groq
from langgraph.graph import END, START, StateGraph

from .chat_evidence import gather_analytical_facts
from .rag_knowledge import retrieve

COUNTRIES = {"AU", "BR", "ID", "ZA"}
YEARS = set(range(2020, 2026))
SENSORS = {"MODIS", "VIIRS SNPP", "VIIRS JPSS-1"}

ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "countries": {"type": "array", "items": {"type": "string", "enum": sorted(COUNTRIES)}},
        "years": {"type": "array", "items": {"type": "integer", "enum": sorted(YEARS)}},
        "sensor": {"anyOf": [{"type": "string", "enum": sorted(SENSORS)}, {"type": "null"}]},
        "compare_sensors": {"type": "boolean"},
        "needs_rag": {"type": "boolean"},
        "needs_analytics": {"type": "boolean"},
    },
    "required": ["countries", "years", "sensor", "compare_sensors", "needs_rag", "needs_analytics"],
    "additionalProperties": False,
}

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "analytical_citations": {"type": "array", "items": {"type": "string"}},
        "knowledge_citations": {"type": "array", "items": {"type": "string"}},
        "suggested_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "analytical_citations", "knowledge_citations", "suggested_questions"],
    "additionalProperties": False,
}

ROUTER_PROMPT = """Classify the user's latest question and extract only explicit or clearly implied scopes.
Return countries from AU, BR, ID, ZA and years from 2020 through 2025. For a comparison across all years,
include each requested year. For "which year had highest/lowest" rankings, include all supported years.
Sensor must be MODIS, VIIRS SNPP, VIIRS JPSS-1, or null. Set compare_sensors when the question compares
two or more sensors, so IGNIS uses the all-sensor summary even if the UI filter selects one sensor. Set needs_analytics
for questions requiring IGNIS detection, track, sensor, FRP, temporal, or comparison metrics. Set needs_rag
for NASA FIRMS technical/scientific documentation questions. Set both for hybrid questions. For a generic
follow-up, use conversation context. Do not invent a scope; omitted countries/years inherit the UI context.
"""

ANSWER_PROMPT = """You are the IGNIS analytical assistant. Answer only from the supplied analytical_facts and
knowledge_chunks. Never invent numbers, years, countries, source details, or citations. Cite supporting
fact IDs in analytical_citations and source section IDs in knowledge_citations. Never cite an ID not present
in the supplied context. State plainly when a requested release is unavailable or still preparing; do not
substitute another country/year. Respect these scientific limits: NASA FIRMS detections are thermal anomalies,
not confirmed independent fires; candidate tracks are unvalidated algorithmic links; detections do not establish
burned area, spread, causes, current emergency conditions, or future fire risk. Sensor counts are not directly
comparable measures of actual fire incidence. Explain that swath width, spatial resolution, revisit schedule,
and sensor algorithms affect observed counts. Mention scope_notes when supplied. If evidence is insufficient,
say so and ask a concise follow-up. Return a short, readable Markdown answer, up to three relevant follow-up
questions, and the required structured citation arrays.
"""


class ChatState(TypedDict, total=False):
    message: str
    history: list[dict[str, str]]
    current_filters: dict[str, Any] | None
    route: dict[str, Any]
    analytical_facts: dict[str, dict]
    scope_notes: list[str]
    knowledge_chunks: list[dict[str, str]]
    generated: dict[str, Any]
    result: dict[str, Any]


class ChatUpstreamError(RuntimeError):
    """Groq failed or returned invalid structured output."""


class ChatRateLimitError(ChatUpstreamError):
    """Groq rejected a request because of an upstream rate limit."""


def _client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ChatUpstreamError("AI chat is not configured on the backend.")
    return Groq(api_key=api_key, timeout=45.0, max_retries=0)


def _structured_call(*, model: str, messages: list[dict[str, str]], name: str,
                     schema: dict, max_tokens: int, temperature: float = 0) -> dict:
    try:
        response = _client().chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_schema", "json_schema": {
                "name": name, "strict": True, "schema": schema,
            }},
            temperature=temperature,
            max_completion_tokens=max_tokens,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Groq returned an empty response.")
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError("Groq returned an invalid response shape.")
        return value
    except ChatUpstreamError:
        raise
    except Exception as error:
        if getattr(error, "status_code", None) == 429:
            raise ChatRateLimitError("AI chat is busy. Please try again shortly.") from error
        raise ChatUpstreamError("The AI service could not complete the request. Please try again.") from error


def route_and_extract(state: ChatState) -> dict:
    history = state.get("history", [])[-8:]
    messages = [{"role": "system", "content": ROUTER_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": state["message"]})
    model = os.getenv("GROQ_CHAT_ROUTER_MODEL", "openai/gpt-oss-20b")
    routed = _structured_call(
        model=model,
        messages=messages,
        name="ignis_chat_route",
        schema=ROUTE_SCHEMA,
        max_tokens=500,
    )
    return {"route": {
        "countries": [code for code in routed.get("countries", []) if code in COUNTRIES][:4],
        "years": sorted({year for year in routed.get("years", []) if year in YEARS})[:6],
        "sensor": routed.get("sensor") if routed.get("sensor") in SENSORS else None,
        "compare_sensors": bool(routed.get("compare_sensors")),
        "needs_rag": bool(routed.get("needs_rag")),
        "needs_analytics": bool(routed.get("needs_analytics")),
    }}


def gather_evidence(state: ChatState) -> dict:
    gathered = gather_analytical_facts(state["route"], state.get("current_filters"))
    chunks = retrieve(state["message"], limit=3) if state["route"]["needs_rag"] else []
    return {
        "analytical_facts": gathered["facts"],
        "scope_notes": gathered["scope_notes"],
        "knowledge_chunks": chunks,
    }


def generate_answer(state: ChatState) -> dict:
    context = {
        "analytical_facts": state.get("analytical_facts", {}),
        "scope_notes": state.get("scope_notes", []),
        "knowledge_chunks": state.get("knowledge_chunks", []),
    }
    messages = [{"role": "system", "content": ANSWER_PROMPT}]
    messages.extend(state.get("history", [])[-8:])
    messages.append({
        "role": "user",
        "content": "Question: " + state["message"] + "\nVerified context JSON:\n" + json.dumps(context, ensure_ascii=True),
    })
    generated = _structured_call(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        messages=messages,
        name="ignis_chat_answer",
        schema=ANSWER_SCHEMA,
        max_tokens=2200,
    )
    return {"generated": generated}


def validate_output(state: ChatState) -> dict:
    generated = state.get("generated", {})
    facts = state.get("analytical_facts", {})
    chunks = state.get("knowledge_chunks", [])
    available_fact_ids = {key for key, value in facts.items() if value.get("status") == "available"}
    available_knowledge_ids = {chunk["id"] for chunk in chunks}
    analytical_citations = list(dict.fromkeys(
        item for item in generated.get("analytical_citations", [])
        if isinstance(item, str) and item in available_fact_ids
    ))
    knowledge_citations = list(dict.fromkeys(
        item for item in generated.get("knowledge_citations", [])
        if isinstance(item, str) and item in available_knowledge_ids
    ))
    answer = generated.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        answer = "I couldn't form a reliable answer from the available evidence. Please rephrase the question."
    else:
        valid_citations = set(analytical_citations) | set(knowledge_citations)

        def keep_known_source(match: re.Match[str]) -> str:
            identifier = match.group(1)
            recognized = identifier.startswith("nasa_firms_knowledge#") or bool(
                re.match(r"^(AU|BR|ID|ZA)\.\d{4}\.", identifier)
            )
            return match.group(0) if not recognized or identifier in valid_citations else ""

        answer = re.sub(r"\[([A-Za-z0-9_.# -]+)\]", keep_known_source, answer)

    requested_analytics = state.get("route", {}).get("needs_analytics", False)
    has_available_metrics = any(value.get("status") == "available" for value in facts.values())
    unavailable = [value for value in facts.values() if value.get("status") == "unavailable"]
    if requested_analytics and facts and unavailable and not has_available_metrics:
        scopes = ", ".join(f"{item['country']} {item['year']}" for item in unavailable[:8])
        answer = f"I can't answer this from local data yet: no validated release is ready for {scopes}."
        analytical_citations = []

    suggestions = generated.get("suggested_questions", [])
    suggestions = [item.strip()[:240] for item in suggestions
                   if isinstance(item, str) and item.strip()][:3]
    requested = state.get("route", {})
    if requested.get("needs_analytics") and not analytical_citations and available_fact_ids:
        analytical_citations = [sorted(available_fact_ids)[0]]
    if requested.get("needs_rag") and not knowledge_citations and available_knowledge_ids:
        knowledge_citations = [sorted(available_knowledge_ids)[0]]
    required_tags = analytical_citations + knowledge_citations
    if required_tags and not any(f"[{tag}]" in answer for tag in required_tags):
        answer = answer.rstrip() + "\n\nSources: " + " ".join(f"[{tag}]" for tag in required_tags)
    return {"result": {
        "answer": answer.strip(),
        "analytical_citations": analytical_citations,
        "knowledge_citations": knowledge_citations,
        "suggested_questions": suggestions,
        "analytical_facts": facts,
        "knowledge_chunks": chunks,
        "scope_notes": state.get("scope_notes", []),
        "scope": state.get("route", {}),
    }}


_builder = StateGraph(ChatState)
_builder.add_node("route_and_extract", route_and_extract)
_builder.add_node("gather_evidence", gather_evidence)
_builder.add_node("generate_answer", generate_answer)
_builder.add_node("validate_output", validate_output)
_builder.add_edge(START, "route_and_extract")
_builder.add_edge("route_and_extract", "gather_evidence")
_builder.add_edge("gather_evidence", "generate_answer")
_builder.add_edge("generate_answer", "validate_output")
_builder.add_edge("validate_output", END)
CHAT_GRAPH = _builder.compile()


def run_chat(message: str, history: list[dict[str, str]], current_filters=None) -> dict:
    try:
        state = CHAT_GRAPH.invoke({
            "message": message,
            "history": history,
            "current_filters": current_filters,
        })
        return state["result"]
    except ChatUpstreamError:
        raise
    except Exception:
        raise
