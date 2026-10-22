import base64
import json
import requests
from typing import List, Dict

OLLAMA_BASE_URL = "http://localhost:11434/api/generate"

def check_ollama_health() -> Dict:
    """Checks if local Ollama server is running and lists installed models."""
    try:
        res = requests.get("http://localhost:11434/api/tags", timeout=3)
        if res.status_code == 200:
            models = [m["name"] for m in res.json().get("models", [])]
            return {"online": True, "models": models}
    except Exception:
        pass
    return {"online": False, "models": []}

def auto_tag_image(image_bytes: bytes, vision_model: str = "moondream") -> Dict:
    """Uses a local vision model (moondream) to auto-detect clothing attributes."""
    b64_img = base64.b64encode(image_bytes).decode("utf-8")
    prompt = (
        "Analyze this clothing item. Reply ONLY with a valid JSON object containing these exact keys: "
        '{"name": "short descriptive title", "category": "Top, Bottom, Layer / Jacket, Footwear, or Accessory", '
        '"color": "primary color", "style_vibe": "Casual, Smart Casual, Streetwear, or Athletic"}'
    )
    payload = {
        "model": vision_model,
        "prompt": prompt,
        "images": [b64_img],
        "stream": False,
        "format": "json"
    }
    try:
        res = requests.post(OLLAMA_BASE_URL, json=payload, timeout=30)
        res.raise_for_status()
        raw_text = res.json().get("response", "{}")
        data = json.loads(raw_text)
        return {
            "name": data.get("name", "Mystery Sloth Garment"),
            "category": data.get("category", "Top"),
            "color": data.get("color", "Neutral"),
            "style_vibe": data.get("style_vibe", "Casual")
        }
    except Exception as e:
        return {
            "name": "Unidentified Item (Manual Override)",
            "category": "Top",
            "color": "Unknown",
            "style_vibe": "Casual",
            "error": str(e)
        }

def generate_outfit_deck(
    clean_items: List[Dict],
    occasion: str,
    laziness_level: int,
    weather: str,
    text_model: str = "llama3.2:3b"
) -> Dict:
    """
    Acts like a Clash Royale Deck Builder for your closet.
    Takes ONLY clean/available clothes and outputs an optimal outfit + a 'Missing Card' unlock recommendation.
    """
    inventory_summary = "\n".join(
        [f"- [ID:{item['id']}] {item['name']} (Category: {item['category']}, Color: {item['color']}, Vibe: {item['style_vibe']})"
         for item in clean_items]
    )

    system_prompt = f"""You are SlothCloset AI, a sharp, witty wardrobe deck-builder running 100% locally.
The user wants an outfit from their CURRENTLY CLEAN clothes.

USER CONTEXT:
- Target Occasion: {occasion}
- Sloth Laziness Level: {laziness_level}/10 (10 = maximum comfort, zero ironing, minimum effort)
- Weather: {weather}

AVAILABLE CLEAN INVENTORY:
{inventory_summary}

INSTRUCTIONS:
1. Pick the best cohesive outfit combination strictly from the AVAILABLE CLEAN INVENTORY above (at minimum a Top and a Bottom, plus Footwear/Layer if available).
2. Calculate a 'Synergy Score' out of 100 based on color theory and occasion match.
3. Suggest ONE 'Unlock Card' (a new piece of clothing NOT in their inventory) that, if bought, would pair with their existing items to unlock 3+ fresh outfit combos.

Respond ONLY in valid JSON with this exact structure:
{{
  "deck_name": "Creative name for this outfit combo",
  "selected_item_ids": [1, 3, 7],
  "synergy_score": 88,
  "color_harmony_reason": "Why these colors and vibes actually work together without looking messy.",
  "sloth_justification": "Why this takes zero mental energy to pull off today.",
  "unlock_card": {{
    "missing_item": "Specific clothing item to buy next (e.g., Charcoal Denim Jacket)",
    "combos_unlocked": "Explain which existing items in their list this new piece unlocks."
  }}
}}"""

    payload = {
        "model": text_model,
        "prompt": system_prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.4}
    }

    try:
        res = requests.post(OLLAMA_BASE_URL, json=payload, timeout=45)
        res.raise_for_status()
        raw_response = res.json().get("response", "{}")
        return json.loads(raw_response)
    except Exception as e:
        return {"error": f"Local Ollama inference failed: {str(e)}"}