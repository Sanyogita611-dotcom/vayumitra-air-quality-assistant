"""Deterministic emissions, indoor air, and health impact calculator for Family Daily Routines."""

from typing import Optional

# Average tailpipe CO2 emission factors (kg CO2 per passenger-km) for urban Indian commutes
COMMUTE_CO2_KG_PER_KM = {
    "petrol_car": 0.18,
    "petrol_scooter": 0.075,
    "auto_cab": 0.11,
    "bus_metro": 0.03,
    "walk_cycle": 0.0,
}

# Approximate direct out-of-pocket fuel/fare cost per km (INR)
COMMUTE_COST_INR_PER_KM = {
    "petrol_car": 9.5,
    "petrol_scooter": 3.2,
    "auto_cab": 11.0,
    "bus_metro": 2.2,
    "walk_cycle": 0.0,
}

VALID_COMMUTE_MODES = set(COMMUTE_CO2_KG_PER_KM.keys())
VALID_COOKING_FUELS = {"lpg", "induction", "biomass_wood"}
VALID_MEMBERS = {"kids", "elderly", "outdoor_worker", "pregnant", "adults"}


def normalize_routine(raw: dict) -> dict:
    """Validate and clamp family daily routine fields into safe defaults."""
    commute_mode = str(raw.get("commute_mode") or "petrol_scooter").strip().lower()
    if commute_mode not in VALID_COMMUTE_MODES:
        commute_mode = "petrol_scooter"

    try:
        commute_km = float(raw.get("commute_km_per_day", 14))
    except (TypeError, ValueError):
        commute_km = 14.0
    commute_km = max(0.0, min(200.0, round(commute_km, 1)))

    cooking_fuel = str(raw.get("cooking_fuel") or "lpg").strip().lower()
    if cooking_fuel not in VALID_COOKING_FUELS:
        cooking_fuel = "lpg"

    has_exhaust = bool(raw.get("has_chimney_exhaust", False))
    burns_waste_or_incense = bool(raw.get("burns_waste_or_incense", False))

    try:
        outdoor_hours = float(raw.get("outdoor_hours_peak", 2.0))
    except (TypeError, ValueError):
        outdoor_hours = 2.0
    outdoor_hours = max(0.0, min(14.0, round(outdoor_hours, 1)))

    raw_members = raw.get("household_members")
    if isinstance(raw_members, list):
        members = [str(m).strip().lower() for m in raw_members if str(m).strip().lower() in VALID_MEMBERS]
    else:
        members = []
    if not members:
        members = ["adults"]

    clean_window = str(raw.get("clean_window") or "1 PM–3 PM").strip()[:48]
    notes = str(raw.get("notes") or "").strip()[:300]

    return {
        "commute_mode": commute_mode,
        "commute_km_per_day": commute_km,
        "cooking_fuel": cooking_fuel,
        "has_chimney_exhaust": has_exhaust,
        "burns_waste_or_incense": burns_waste_or_incense,
        "outdoor_hours_peak": outdoor_hours,
        "household_members": members,
        "clean_window": clean_window,
        "notes": notes,
    }


def compute_routine_metrics(
    routine: dict,
    live_aqi: Optional[int],
    live_pm25: Optional[float],
) -> dict:
    """Compute realistic weekly CO2 savings, monthly INR savings, and PM2.5 exposure reduction."""
    mode = routine["commute_mode"]
    km_day = routine["commute_km_per_day"]
    cooking = routine["cooking_fuel"]
    has_exhaust = routine["has_chimney_exhaust"]
    burns_waste = routine["burns_waste_or_incense"]
    outdoor_hrs = routine["outdoor_hours_peak"]

    # Commute shift: switch 3 of 6 commute days/week to Bus/Metro/Carpool (or maintain if already green)
    days_shifted = 3.0 if km_day > 0 else 0.0
    if mode in ("petrol_car", "petrol_scooter", "auto_cab"):
        delta_co2_km = max(0.0, COMMUTE_CO2_KG_PER_KM[mode] - COMMUTE_CO2_KG_PER_KM["bus_metro"])
        commute_co2_saved_week = km_day * days_shifted * delta_co2_km
        delta_inr_km = max(0.0, COMMUTE_COST_INR_PER_KM[mode] - COMMUTE_COST_INR_PER_KM["bus_metro"])
        monthly_inr_saved = round(km_day * days_shifted * 4.3 * delta_inr_km)
    else:
        # Already low-emission commute: recognize avoided car emissions (~3 days/week)
        commute_co2_saved_week = km_day * 3.0 * (COMMUTE_CO2_KG_PER_KM["petrol_car"] - COMMUTE_CO2_KG_PER_KM[mode])
        monthly_inr_saved = 0

    # Household emission reductions (stopping trash/leaf/incense smoke + cleaner cooking)
    home_co2_saved_week = 0.0
    if cooking == "biomass_wood":
        home_co2_saved_week += 8.5
    if burns_waste:
        home_co2_saved_week += 3.2
    # Basic appliance & zero-idling habits
    home_co2_saved_week += 1.2

    weekly_co2_saved_kg = round(commute_co2_saved_week + home_co2_saved_week, 1)
    annual_trees_equivalent = max(1, round((weekly_co2_saved_kg * 52) / 21.0))

    # PM2.5 cigarette-equivalent exposure and achievable reduction
    effective_pm25 = live_pm25 if (live_pm25 is not None and live_pm25 > 0) else 66.0
    effective_aqi = live_aqi if (live_aqi is not None and live_aqi >= 0) else 155

    exposure_factor = 1.0 + min(0.6, outdoor_hrs * 0.08)
    if cooking == "biomass_wood":
        exposure_factor += 0.45
    elif not has_exhaust:
        exposure_factor += 0.15
    if burns_waste:
        exposure_factor += 0.15

    baseline_cigs = max(1.0, round((effective_pm25 * exposure_factor) / 22.0, 1))

    # Realistic combined exposure reduction from mask + clean-window timing + wet mop + exhaust/smoke cut
    reduction_pct = 38
    if outdoor_hrs >= 1.5:
        reduction_pct += 12
    if not has_exhaust or cooking == "biomass_wood":
        reduction_pct += 10
    if burns_waste:
        reduction_pct += 6
    reduction_pct = min(68, reduction_pct)

    reduced_cigs = max(0.4, round(baseline_cigs * (1.0 - reduction_pct / 100.0), 1))

    return {
        "live_aqi": effective_aqi,
        "live_pm25": round(effective_pm25, 1),
        "weekly_co2_saved_kg": weekly_co2_saved_kg,
        "monthly_fuel_savings_inr": monthly_inr_saved,
        "annual_trees_equivalent": annual_trees_equivalent,
        "baseline_cigs_per_day": baseline_cigs,
        "reduced_cigs_per_day": reduced_cigs,
        "exposure_reduction_pct": reduction_pct,
    }


def build_deterministic_routine_plan(
    routine: dict,
    metrics: dict,
    city: str,
    language: str,
) -> dict:
    """Build a tailored, language-aware 3-pillar plan (used directly offline or as fallback for Gemini)."""
    mode = routine["commute_mode"]
    km = routine["commute_km_per_day"]
    cooking = routine["cooking_fuel"]
    has_exhaust = routine["has_chimney_exhaust"]
    burns_waste = routine["burns_waste_or_incense"]
    outdoor_hrs = routine["outdoor_hours_peak"]
    members = routine["household_members"]
    win = routine["clean_window"]

    co2_wk = metrics["weekly_co2_saved_kg"]
    inr_mo = metrics["monthly_fuel_savings_inr"]
    red_pct = metrics["exposure_reduction_pct"]
    base_c = metrics["baseline_cigs_per_day"]
    red_c = metrics["reduced_cigs_per_day"]
    aqi = metrics["live_aqi"]

    vulnerable_en = []
    vulnerable_hi = []
    if "kids" in members:
        vulnerable_en.append("young children")
        vulnerable_hi.append("बच्चों")
    if "elderly" in members:
        vulnerable_en.append("seniors")
        vulnerable_hi.append("बुजुर्गों")
    if "pregnant" in members:
        vulnerable_en.append("expectant mother")
        vulnerable_hi.append("गर्भवती माँ")
    if "outdoor_worker" in members:
        vulnerable_en.append("outdoor workers")
        vulnerable_hi.append("बाहर काम करने वालों")
    group_en = ", ".join(vulnerable_en) if vulnerable_en else "your whole family"
    group_hi = ", ".join(vulnerable_hi) if vulnerable_hi else "पूरे परिवार"

    if language == "English":
        low_emission = []
        if mode == "petrol_car":
            low_emission.append(
                f"Shift 3 days/week of your {km:.0f} km car commute to Metro, Bus, or office carpool—and switch off the engine at red lights longer than 30 seconds."
            )
        elif mode == "petrol_scooter":
            low_emission.append(
                f"Replace 3 days/week of your {km:.0f} km two-wheeler ride with Metro/Bus or shared e-rickshaw, and keep tires inflated + PUC updated to cut exhaust smoke."
            )
        elif mode == "auto_cab":
            low_emission.append(
                f"Choose CNG/electric shared autos or Metro for half of your {km:.0f} km trips, and bundle errands into one single afternoon outing."
            )
        else:
            low_emission.append(
                f"Great job already using low-emission travel ({km:.0f} km/day)! Encourage carpooling for family outings and combine nearby errands on foot."
            )

        if cooking == "biomass_wood":
            low_emission.append(
                "Transition away from wood/coal chulha to LPG or induction for daily meals to eliminate heavy indoor and neighborhood black smoke."
            )
        elif cooking == "lpg":
            low_emission.append(
                "Use pressure cookers and covered lids on LPG stoves—this cuts gas burn by ~25% and reduces indoor nitrogen dioxide."
            )
        else:
            low_emission.append(
                "Keep using clean induction cooking and run heavy appliances off-peak when possible to keep household emissions minimal."
            )

        if burns_waste:
            low_emission.append(
                "Stop burning dry leaves, trash, or heavy indoor incense/mosquito coils—compost garden waste and use window mesh nets instead."
            )
        else:
            low_emission.append(
                "Never burn winter waste or wood outdoors; report local open garbage burning to your municipal helpline to protect neighborhood air."
            )

        indoor_hacks = [
            f"Ventilate only during {city}'s cleanest window today ({win}) for 15–20 minutes; keep doors and windows tightly shut during early morning and evening peak smog.",
            "Switch from dry sweeping to daily wet mopping (geela pochha) and wipe sills with a damp cloth so fine PM2.5 dust cannot re-enter the air.",
            (
                "Run your kitchen exhaust/chimney during cooking and for 10 minutes afterward, and place Tulsi, Snake Plant, or Money Plant near sunny sills."
                if has_exhaust
                else "Open the kitchen window/exhaust fan (or point a table fan outward) while cooking to push frying fumes out immediately, and keep Tulsi/Snake Plant indoors."
            ),
        ]

        insights = [
            f"Air Exposure Drop: Following this routine cuts daily smoke exposure for {group_en} by ~{red_pct}% (from ~{base_c} to ~{red_c} cigarette-equivalents/day at AQI {aqi}).",
            f"Carbon Footprint Cut: Saves ~{co2_wk} kg CO₂ every week—equal to planting ~{metrics['annual_trees_equivalent']} trees per year.",
            (
                f"Household Savings: Shifting 3 commute days/week saves roughly ₹{inr_mo:,}/month in fuel while lowering cough and asthma flare-ups."
                if inr_mo > 0
                else f"Health & Time Shield: Shifting {outdoor_hrs:.1f} hrs of peak outdoor exposure and keeping indoor air dust-free directly protects {group_en}'s lungs."
            ),
        ]
        spoken = (
            f"Here is your tailored plan for {city}. By following these low-emission steps and ventilating only during {win}, "
            f"your family can cut daily smoke exposure by about {red_pct} percent and save roughly {co2_wk} kilograms of carbon emissions every week."
        )
        return {
            "low_emission_steps": low_emission,
            "indoor_air_hacks": indoor_hacks,
            "impact_insights": insights,
            "spoken_summary": spoken,
        }

    if language == "Hindi":
        low_emission = []
        if mode in ("petrol_car", "petrol_scooter", "auto_cab"):
            low_emission.append(
                f"अपनी रोज़ की {km:.0f} किमी यात्रा में से हफ्ते में 3 दिन मेट्रो, बस, साझा ई-रिक्शा या कारपूल चुनें और 30 सेकंड से ज़्यादा लाल बत्ती पर इंजन बंद रखें।"
            )
        else:
            low_emission.append(
                f"आप पहले से ही साफ सफर ({km:.0f} किमी/दिन) कर रहे हैं! पास के बाज़ार के काम एक ही ट्रिप में निपटाएँ ताकि सड़कों पर धुआँ कम हो।"
            )

        if cooking == "biomass_wood":
            low_emission.append(
                "लकड़ी या कोयले के चूल्हे की जगह एलपीजी या इंडक्शन अपनाएँ—इससे रसोई और मोहल्ले का काला धुआँ तुरंत कम होगा।"
            )
        else:
            low_emission.append(
                "खाना बनाते समय प्रेशर कुकर और ढक्कन का इस्तेमाल करें—इससे गैस कम जलती है और रसोई में धुआँ नहीं भरता।"
            )

        if burns_waste:
            low_emission.append(
                "सूखे पत्ते, कचरा, प्लास्टिक या ज़्यादा अगरबत्ती/मच्छर कॉइल बिल्कुल न जलाएँ; मच्छर से बचाव के लिए जाली का इस्तेमाल करें।"
            )
        else:
            low_emission.append(
                "सर्दियों में कभी भी कचरा या लकड़ी न जलाएँ और आस-पास खुले में कचरा जलते देखें तो रोकें।"
            )

        indoor_hacks = [
            f"{city} में आज सबसे साफ समय ({win}) के दौरान ही 15–20 मिनट खिड़की खोलें; सुबह-शाम की धुंध में खिड़की-दरवाज़े बंद रखें।",
            "घर में सूखा झाड़ू लगाने की जगह रोज़ गीला पोछा लगाएँ ताकि बारीक धूल हवा में दोबारा न उड़े।",
            (
                "खाना बनाते समय और उसके 10 मिनट बाद तक चिमनी/एग्जॉस्ट चलाएँ, और कमरे में तुलसी या स्नेक प्लांट रखें।"
                if has_exhaust
                else "खाना बनाते समय रसोई की खिड़की की तरफ पंखा बाहर की ओर चलाकर धुआँ निकालें, और घर में तुलसी व मनी प्लांट रखें।"
            ),
        ]

        insights = [
            f"फेफड़ों की सुरक्षा: इस रूटीन से {group_hi} के लिए धुएँ का नुकसान लगभग {red_pct}% कम होगा (~{base_c} से घटकर ~{red_c} सिगरेट बराबर/दिन, AQI {aqi})।",
            f"धुआँ और कार्बन में कमी: हर हफ्ते लगभग {co2_wk} किलो CO₂ बचेगा—जो साल भर में ~{metrics['annual_trees_equivalent']} पेड़ लगाने के बराबर है।",
            (
                f"बचत और सेहत: हफ्ते में 3 दिन बस/मेट्रो चुनने से महीने में लगभग ₹{inr_mo:,} ईंधन बचेगा और खाँसी-दमा से बचाव होगा।"
                if inr_mo > 0
                else f"सांस की सेहत: बाहर के पीक समय ({outdoor_hrs:.1f} घंटे) में मास्क/कपड़ा पहनने और गीले पोछे से {group_hi} को तुरंत राहत मिलेगी।"
            ),
        ]
        spoken = (
            f"{city} के लिए आपके परिवार का प्लान तैयार है। इन आसान कदमों और {win} के साफ समय में खिड़की खोलने से "
            f"आपके परिवार के धुएँ का नुकसान लगभग {red_pct} प्रतिशत कम होगा और हर हफ्ते करीब {co2_wk} किलो कार्बन धुआँ बचेगा।"
        )
        return {
            "low_emission_steps": low_emission,
            "indoor_air_hacks": indoor_hacks,
            "impact_insights": insights,
            "spoken_summary": spoken,
        }

    if language == "Marathi":
        low_emission = []
        if mode in ("petrol_car", "petrol_scooter", "auto_cab"):
            low_emission.append(
                f"तुमच्या रोजच्या {km:.0f} किमी प्रवासापैकी आठवड्यातून 3 दिवस बस, मेट्रो, शेअर रिक्षा किंवा कारपूल वापरा आणि लाल सिग्नलला गाडी बंद ठेवा."
            )
        else:
            low_emission.append(
                f"छान! तुम्ही आधीच स्वच्छ प्रवास ({km:.0f} किमी/दिवस) करता. जवळची कामे एकाच फेरीत उरका म्हणजे रस्त्यावरचा धूर कमी होईल."
            )

        if cooking == "biomass_wood":
            low_emission.append(
                "लाकूड किंवा कोळशाच्या चुलीऐवजी एलपीजी गॅस किंवा इंडक्शन वापरा—यामुळे स्वयंपाकघरातील आणि परिसरातील काळा धूर लगेच कमी होईल."
            )
        else:
            low_emission.append(
                "स्वयंपाक करताना प्रेशर कुकर आणि झाकण वापरा—गॅस वाचेल आणि घरात धूर साचणार नाही."
            )

        if burns_waste:
            low_emission.append(
                "सुका पालापाचोळा, कचरा, प्लास्टिक किंवा जास्त अगरबत्ती/मच्छर कॉईल जाळू नका; डासांसाठी खिडकीला जाळी लावा."
            )
        else:
            low_emission.append(
                "हिवाळ्यात कचरा किंवा लाकूड कधीही जाळू नका आणि परिसरात उघड्यावर कचरा जाळणे थांबवा."
            )

        indoor_hacks = [
            f"{city} मध्ये आजच्या सर्वात स्वच्छ वेळेत ({win}) फक्त 15–20 मिनिटे खिडक्या उघडा; सकाळ-संध्याकाळच्या धुरात खिडक्या बंद ठेवा.",
            "घरात कोरड्या झाडूऐवजी रोज ओल्या फडक्याने (ओला पोछा) फरशी पुसा म्हणजे बारीक धूळ पुन्हा हवेत उडणार नाही.",
            (
                "स्वयंपाक करताना आणि त्यानंतर 10 मिनिटे एक्झॉस्ट/चिमणी चालू ठेवा, आणि घरात तुळस किंवा मनी प्लांट ठेवा."
                if has_exhaust
                else "स्वयंपाक करताना स्वयंपाकघराची खिडकी उघडी ठेवून पंखा बाहेरच्या बाजूने लावा आणि घरात तुळस किंवा स्नेक प्लांट ठेवा."
            ),
        ]

        insights = [
            f"फुफ्फुसांचे रक्षण: या सवयींमुळे कुटुंबाचा धुराचा त्रास सुमारे {red_pct}% कमी होईल (~{base_c} वरून ~{red_c} सिगारेट बरोबर/दिवस, AQI {aqi}).",
            f"प्रदूषणात घट: दर आठवड्याला ~{co2_wk} किलो धूर (CO₂) वाचेल—वर्षभरात ~{metrics['annual_trees_equivalent']} झाडे लावल्यासारखे!",
            (
                f"पैशांची बचत: आठवड्यातून 3 दिवस बस/मेट्रो वापरल्यास महिन्याला ~₹{inr_mo:,} इंधन वाचेल आणि खोकला-दमा कमी राहील."
                if inr_mo > 0
                else f"आरोग्याचे कवच: बाहेरच्या धुराच्या वेळेत ({outdoor_hrs:.1f} तास) मास्क किंवा स्वच्छ सुती कापड बांधल्यास श्वासाचे आजार टळतील."
            ),
        ]
        spoken_mr = (
            f"{city} साठी तुमच्या कुटुंबाचा सोपा आराखडा तयार आहे. हे छोटे उपाय केल्यास आणि फक्त {win} दरम्यान खिडक्या उघडल्यास "
            f"धुराचा त्रास सुमारे {red_pct} टक्के कमी होईल आणि दर आठवड्याला जवळपास {co2_wk} किलो धूर वाचेल."
        )
        return {
            "low_emission_steps": low_emission,
            "indoor_air_hacks": indoor_hacks,
            "impact_insights": insights,
            "spoken_summary": spoken_mr,
        }

    # Default: Hinglish display + Devanagari spoken_summary
    low_emission = []
    if mode in ("petrol_car", "petrol_scooter", "auto_cab"):
        low_emission.append(
            f"Apni roz ki {km:.0f} km yatra mein se hafte mein 3 din Metro, Bus, sajha e-rickshaw ya carpool chunein, aur 30 sec se zyada red light par engine band rakhein."
        )
    else:
        low_emission.append(
            f"Bahut badhiya! Aap pehle se clean travel ({km:.0f} km/day) kar rahe hain—paas ke kaam ek hi trip mein niptayein."
        )

    if cooking == "biomass_wood":
        low_emission.append(
            "Lakdi ya koyle ke chulhe ki jagah LPG ya induction apnayein—isse rasoi aur mohalle ka kala dhuan turant kam hoga."
        )
    else:
        low_emission.append(
            "Khana banate waqt pressure cooker aur dhakkan use karein—gas ~25% bachegi aur kitchen mein dhuan nahi bharega."
        )

    if burns_waste:
        low_emission.append(
            "Sookhe patte, kachra, plastic ya tez agarbatti/mosquito coil bilkul na jalayein; macchar ke liye jaali (net) lagayein."
        )
    else:
        low_emission.append(
            "Thand mein kachra ya lakdi bilkul na jalayein aur mohalle mein khule mein kachra jalane se rokein."
        )

    indoor_hacks = [
        f"{city} mein aaj sabse saaf samay ({win}) mein hi 15–20 min khidki kholein; subah-shaam dhundh mein khidki-darwaze band rakhein.",
        "Ghar mein sookha jhadu lagane ki jagah roz geela pochha (wet mop) lagayein taaki bareek dhool dobara hawa mein na ude.",
        (
            "Khana banate waqt aur 10 min baad tak chimney/exhaust chalayein, aur khidki ke paas Tulsi ya Snake Plant rakhein."
            if has_exhaust
            else "Khana banate waqt kitchen window/exhaust fan bahar ki taraf chalakar dhuan nikaalein, aur ghar mein Tulsi/Money Plant rakhein."
        ),
    ]

    insights = [
        f"Fefdon Ki Suraksha: Is routine se {group_en} ka roz ka dhuan nuksan ~{red_pct}% kam hoga (~{base_c} se ghatkar ~{red_c} cigarette barabar/day, AQI {aqi}).",
        f"Carbon Footprint Kam: Har hafte ~{co2_wk} kg CO₂ bachega—saal mein ~{metrics['annual_trees_equivalent']} ped lagane ke barabar!",
        (
            f"Bachat Aur Sehat: Hafte mein 3 din Bus/Metro lene se mahine mein ~₹{inr_mo:,} fuel bachega aur khansi-dama ka khatra ghat jayega."
            if inr_mo > 0
            else f"Saans Ki Raksha: Peak smog ({outdoor_hrs:.1f} hrs) mein N95 mask/3-layer suti kapda aur geela pochha aapke parivar ko surakshit rakhega."
        ),
    ]
    spoken_devanagari = (
        f"{city} के लिए आपके परिवार का प्लान तैयार है। इन आसान कदमों और {win} के साफ समय में खिड़की खोलने से "
        f"आपके परिवार के धुएँ का नुकसान लगभग {red_pct} प्रतिशत कम होगा और हर हफ्ते करीब {co2_wk} किलो कार्बन धुआँ बचेगा।"
    )
    return {
        "low_emission_steps": low_emission,
        "indoor_air_hacks": indoor_hacks,
        "impact_insights": insights,
        "spoken_summary": spoken_devanagari,
    }
