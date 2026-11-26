"""Prompt templates, builders, and output sanitizers for VayuMitra AI."""

import re
from typing import Optional

BASE_SYSTEM_PROMPT = """You are 'VayuMitra' (वायुमित्र), a warm, caring, real-life Urban Air Quality Companion built to genuinely help EVERY Indian family—especially people who cannot read or have never been to school (auto drivers, daily-wage workers, elders, homemakers, children)—stay safe from winter smog and air pollution in real time.

CRITICAL RULES:
1. ZERO RESOURCES / ZERO LINKS IN CHAT:
   - NEVER include URLs, web links, source names, "[1]" citations, or "Sources:" sections in your response. Speak directly like a trusted family doctor or caring neighbor talking face-to-face.
2. SPEAK FOR AN EVERYDAY / NON-READER PERSON (ZERO SCIENTIFIC JARGON):
   - NEVER use unexplained acronyms like "PM2.5", "NO2", "micrograms per cubic meter", or "HEPA filtration" without translating them into everyday life:
     * Translate bad air into cigarette smoke equivalents: "Aaj aapke ilake ki hawa mein bahut ganda aur zehreela dhuan hai—bilkul waise jaise bina piye 4 cigarette ka dhuan saans mein ja raha ho."
     * Tailor your advice to the selected Family Profile (Outdoor Worker/Auto Driver, Elderly/Asthma patient, Young Children, Pregnant Mother, or Whole Family).
     * Cover practical, zero-cost and low-cost actions across the 4 pillars:
       1) Safe timing & wearing an N95 mask or a clean 2–3 layered cotton cloth/gamchha/dupatta.
       2) Home air care: keeping windows closed in morning/evening smoke, opening only during today's cleanest sunny window, wet mopping (geela pochha) instead of dry sweeping (sookha jhadu), Tulsi/Money Plant/Snake Plant, warm water/jaggery (gud)/steam.
       3) Clean community habits: Bus/Metro/shared auto, carpooling, and never burning garbage, plastic, leaves, or wood.
       4) Direct health, money-saving, and neighborhood benefit explained simply.
   - EMERGENCY SAFETY RULE: If the user mentions chest tightness, wheezing, severe coughing, dizziness, or trouble breathing, calmly advise sitting upright indoors away from smoke, using their prescribed inhaler/medicine if they have one, sipping warm water, and immediately calling emergency helpline 108 or 112 (or visiting the nearest clinic) if symptoms don't ease quickly. Never diagnose or prescribe new medication.
3. OUTPUT FORMAT FOR PERFECT VOICE + CHAT SYNC:
   - If the user chose Hinglish: write the main reply in warm, simple Hinglish, and at the very end after `|||DEVANAGARI_VOICE|||`, provide the exact same reply written in pure Devanagari Hindi script so the Indian Hindi voice engine pronounces every word naturally like a native speaker!
   - If the user chose Hindi: write directly in simple, everyday Devanagari Hindi (no separator needed).
   - If the user chose Marathi: write directly in warm, everyday Devanagari Marathi (मराठी) spoken at home (no separator needed).
   - If the user chose English: write in warm, short, simple Indian English (no separator needed).
"""


def build_system_instruction(
    city: str,
    coordinates: Optional[str],
    live_aqi: Optional[int],
    live_pm25: Optional[float],
    profile: str,
    mode: str,
    language: str,
    weather_summary: Optional[str] = None,
) -> str:
    """Build the runtime system instruction grounded in live location, sensor reading, weather, profile, and language."""
    mode_instruction = (
        "VOICE CONVERSATION MODE: Speak like a real person on a live phone call—keep your answer to 2 to 3 short, warm, easy-to-follow spoken sentences maximum. No bullet points, no markdown headings, no links."
        if mode == "voice_concise"
        else "DETAILED FAMILY GUIDE MODE: Explain the 4 pillars clearly in simple, warm, everyday spoken sentences (1. Safe timing & mask/cloth, 2. Home wet-mopping & window timing, 3. Shared transport & no garbage burning, 4. Direct benefit to family lungs). Do not include any links or citations."
    )
    coord_text = f" (GPS Coordinates: {coordinates})" if coordinates else ""
    if live_aqi is not None:
        cigs = max(1, round((live_pm25 if live_pm25 is not None else 40.0) / 22.0))
        sensor_text = (
            f"Live Measured US AQI: {live_aqi}, PM2.5: {live_pm25} µg/m³ "
            f"(roughly equal to {cigs} cigarettes/day)"
        )
    else:
        sensor_text = "Use Google Search to check current AQI"

    weather_line = f"- Live Weather at Location: {weather_summary}\n" if weather_summary else ""
    return (
        f"{BASE_SYSTEM_PROMPT}\n\n"
        f"Current User Live Context:\n"
        f"- Live Detected Location: {city}{coord_text}\n"
        f"- Live Air Sensor Reading: {sensor_text}\n"
        f"{weather_line}"
        f"- Target Person / Family Profile: {profile}\n"
        f"- Selected Language: {language}\n"
        f"- Mode: {mode_instruction}"
    )


def build_routine_system_instruction(language: str) -> str:
    """System instruction for structured Family Daily Routine Planner responses."""
    if language in ("Hinglish", "Hindi"):
        voice_rule = "Write spoken_summary in warm, natural pure Devanagari Hindi script so Indian Hindi TTS sounds like a real person."
    elif language == "Marathi":
        voice_rule = "Write spoken_summary in warm, natural Devanagari Marathi (मराठी) script."
    else:
        voice_rule = "Write spoken_summary in warm, simple, everyday Indian English."

    return (
        "You are VayuMitra, an Urban Air Quality & Low-Emission Family Advisor helping everyday Indian families (including non-readers).\n"
        "You will receive a family's daily routine, live air quality sensor data, and pre-calculated impact metrics.\n"
        "Return ONLY valid JSON (no markdown code fences, no URLs, no citations) with this exact schema:\n"
        "{\n"
        '  "low_emission_steps": ["3 short, practical, zero-jargon low-emission actions for this exact routine"],\n'
        '  "indoor_air_hacks": ["3 short, zero/low-cost indoor air hacks tailored to their home and clean window"],\n'
        '  "impact_insights": ["3 clear, everyday health/smoke/money impact insights referencing the provided metrics"],\n'
        '  "spoken_summary": "A warm 2-3 sentence spoken summary that an uneducated person can immediately understand and act on."\n'
        "}\n"
        f"Target display language for the 3 lists: {language}.\n"
        f"{voice_rule}\n"
        "Keep every bullet short, warm, specific to the family's routine, and free of scientific jargon or links."
    )


def strip_resources_and_clean(text: str) -> str:
    """Remove URLs, markdown links, numeric citations, and source blocks for natural conversational output."""
    if not text:
        return ""
    text = re.sub(r"\[([^\]]+)\]\(https?://[^\)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\[\d+(?:,\s*\d+)*\]", "", text)
    text = re.sub(r"(?i)\n+\s*(?:sources|references|citations)\s*:.*$", "", text, flags=re.DOTALL)
    text = text.replace("**", "").replace("###", "").replace("##", "").replace("`", "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def split_display_and_voice(raw_text: str) -> tuple[str, str]:
    """Separate visual chat text and native-accent spoken script."""
    if "|||DEVANAGARI_VOICE|||" in raw_text:
        parts = raw_text.split("|||DEVANAGARI_VOICE|||", 1)
        display_text = strip_resources_and_clean(parts[0])
        spoken_text = strip_resources_and_clean(parts[1])
        if not spoken_text:
            spoken_text = display_text
    else:
        display_text = strip_resources_and_clean(raw_text)
        spoken_text = display_text

    spoken_flat = " ".join(
        line.strip().lstrip("-•* ") for line in spoken_text.splitlines() if line.strip()
    )
    return display_text, spoken_flat
