import importlib.util
import sys
from pathlib import Path


def load_ai_module():
    mod_path = Path("theorycraft-form/ai-form.py").resolve()
    spec = importlib.util.spec_from_file_location("theorycraft_ai_form", str(mod_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["theorycraft_ai_form"] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_llm_normalization_maps_city_variants_to_allowed_options():
    mod = load_ai_module()
    fields_schema = {
        "fields": [
            {
                "name": "In what cities are you available to work?",
                "role": "listbox",
                "options": [
                    "Amsterdam",
                    "New York",
                    "San Jose (Campbell)",
                    "Seattle",
                ],
            }
        ]
    }
    # Simulate an LLM that answered with text not exactly matching options
    llm_yaml = {
        "fields": [
            {
                "name": "In what cities are you available to work?",
                "role": "listbox",
                "value": "New York City",
            }
        ]
    }
    out = mod.validate_and_normalize(fields_schema, llm_yaml)
    assert out and out[0]["value"] == "New York"

    # And Mountain View should normalize to San Jose (Campbell)
    llm_yaml_mv = {
        "fields": [
            {
                "name": "In what cities are you available to work?",
                "role": "listbox",
                "value": "Mountain View",
            }
        ]
    }
    out2 = mod.validate_and_normalize(fields_schema, llm_yaml_mv)
    assert out2 and out2[0]["value"] == "San Jose (Campbell)"
