"""Gemini Interactions API service with secure header auth, input validation, and graceful fallback."""

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Optional

from prompts import (
    build_routine_system_instruction,
    build_system_instruction,
    split_display_and_voice,
    strip_resources_and_clean,
)
from services.impact_calculator import (
    build_deterministic_routine_plan,
    compute_routine_metrics,
    normalize_routine,
)

try:
    from google import genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

logger = logging.getLogger("vayumitra.gemini")

ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_LANGUAGES = {"Hinglish", "Hindi", "Marathi", "English"}
ALLOWED_MODES = {"voice_concise", "detailed_plan"}
MAX_MESSAGE_CHARS = 4000
MAX_IMAGE_BASE64_CHARS = 8 * 1024 * 1024  # ~6 MB raw image


def _get_model_name() -> str:
    return (os.environ.get("GEMINI_MODEL") or "gemini-4-hydrogen").strip()


def _get_agent_name() -> str:
    return (os.environ.get("GEMINI_AGENT") or "antigravity-preview-09-2026").strip()


def _sanitize_error_message(err: Exception) -> str:
    """Strip any accidental API keys or query strings before logging or returning an error."""
    raw = str(err) or type(err).__name__
    redacted = re.sub(r"(?i)(key|api_key|token)=([^&\s]+)", r"\1=[REDACTED]", raw)
    redacted = re.sub(r"AIza[0-9A-Za-z_\-]{10,}", "[REDACTED_KEY]", redacted)
    return redacted[:240]


def _parse_optional_int(val, min_val: int, max_val: int) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        parsed = int(round(float(val)))
        return max(min_val, min(max_val, parsed))
    except (TypeError, ValueError):
        return None


def _parse_optional_float(val, min_val: float, max_val: float) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        parsed = float(val)
        return max(min_val, min(max_val, round(parsed, 2)))
    except (TypeError, ValueError):
        return None


def build_multimodal_input(augmented_text: str, image_base64: Optional[str], image_mime_type: Optional[str]):
    if image_base64 and image_mime_type:
        return [
            {"type": "text", "text": augmented_text},
            {"type": "image", "data": image_base64, "mime_type": image_mime_type},
        ]
    return augmented_text


def call_interactions_rest_api(
    api_key: str,
    system_instruction: str,
    input_payload,
    previous_interaction_id: Optional[str] = None,
    use_tools: bool = True,
) -> dict:
    """Zero-dependency urllib fallback to Gemini Interactions API using secure header auth."""
    url = "https://generativelanguage.googleapis.com/v1beta/interactions"
    body = {
        "model": _get_model_name(),
        "system_instruction": system_instruction,
        "input": input_payload,
    }
    if use_tools:
        body["tools"] = [{"type": "google_search"}, {"type": "url_context"}]
    if previous_interaction_id:
        body["previous_interaction_id"] = previous_interaction_id

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_rest_text(data: dict) -> str:
    raw_reply = data.get("output_text", "")
    if raw_reply:
        return raw_reply
    texts = []
    for step in data.get("steps", []):
        if step.get("type") == "model_output":
            for part in step.get("content", []):
                if part.get("type") == "text" and part.get("text"):
                    texts.append(part["text"])
    return "\n".join(texts)


def _invoke_gemini(
    api_key: str,
    system_instruction: str,
    input_payload,
    previous_interaction_id: Optional[str] = None,
    use_agent: bool = True,
    use_tools: bool = True,
) -> tuple[str, Optional[str]]:
    """Call Gemini via google-genai SDK (agent -> direct model fallback) or REST fallback."""
    model_name = _get_model_name()
    agent_name = _get_agent_name()
    tools = [{"type": "google_search"}, {"type": "url_context"}] if use_tools else None

    if HAS_GENAI:
        client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        if use_agent:
            try:
                kwargs = {
                    "agent": agent_name,
                    "system_instruction": system_instruction,
                    "input": input_payload,
                    "environment": "remote",
                    "agent_config": {
                        "type": "antigravity",
                        "model": model_name,
                    },
                }
                if tools:
                    kwargs["tools"] = tools
                if previous_interaction_id:
                    kwargs["previous_interaction_id"] = previous_interaction_id

                interaction = client.interactions.create(**kwargs)
                return (
                    interaction.output_text or "Namaste, kripya dobara poochhein.",
                    getattr(interaction, "id", None),
                )
            except Exception as agent_err:
                logger.info("Managed agent unavailable (%s); falling back to %s", type(agent_err).__name__, model_name)

        fallback_kwargs = {
            "model": model_name,
            "system_instruction": system_instruction,
            "input": input_payload,
        }
        if tools:
            fallback_kwargs["tools"] = tools
        if previous_interaction_id:
            fallback_kwargs["previous_interaction_id"] = previous_interaction_id

        interaction = client.interactions.create(**fallback_kwargs)
        return (
            interaction.output_text or "Namaste, kripya dobara poochhein.",
            getattr(interaction, "id", None),
        )

    data = call_interactions_rest_api(
        api_key=api_key,
        system_instruction=system_instruction,
        input_payload=input_payload,
        previous_interaction_id=previous_interaction_id,
        use_tools=use_tools,
    )
    raw_reply = _extract_rest_text(data) or "Namaste, kripya dobara poochhein."
    return raw_reply, data.get("id")


def handle_chat_logic(payload: dict) -> tuple[int, dict]:
    """Validate chat payload and return conversational + spoken response."""
    raw_message = payload.get("message")
    message = str(raw_message).strip() if raw_message is not None else ""
    image_base64 = payload.get("image_base64")
    image_mime_type = payload.get("image_mime_type")

    if not message and not image_base64:
        return 400, {"detail": "Please provide a message or an image."}
    if len(message) > MAX_MESSAGE_CHARS:
        return 400, {"detail": f"Message is too long (max {MAX_MESSAGE_CHARS} characters)."}

    if image_base64:
        if not isinstance(image_base64, str) or len(image_base64) > MAX_IMAGE_BASE64_CHARS:
            return 400, {"detail": "Image payload is invalid or exceeds size limit."}
        if image_mime_type not in ALLOWED_IMAGE_MIMES:
            return 400, {"detail": "Unsupported image format. Please use JPEG, PNG, or WebP."}

    city = str(payload.get("city") or "Delhi").strip()[:160] or "Delhi"
    coordinates = str(payload.get("coordinates") or "").strip()[:64] or None
    live_aqi = _parse_optional_int(payload.get("live_aqi"), 0, 1000)
    live_pm25 = _parse_optional_float(payload.get("live_pm25"), 0.0, 2000.0)
    profile = str(payload.get("profile") or "Sabhi Parivar (General Family)").strip()[:160]
    mode = str(payload.get("mode") or "voice_concise").strip()
    if mode not in ALLOWED_MODES:
        mode = "voice_concise"
    language = str(payload.get("language") or "Hinglish").strip()
    if language not in ALLOWED_LANGUAGES:
        language = "Hinglish"

    previous_interaction_id = payload.get("previous_interaction_id")
    if previous_interaction_id is not None:
        previous_interaction_id = str(previous_interaction_id).strip()[:128] or None

    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return 400, {
            "detail": "Server GEMINI_API_KEY is not configured. See README.md to set it in .env or deployment secrets."
        }

    weather_summary = str(payload.get("weather_summary") or "").strip()[:160] or None
    system_instruction = build_system_instruction(
        city, coordinates, live_aqi, live_pm25, profile, mode, language, weather_summary=weather_summary
    )
    coord_info = f" (GPS: {coordinates})" if coordinates else ""
    aqi_info = f" | Live AQI: {live_aqi} (PM2.5: {live_pm25})" if live_aqi is not None else ""
    augmented_text = (
        f"[Location: {city}{coord_info}{aqi_info} | Profile: {profile} | Language: {language} | Mode: {mode}]\n"
        f"User says: {message}"
    )
    input_payload = build_multimodal_input(augmented_text, image_base64, image_mime_type)

    try:
        raw_reply, interaction_id = _invoke_gemini(
            api_key=api_key,
            system_instruction=system_instruction,
            input_payload=input_payload,
            previous_interaction_id=previous_interaction_id,
            use_agent=True,
            use_tools=True,
        )
        display_text, spoken_text = split_display_and_voice(raw_reply)
        return 200, {
            "reply": display_text,
            "spoken_summary": spoken_text,
            "interaction_id": interaction_id,
            "city": city,
        }
    except Exception as err:
        safe_err = _sanitize_error_message(err)
        logger.error("Gemini chat request failed: %s", safe_err)
        return 500, {"detail": f"Gemini API Error: {safe_err}"}


def _parse_routine_json(raw_text: str) -> Optional[dict]:
    """Parse structured JSON returned by Gemini for the Family Daily Routine Planner."""
    if not raw_text:
        return None
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None

    low_emission = parsed.get("low_emission_steps")
    indoor = parsed.get("indoor_air_hacks")
    insights = parsed.get("impact_insights")
    spoken = parsed.get("spoken_summary")

    if not (isinstance(low_emission, list) and isinstance(indoor, list) and isinstance(insights, list)):
        return None

    clean_low = [strip_resources_and_clean(str(x)) for x in low_emission if str(x).strip()][:4]
    clean_indoor = [strip_resources_and_clean(str(x)) for x in indoor if str(x).strip()][:4]
    clean_insights = [strip_resources_and_clean(str(x)) for x in insights if str(x).strip()][:4]
    clean_spoken = strip_resources_and_clean(str(spoken or ""))

    if not (clean_low and clean_indoor and clean_insights):
        return None

    return {
        "low_emission_steps": clean_low,
        "indoor_air_hacks": clean_indoor,
        "impact_insights": clean_insights,
        "spoken_summary": clean_spoken,
    }


def handle_routine_logic(payload: dict) -> tuple[int, dict]:
    """Generate a tailored Family Daily Routine plan with quantified CO2/PM2.5 impact insights."""
    city = str(payload.get("city") or "Delhi NCR").strip()[:160] or "Delhi NCR"
    live_aqi = _parse_optional_int(payload.get("live_aqi"), 0, 1000)
    live_pm25 = _parse_optional_float(payload.get("live_pm25"), 0.0, 2000.0)
    language = str(payload.get("language") or "Hinglish").strip()
    if language not in ALLOWED_LANGUAGES:
        language = "Hinglish"

    routine = normalize_routine(payload.get("routine") if isinstance(payload.get("routine"), dict) else payload)
    metrics = compute_routine_metrics(routine, live_aqi, live_pm25)
    fallback_plan = build_deterministic_routine_plan(routine, metrics, city, language)

    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    ai_enhanced = False
    plan = fallback_plan

    if api_key:
        system_instruction = build_routine_system_instruction(language)
        routine_prompt = (
            f"City: {city}\n"
            f"Live US AQI: {metrics['live_aqi']} | PM2.5: {metrics['live_pm25']} µg/m³\n"
            f"Family Daily Routine: {json.dumps(routine, ensure_ascii=False)}\n"
            f"Pre-calculated Impact Metrics: {json.dumps(metrics, ensure_ascii=False)}\n"
            "Generate the tailored JSON plan now."
        )
        try:
            raw_reply, _ = _invoke_gemini(
                api_key=api_key,
                system_instruction=system_instruction,
                input_payload=routine_prompt,
                use_agent=False,
                use_tools=False,
            )
            parsed = _parse_routine_json(raw_reply)
            if parsed:
                if not parsed["spoken_summary"]:
                    parsed["spoken_summary"] = fallback_plan["spoken_summary"]
                plan = parsed
                ai_enhanced = True
        except Exception as err:
            logger.warning("Gemini routine personalization fell back to deterministic engine: %s", _sanitize_error_message(err))

    return 200, {
        "city": city,
        "language": language,
        "ai_enhanced": ai_enhanced,
        "routine": routine,
        "metrics": metrics,
        "low_emission_steps": plan["low_emission_steps"],
        "indoor_air_hacks": plan["indoor_air_hacks"],
        "impact_insights": plan["impact_insights"],
        "spoken_summary": plan["spoken_summary"],
    }
