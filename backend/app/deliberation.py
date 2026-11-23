"""Traceable participatory deliberation synthesizer (Google AI Studio Gemini + offline fallback)."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any

from backend.app.schemas import (
    CityKey,
    DeliberationResponse,
    DeliberationTheme,
    FeedbackRecord,
    NEBWeights,
)


def _validate_and_sanitize_themes(
    raw_themes: list[dict[str, Any]],
    valid_ids: set[int],
    valid_cells: set[str],
    fallback_weights: NEBWeights | None,
) -> list[DeliberationTheme]:
    """Enforce strict traceability: drop any citation not present in the database."""
    sanitized: list[DeliberationTheme] = []
    for item in raw_themes:
        cited_ids = [int(i) for i in item.get("cited_feedback_ids", []) if int(i) in valid_ids]
        cited_cells = [str(c) for c in item.get("cited_h3_indices", []) if str(c) in valid_cells]
        if not cited_ids or not cited_cells:
            continue
        sanitized.append(
            DeliberationTheme(
                theme_title=str(item.get("theme_title", "Community Priority Theme"))[:120],
                summary=str(item.get("summary", ""))[:500],
                cited_feedback_ids=sorted(set(cited_ids)),
                cited_h3_indices=sorted(set(cited_cells)),
                suggested_neb_weights=fallback_weights,
            )
        )
    return sanitized


def _deterministic_cluster(
    records: list[FeedbackRecord],
    stratified_weights: NEBWeights | None,
) -> list[DeliberationTheme]:
    """Group resident comments by priority_tag with 100% exact citation traceability."""
    by_tag: dict[str, list[FeedbackRecord]] = defaultdict(list)
    for rec in records:
        by_tag[rec.priority_tag].append(rec)

    themes: list[DeliberationTheme] = []
    for tag, items in sorted(by_tag.items(), key=lambda kv: len(kv[1]), reverse=True):
        fids = sorted({r.feedback_id for r in items})
        cells = sorted({r.h3_index for r in items})
        strata = sorted({r.stratum for r in items})
        sample_quotes = "; ".join(f"[#{r.feedback_id}] {r.rationale_text}" for r in items[:2])
        themes.append(
            DeliberationTheme(
                theme_title=f"{tag} ({len(items)} resident submissions)",
                summary=(
                    f"Raised across {len(cells)} H3 cell(s) by strata {', '.join(strata)}. "
                    f"Evidence: {sample_quotes}"
                ),
                cited_feedback_ids=fids,
                cited_h3_indices=cells,
                suggested_neb_weights=stratified_weights,
            )
        )
    return themes


def synthesize_deliberation(
    city: CityKey,
    records: list[FeedbackRecord],
    stratified_weights: NEBWeights | None,
    use_live_llm: bool = True,
) -> DeliberationResponse:
    """
    Synthesize citizen feedback into traceable planning trade-offs.
    Strictly advisory: never mutates active simulation weights.
    """
    if not records:
        return DeliberationResponse(
            city=city,
            provider="none",
            advisory_only=True,
            weights_mutated=False,
            themes=[],
            stratified_citizen_weights=None,
        )

    valid_ids = {r.feedback_id for r in records}
    valid_cells = {r.h3_index for r in records}
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if use_live_llm and api_key:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            payload = [
                {
                    "feedback_id": r.feedback_id,
                    "h3_index": r.h3_index,
                    "stratum": r.stratum,
                    "persona_role": r.persona_role,
                    "priority_tag": r.priority_tag,
                    "rationale_text": r.rationale_text,
                }
                for r in records
            ]
            prompt = (
                f"You are an impartial participatory urban-planning facilitator analyzing citizen heat-adaptation "
                f"feedback for {city}. Cluster these submissions into 2 to 4 concise planning trade-off themes. "
                f"STRICT RULE: Every theme MUST cite exact feedback_id integers and h3_index strings from the input JSON. "
                f"Do not invent IDs or change municipal weights.\n\n"
                f"Return JSON matching: {{\"themes\": [{{\"theme_title\": str, \"summary\": str, "
                f"\"cited_feedback_ids\": [int], \"cited_h3_indices\": [str]}}]}}\n\n"
                f"Submissions:\n{json.dumps(payload, ensure_ascii=False)}"
            )
            resp = client.models.generate_content(
                model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
            parsed = json.loads(resp.text or "{}")
            themes = _validate_and_sanitize_themes(
                parsed.get("themes", []), valid_ids, valid_cells, stratified_weights
            )
            if themes:
                return DeliberationResponse(
                    city=city,
                    provider=f"google-ai-studio:{os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')}",
                    advisory_only=True,
                    weights_mutated=False,
                    themes=themes,
                    stratified_citizen_weights=stratified_weights,
                )
        except Exception:
            # Graceful fallback to deterministic traceable synthesis if API quota/network fails
            pass

    themes = _deterministic_cluster(records, stratified_weights)
    return DeliberationResponse(
        city=city,
        provider="deterministic-traceable-fallback",
        advisory_only=True,
        weights_mutated=False,
        themes=themes,
        stratified_citizen_weights=stratified_weights,
    )