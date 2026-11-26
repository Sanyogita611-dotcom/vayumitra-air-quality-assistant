"""Comprehensive unit, security, localization, and HTTP integration tests for VayuMitra AI."""

import json
import os
import re
import subprocess
import threading
import unittest
import urllib.error
import urllib.request
from io import BytesIO
from unittest.mock import MagicMock, patch

from app import STATIC_DIR, create_server
from prompts import (
    BASE_SYSTEM_PROMPT,
    build_routine_system_instruction,
    build_system_instruction,
    split_display_and_voice,
    strip_resources_and_clean,
)
from services.environment_service import clear_environment_cache, parse_google_air_quality
from services.gemini_service import (
    MAX_IMAGE_BASE64_CHARS,
    MAX_MESSAGE_CHARS,
    _parse_routine_json,
    _sanitize_error_message,
    build_multimodal_input,
    call_interactions_rest_api,
    handle_chat_logic,
    handle_routine_logic,
)
from services.geocode_service import (
    _clean_district,
    _format_nominatim_result,
    clear_geocode_caches,
    forward_geocode_query,
    reverse_geocode_coordinates,
)
from services.impact_calculator import (
    build_deterministic_routine_plan,
    compute_routine_metrics,
    normalize_routine,
)


class TestPromptsAndSanitization(unittest.TestCase):
    def test_base_prompt_enforces_zero_jargon_and_emergency_safety(self):
        self.assertIn("ZERO RESOURCES / ZERO LINKS", BASE_SYSTEM_PROMPT)
        self.assertIn("108", BASE_SYSTEM_PROMPT)
        self.assertIn("112", BASE_SYSTEM_PROMPT)
        self.assertIn("|||DEVANAGARI_VOICE|||", BASE_SYSTEM_PROMPT)
        self.assertIn("Marathi", BASE_SYSTEM_PROMPT)

    def test_strip_resources_removes_urls_citations_markdown_and_sources(self):
        raw = (
            "### **Safe Advice**: Wear an N95 mask [1, 2]. "
            "See [CPCB](https://cpcb.nic.in) or http://example.com/aqi.\n\n\n"
            "Sources:\n- https://cpcb.nic.in"
        )
        cleaned = strip_resources_and_clean(raw)
        self.assertNotIn("https://", cleaned)
        self.assertNotIn("http://", cleaned)
        self.assertNotIn("[1, 2]", cleaned)
        self.assertNotIn("Sources:", cleaned)
        self.assertNotIn("**", cleaned)
        self.assertNotIn("###", cleaned)
        self.assertIn("Wear an N95 mask", cleaned)

    def test_strip_resources_handles_empty_string(self):
        self.assertEqual(strip_resources_and_clean(""), "")

    def test_split_display_and_voice_handles_dual_script_and_fallback(self):
        raw = "Aaj hawa kharab hai.\n- Mask pehnein.|||DEVANAGARI_VOICE|||आज हवा खराब है।\n- मास्क पहनें।"
        display, spoken = split_display_and_voice(raw)
        self.assertIn("Aaj hawa kharab hai.", display)
        self.assertEqual(spoken, "आज हवा खराब है। मास्क पहनें।")

        # Empty voice part falls back to cleaned display text
        d2, s2 = split_display_and_voice("Simple advice|||DEVANAGARI_VOICE|||   ")
        self.assertEqual(d2, "Simple advice")
        self.assertEqual(s2, "Simple advice")

    def test_build_system_instruction_modes_and_sensor_math(self):
        voice_prompt = build_system_instruction(
            city="Kasba Peth, Pune",
            coordinates="18.5204, 73.8567",
            live_aqi=185,
            live_pm25=88.0,
            profile="Elderly",
            mode="voice_concise",
            language="Marathi",
        )
        self.assertIn("Kasba Peth, Pune", voice_prompt)
        self.assertIn("185", voice_prompt)
        self.assertIn("4 cigarettes/day", voice_prompt)
        self.assertIn("VOICE CONVERSATION MODE", voice_prompt)
        self.assertIn("Marathi", voice_prompt)

        detailed_prompt = build_system_instruction(
            city="Delhi",
            coordinates=None,
            live_aqi=None,
            live_pm25=None,
            profile="Whole Family",
            mode="detailed_plan",
            language="English",
        )
        self.assertIn("DETAILED FAMILY GUIDE MODE", detailed_prompt)
        self.assertIn("Use Google Search", detailed_prompt)

    def test_build_routine_system_instruction_per_language(self):
        self.assertIn("Devanagari Hindi", build_routine_system_instruction("Hinglish"))
        self.assertIn("Devanagari Hindi", build_routine_system_instruction("Hindi"))
        self.assertIn("Marathi", build_routine_system_instruction("Marathi"))
        self.assertIn("Indian English", build_routine_system_instruction("English"))


class TestImpactCalculator(unittest.TestCase):
    def test_normalize_routine_clamps_out_of_bounds_and_invalid_values(self):
        norm = normalize_routine({
            "commute_mode": "spaceship",
            "commute_km_per_day": 999,
            "cooking_fuel": "nuclear",
            "outdoor_hours_peak": -5,
            "household_members": ["kids", "unknown"],
            "has_chimney_exhaust": 1,
            "burns_waste_or_incense": 0,
        })
        self.assertEqual(norm["commute_mode"], "petrol_scooter")
        self.assertEqual(norm["commute_km_per_day"], 200.0)
        self.assertEqual(norm["cooking_fuel"], "lpg")
        self.assertEqual(norm["outdoor_hours_peak"], 0.0)
        self.assertEqual(norm["household_members"], ["kids"])
        self.assertTrue(norm["has_chimney_exhaust"])
        self.assertFalse(norm["burns_waste_or_incense"])

    def test_normalize_routine_defaults_empty_members_to_adults(self):
        norm = normalize_routine({"household_members": []})
        self.assertEqual(norm["household_members"], ["adults"])

    def test_car_commuter_saves_more_than_walk_cycle(self):
        car = normalize_routine({"commute_mode": "petrol_car", "commute_km_per_day": 25})
        walk = normalize_routine({"commute_mode": "walk_cycle", "commute_km_per_day": 5})
        car_m = compute_routine_metrics(car, live_aqi=200, live_pm25=100.0)
        walk_m = compute_routine_metrics(walk, live_aqi=200, live_pm25=100.0)
        self.assertGreater(car_m["monthly_fuel_savings_inr"], 0)
        self.assertEqual(walk_m["monthly_fuel_savings_inr"], 0)
        self.assertGreater(car_m["weekly_co2_saved_kg"], walk_m["weekly_co2_saved_kg"])

    def test_biomass_and_waste_burning_increase_potential_impact(self):
        clean_home = normalize_routine({
            "commute_mode": "petrol_scooter",
            "commute_km_per_day": 15,
            "cooking_fuel": "induction",
            "has_chimney_exhaust": True,
            "burns_waste_or_incense": False,
        })
        smoky_home = normalize_routine({
            "commute_mode": "petrol_scooter",
            "commute_km_per_day": 15,
            "cooking_fuel": "biomass_wood",
            "has_chimney_exhaust": False,
            "burns_waste_or_incense": True,
            "outdoor_hours_peak": 5,
        })
        m_clean = compute_routine_metrics(clean_home, live_aqi=180, live_pm25=90.0)
        m_smoky = compute_routine_metrics(smoky_home, live_aqi=180, live_pm25=90.0)
        self.assertGreater(m_smoky["weekly_co2_saved_kg"], m_clean["weekly_co2_saved_kg"])
        self.assertGreater(m_smoky["exposure_reduction_pct"], m_clean["exposure_reduction_pct"])
        self.assertLessEqual(m_smoky["exposure_reduction_pct"], 68)

    def test_deterministic_plan_covers_all_four_languages_without_urls(self):
        routine = normalize_routine({
            "commute_mode": "petrol_car",
            "commute_km_per_day": 20,
            "cooking_fuel": "lpg",
            "has_chimney_exhaust": False,
            "burns_waste_or_incense": True,
            "outdoor_hours_peak": 2.5,
            "household_members": ["kids", "elderly", "pregnant", "outdoor_worker"],
        })
        metrics = compute_routine_metrics(routine, live_aqi=210, live_pm25=110.0)
        for lang in ("English", "Hindi", "Marathi", "Hinglish"):
            plan = build_deterministic_routine_plan(routine, metrics, "Pune", lang)
            self.assertEqual(len(plan["low_emission_steps"]), 3)
            self.assertEqual(len(plan["indoor_air_hacks"]), 3)
            self.assertEqual(len(plan["impact_insights"]), 3)
            self.assertTrue(plan["spoken_summary"])
            combined = " ".join(
                plan["low_emission_steps"] + plan["indoor_air_hacks"] + plan["impact_insights"] + [plan["spoken_summary"]]
            )
            self.assertNotIn("http://", combined)
            self.assertNotIn("https://", combined)


class TestSecurityAndGeminiService(unittest.TestCase):
    def test_sanitize_error_message_redacts_query_keys_and_google_keys(self):
        err = Exception("HTTPError 403 for https://example.com?key=AIzaSySecretKey1234567890&token=abc123")
        sanitized = _sanitize_error_message(err)
        self.assertNotIn("AIzaSySecretKey", sanitized)
        self.assertNotIn("abc123", sanitized)
        self.assertIn("[REDACTED]", sanitized)

    def test_rest_api_passes_key_in_header_never_in_url(self):
        fake_resp = MagicMock()
        fake_resp.__enter__.return_value.read.return_value = b'{"id":"int_1","output_text":"Hello"}'
        with patch("urllib.request.urlopen", return_value=fake_resp) as mock_open:
            data = call_interactions_rest_api(
                api_key="SUPER_SECRET_KEY",
                system_instruction="sys",
                input_payload="hello",
                previous_interaction_id="prev_1",
            )
            self.assertEqual(data["output_text"], "Hello")
            req_obj = mock_open.call_args[0][0]
            self.assertNotIn("SUPER_SECRET_KEY", req_obj.full_url)
            self.assertEqual(req_obj.get_header("X-goog-api-key"), "SUPER_SECRET_KEY")

    def test_multimodal_input_builder(self):
        self.assertEqual(build_multimodal_input("hi", None, None), "hi")
        mm = build_multimodal_input("check sky", "BASE64DATA", "image/jpeg")
        self.assertIsInstance(mm, list)
        self.assertEqual(len(mm), 2)
        self.assertEqual(mm[1]["type"], "image")
        self.assertEqual(mm[1]["mime_type"], "image/jpeg")

    def test_chat_validation_edge_cases(self):
        # Empty message & no image
        status, data = handle_chat_logic({"message": "   "})
        self.assertEqual(status, 400)

        # Oversized message
        status, data = handle_chat_logic({"message": "a" * (MAX_MESSAGE_CHARS + 1)})
        self.assertEqual(status, 400)
        self.assertIn("too long", data["detail"])

        # Unsupported image MIME
        for bad_mime in ("application/pdf", "image/svg+xml", "text/html"):
            status, data = handle_chat_logic({
                "message": "Check",
                "image_base64": "AAAA",
                "image_mime_type": bad_mime,
            })
            self.assertEqual(status, 400)
            self.assertIn("Unsupported image format", data["detail"])

        # Oversized base64 image
        status, data = handle_chat_logic({
            "message": "Check",
            "image_base64": "A" * (MAX_IMAGE_BASE64_CHARS + 10),
            "image_mime_type": "image/jpeg",
        })
        self.assertEqual(status, 400)

        # Non-numeric AQI/PM2.5 must not throw TypeError
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            status, data = handle_chat_logic({
                "message": "How is air?",
                "live_aqi": "bad-aqi",
                "live_pm25": "bad-pm",
            })
            self.assertEqual(status, 400)
            self.assertIn("GEMINI_API_KEY", data["detail"])

    def test_chat_success_with_mocked_gemini(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test_key"}, clear=False):
            with patch(
                "services.gemini_service._invoke_gemini",
                return_value=("Hawa theek hai [1].|||DEVANAGARI_VOICE|||हवा ठीक है।", "int_42"),
            ):
                status, data = handle_chat_logic({
                    "message": "Aaj hawa kaisi hai?",
                    "city": "Pune",
                    "live_aqi": 120,
                    "live_pm25": 45,
                    "language": "Hinglish",
                })
                self.assertEqual(status, 200)
                self.assertEqual(data["reply"], "Hawa theek hai .")
                self.assertEqual(data["spoken_summary"], "हवा ठीक है।")
                self.assertEqual(data["interaction_id"], "int_42")

    def test_parse_routine_json_valid_and_malformed(self):
        raw = """```json
        {
          "low_emission_steps": ["Take Metro https://metro.example.com"],
          "indoor_air_hacks": ["Wet mop daily [1]"],
          "impact_insights": ["Saves 10 kg CO2/week"],
          "spoken_summary": "Plan ready."
        }
        ```"""
        parsed = _parse_routine_json(raw)
        self.assertIsNotNone(parsed)
        self.assertNotIn("https://", parsed["low_emission_steps"][0])
        self.assertNotIn("[1]", parsed["indoor_air_hacks"][0])

        self.assertIsNone(_parse_routine_json("not valid json at all"))
        self.assertIsNone(_parse_routine_json('{"low_emission_steps": []}'))

    def test_routine_logic_falls_back_gracefully_when_gemini_errors(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test_key"}, clear=False):
            with patch("services.gemini_service._invoke_gemini", side_effect=RuntimeError("timeout")):
                status, data = handle_routine_logic({
                    "city": "Nagpur",
                    "live_aqi": 140,
                    "live_pm25": 58,
                    "language": "Marathi",
                    "routine": {"commute_mode": "petrol_scooter", "commute_km_per_day": 14},
                })
                self.assertEqual(status, 200)
                self.assertFalse(data["ai_enhanced"])
                self.assertEqual(len(data["low_emission_steps"]), 3)


class TestGeocodeService(unittest.TestCase):
    def setUp(self):
        clear_geocode_caches()

    def test_clean_district_and_nominatim_formatting(self):
        self.assertEqual(_clean_district("Pune District"), "Pune")
        self.assertEqual(_clean_district("Haveli Taluka"), "Haveli")

        res = _format_nominatim_result(
            {
                "address": {
                    "suburb": "Koramangala",
                    "city": "Bengaluru",
                    "state": "Karnataka",
                    "postcode": "560034",
                }
            },
            12.9352,
            77.6245,
        )
        self.assertEqual(res["display_name"], "Koramangala, Bengaluru")
        self.assertIn("560034", res["exact_address"])

    def test_reverse_geocode_uses_cache_on_repeat_calls(self):
        fake_payload = json.dumps({
            "address": {"neighbourhood": "Shivajinagar", "city": "Pune", "state": "Maharashtra"}
        }).encode("utf-8")

        def make_resp(*args, **kwargs):
            cm = MagicMock()
            cm.__enter__.return_value = BytesIO(fake_payload)
            return cm

        with patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": ""}, clear=False):
            with patch("urllib.request.urlopen", side_effect=make_resp) as mock_open:
                first = reverse_geocode_coordinates(18.5308, 73.8475)
                second = reverse_geocode_coordinates(18.5308, 73.8475)
                self.assertEqual(first["display_name"], "Shivajinagar, Pune")
                self.assertFalse(first["cached"])
                self.assertTrue(second["cached"])
                self.assertEqual(mock_open.call_count, 1)

    def test_reverse_geocode_returns_gps_fallback_when_all_providers_fail(self):
        with patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": ""}, clear=False):
            with patch("urllib.request.urlopen", side_effect=OSError("network down")):
                res = reverse_geocode_coordinates(18.52, 73.85)
                self.assertEqual(res["provider"], "GPS Coordinates")
                self.assertIn("18.5200", res["display_name"])

    def test_forward_geocode_empty_query_returns_none(self):
        self.assertIsNone(forward_geocode_query("   "))


class TestFrontendIntegrity(unittest.TestCase):
    def test_index_html_has_accessibility_and_low_literacy_controls(self):
        with open(os.path.join(STATIC_DIR, "index.html"), "r", encoding="utf-8") as f:
            html = f.read()
        for required_token in (
            'class="skip-link',
            'id="sr-announcer"',
            'aria-live="polite"',
            '<main id="main-content"',
            'id="mic-btn"',
            'id="emergency-btn"',
            'id="tile-mask"',
            'id="tile-window"',
            'id="tile-family"',
            'id="tile-home"',
            'id="routine-form"',
            "<fieldset",
            "<legend",
            'value="Marathi"',
            'value="Hindi"',
            'value="Hinglish"',
            'value="English"',
        ):
            self.assertIn(required_token, html)

    def test_i18n_js_has_100_percent_key_parity_across_all_languages(self):
        script = (
            "const fs=require('fs'), vm=require('vm');"
            "const ctx={window:{}};"
            "vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'), ctx);"
            "const d=ctx.window.VAYU_I18N;"
            "const langs=Object.keys(d);"
            "const base=Object.keys(d.Hinglish).sort();"
            "const missing={};"
            "for (const l of langs) {"
            "  const m=base.filter(k => !d[l][k]);"
            "  if (m.length) missing[l]=m;"
            "}"
            "console.log(JSON.stringify({langs, count: base.length, missing}));"
        )
        i18n_path = os.path.join(STATIC_DIR, "i18n.js")
        proc = subprocess.run(["node", "-e", script, i18n_path], capture_output=True, text=True, check=True)
        report = json.loads(proc.stdout)
        self.assertEqual(set(report["langs"]), {"Hinglish", "Hindi", "Marathi", "English"})
        self.assertGreater(report["count"], 50)
        self.assertEqual(report["missing"], {}, f"Missing i18n keys: {report['missing']}")


class TestHTTPServerIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_health_endpoint_and_security_headers(self):
        with urllib.request.urlopen(f"{self.base_url}/api/health", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")
            self.assertEqual(resp.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
            self.assertEqual(resp.headers.get("Cache-Control"), "no-store")
            body = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(body["status"], "ok")
            self.assertIn("has_env_api_key", body)

    def test_static_assets_served_and_sensitive_paths_blocked(self):
        expected_mimes = {
            "/": "text/html",
            "/styles.css": "text/css",
            "/i18n.js": "application/javascript",
            "/app.js": "application/javascript",
            "/favicon.ico": "image/svg+xml",
        }
        for asset, mime_prefix in expected_mimes.items():
            with urllib.request.urlopen(f"{self.base_url}{asset}", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                ctype = (resp.headers.get("Content-Type") or "").lower()
                self.assertTrue(
                    ctype.startswith(mime_prefix),
                    f"Expected {asset} Content-Type starting with {mime_prefix}, got {ctype}",
                )

        for blocked in (
            "/../app.py",
            "/.env",
            "/%2e%2e/app.py",
            "/.gitignore",
            "/../services/gemini_service.py",
            "/nonexistent-file.js",
        ):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"{self.base_url}{blocked}", timeout=5)
            self.assertEqual(ctx.exception.code, 404)

    def test_post_error_handling_for_malformed_json_and_unknown_routes(self):
        # Malformed JSON
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=b"{bad json",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)

        # JSON array instead of object
        req2 = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=b"[1, 2, 3]",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx2:
            urllib.request.urlopen(req2, timeout=5)
        self.assertEqual(ctx2.exception.code, 400)

        # Unknown POST endpoint
        req3 = urllib.request.Request(
            f"{self.base_url}/api/does-not-exist",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx3:
            urllib.request.urlopen(req3, timeout=5)
        self.assertEqual(ctx3.exception.code, 404)

    def test_routine_plan_endpoint_works_for_all_languages(self):
        for lang in ("Hinglish", "Hindi", "Marathi", "English"):
            payload = {
                "city": "Pune",
                "live_aqi": 170,
                "live_pm25": 82,
                "language": lang,
                "routine": {
                    "commute_mode": "petrol_scooter",
                    "commute_km_per_day": 16,
                    "cooking_fuel": "lpg",
                    "outdoor_hours_peak": 2,
                    "household_members": ["kids", "elderly"],
                },
            }
            req = urllib.request.Request(
                f"{self.base_url}/api/routine-plan",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
                with urllib.request.urlopen(req, timeout=5) as resp:
                    self.assertEqual(resp.status, 200)
                    data = json.loads(resp.read().decode("utf-8"))
                    self.assertEqual(data["language"], lang)
                    self.assertEqual(len(data["low_emission_steps"]), 3)
                    self.assertEqual(len(data["indoor_air_hacks"]), 3)
                    self.assertEqual(len(data["impact_insights"]), 3)
                    self.assertGreater(data["metrics"]["weekly_co2_saved_kg"], 0)

    def test_geocode_endpoints_validate_parameters(self):
        for bad_url in (
            "/api/reverse-geocode?lat=999&lon=77",
            "/api/reverse-geocode?lat=18&lon=-200",
            "/api/reverse-geocode?lat=abc&lon=77",
            "/api/environment?lat=999&lon=77",
            "/api/geocode?q=",
        ):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"{self.base_url}{bad_url}", timeout=5)
            self.assertEqual(ctx.exception.code, 400)

    def test_google_air_quality_parser_extracts_local_aqi_and_pollutants(self):
        clear_environment_cache()
        sample = {
            "indexes": [
                {"code": "uaqi", "displayName": "Universal AQI", "aqi": 62, "category": "Moderate", "dominantPollutant": "pm25"},
                {"code": "ind_cpcb", "displayName": "NAQI (India)", "aqi": 178, "category": "Moderate", "dominantPollutant": "pm25"},
            ],
            "pollutants": [
                {"code": "pm25", "concentration": {"value": 84.3}},
                {"code": "pm10", "concentration": {"value": 142.1}},
                {"code": "no2", "concentration": {"value": 24.5}},
            ],
        }
        parsed = parse_google_air_quality(sample)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["aqi"], 178)
        self.assertEqual(parsed["aqi_scale"], "NAQI (India)")
        self.assertEqual(parsed["pm25"], 84.3)
        self.assertEqual(parsed["pm10"], 142.1)
        self.assertEqual(parsed["provider"], "Google Maps Air Quality API")


if __name__ == "__main__":
    unittest.main()
