"""What the AI may offer to record for the person. These are only declarations: the model proposes a call,
nothing is written until the person confirms it (see chat_actions)."""

DECLARATIONS = [
    {
        "name": "add_body_measurement",
        "description": "Offer to record a body measurement (for example today's weight or waist). "
                       "Use only when the person clearly asks to save or log a measurement.",
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["weight", "waist", "body_fat_pct", "muscle_kg", "body_water_pct",
                                                    "bone_kg", "visceral_fat", "bmr_kcal", "skeletal_muscle_kg",
                                                    "skeletal_muscle_pct", "protein_pct", "body_age",
                                                    "hip", "fat_mass_kg", "lean_mass_kg", "active_cell_mass_kg", "active_cell_mass_pct", "total_body_water_kg", "extracellular_water_kg", "ecw_icw_ratio", "phase_angle", "specific_bmr"]},
                "value": {"type": "number", "description": "kg for weight, cm for waist, percent for *_pct"},
                "date": {"type": "string", "description": "YYYY-MM-DD; omit for today"},
            },
            "required": ["kind", "value"],
        },
    },
    {
        "name": "log_visit",
        "description": "Offer to add a doctor visit or a procedure to the person's medical history. "
                       "Use only when the person asks to log or save one.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "short title, e.g. 'Cardiologist'"},
                "record_type": {"type": "string", "enum": ["visit", "procedure"]},
                "date": {"type": "string", "description": "YYYY-MM-DD; omit for today"},
                "doctor_name": {"type": "string"},
                "clinic_name": {"type": "string"},
                "department": {"type": "string"},
                "reason": {"type": "string"},
                "details": {"type": "string", "description": "what was said or done"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "add_journal_entry",
        "description": "Offer to add a symptom or a note to the person's health journal. "
                       "Use only when the person asks to note or log it.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "category": {"type": "string", "enum": ["symptom", "note"]},
                "description": {"type": "string"},
                "severity_1_10": {"type": "integer"},
                "body_location": {"type": "string"},
                "entry_date": {"type": "string", "description": "YYYY-MM-DD; omit for today"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "log_supplement",
        "description": "Offer to log a dose just taken (supplement, medicine or stimulant such as coffee). "
                       "Use only when the person asks to log it.",
        "parameters": {
            "type": "object",
            "properties": {
                "item_name": {"type": "string"},
                "dosage": {"type": "number"},
                "unit": {"type": "string", "description": "mg, g, ml, cup ..."},
                "category": {"type": "string", "enum": ["supplement", "medication", "stimulant"]},
            },
            "required": ["item_name"],
        },
    },
]
