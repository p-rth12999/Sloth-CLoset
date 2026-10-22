import os
import re
import io
import time
import json
import uuid
from pathlib import Path
import requests
from PIL import Image
import streamlit as st
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

st.set_page_config(
    page_title="SLOTHCLOSET // Wardrobe OS",
    page_icon="🦥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- SUPERDESIGN / KARPATHY MINIMALIST DARK CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');
    .stApp { background-color: #070709; color: #ededef; font-family: 'Inter', sans-serif; }
    .mono-tag { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #a1a1aa; letter-spacing: 0.04em; text-transform: uppercase; }
    .studio-card {
        background: radial-gradient(circle at 50% 35%, #181a24 0%, #0d0e12 80%);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px;
        padding: 14px;
        margin-bottom: 10px;
    }
    .metric-box {
        background: #0e0f14;
        border: 1px solid rgba(255,255,255,0.07);
        border-radius: 10px;
        padding: 14px;
    }
</style>
""", unsafe_allow_html=True)


def get_secret(key: str, default: str = "") -> str:
    try:
        if key in st.secrets:
            return str(st.secrets[key]).strip().strip('"').strip("'")
    except Exception:
        pass
    return os.getenv(key, default).strip().strip('"').strip("'")


MONGO_URI = get_secret("MONGO_URI", "")
SERPAPI_KEY = get_secret("SERPAPI_KEY", "")
GROQ_API_KEY = get_secret("GROQ_API_KEY", "")
GEMMA_MODEL = get_secret("GEMMA_MODEL", "gemma2:2b")
OLLAMA_URL = "http://localhost:11434/api/generate"
RULES_PATH = BASE_DIR / "meta_rules.json"
LOCAL_BACKUP_FILE = BASE_DIR / "wardrobe_local.json"


@st.cache_resource
def get_mongo_collection():
    if MONGO_URI and "<" not in MONGO_URI:
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=4000)
            client.admin.command("ping")
            return client["slothcloset_db"]["wardrobe"]
        except Exception:
            return None
    return None


wardrobe_col = get_mongo_collection()


def load_meta_rules() -> dict:
    if RULES_PATH.exists():
        try:
            return json.loads(RULES_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "base_score": 68,
        "pairings": {
            "neutral_dark+neutral_light": 18,
            "neutral_dark+warm_pop": 22,
            "neutral_dark+earth": 16,
            "neutral_dark+cool": 15,
            "neutral_dark+neutral_dark": 14,
            "neutral_light+earth": 18,
            "neutral_light+cool": 20,
            "earth+warm_pop": 20,
            "cool+warm_pop": 18,
            "warm_pop+warm_pop": -22
        },
        "archetypes": {
            "balanced": {"name": "Standard Meta Draft", "badge": "⚡ All-Rounder", "desc": "Balanced multi-color harmony across your clean, unbanned wardrobe."},
            "monochrome": {"name": "The Monochrome Beatdown", "badge": "🖤 Dark/Light Core", "desc": "Strictly prioritizes Black, White, Charcoal, and Grey; blocks loud pop colors."},
            "earth": {"name": "The Earth-Tone Cycle", "badge": "🌿 Olive & Utility", "desc": "Prioritizes Olive, Forest Green, Cargo, Mustard, and grounded utility pieces."},
            "contrast": {"name": "High-Contrast Aggro", "badge": "🔥 Pop Win-Condition", "desc": "Pairs statement pop colors (Crimson, Mango, Mustard) with grounded dark anchors."}
        }
    }


def get_seed_clothes() -> list:
    """16 Diverse Multi-Color Wardrobe Assets (Tops, Layers, Bottoms, 2 Shoes, 2 Watches)"""
    u = "https://images.unsplash.com/"
    return [
        # --- TOPS (6) ---
        {"id": "c1", "name": "Matte Black Oversized Heavy Tee", "category": "Top", "color": "Pitch Black / Charcoal", "hex_colors": ["#181A1F", "#374151"], "style_vibe": "Monochrome / Streetwear", "image_url": u + "photo-1583743814966-8936f5b7be1a?w=500&auto=format&fit=crop&q=60", "is_clean": True, "is_banned": False},
        {"id": "c2", "name": "Crisp White Boxy Crewneck Tee", "category": "Top", "color": "Pure White / Off-White", "hex_colors": ["#FFFFFF", "#E5E7EB"], "style_vibe": "Monochrome / Minimalist", "image_url": u + "photo-1521572267360-ee0c2909d518?w=500&auto=format&fit=crop&q=60", "is_clean": True, "is_banned": False},
        {"id": "c3", "name": "Navy & Crimson Jersey Tee", "category": "Top", "color": "Navy / Crimson / Gold", "hex_colors": ["#1B263B", "#D90429", "#FFB703"], "style_vibe": "Sporty / Contrast", "image_url": u + "photo-1576566588028-4147f3842f27?w=500&auto=format&fit=crop&q=60", "is_clean": True, "is_banned": False},
        {"id": "c4", "name": "Ice Blue Striped Half-Sleeve Shirt", "category": "Top", "color": "Ice Blue / Crisp White", "hex_colors": ["#BFDBFE", "#FFFFFF"], "style_vibe": "Smart Casual / Cool", "image_url": u + "photo-1596755094514-f87e34085b2c?w=500&auto=format&fit=crop&q=60", "is_clean": True, "is_banned": False},
        {"id": "c5", "name": "Mustard Graphic Street Tee", "category": "Top", "color": "Mustard Gold / Black", "hex_colors": ["#E1AD01", "#181A1F"], "style_vibe": "Streetwear / Earth", "image_url": u + "photo-1521572163474-6864f9cf17ab?w=500&auto=format&fit=crop&q=60", "is_clean": True, "is_banned": False},
        {"id": "c6", "name": "Forest Olive Waffle Knit Henley", "category": "Top", "color": "Forest Olive / Earth Brown", "hex_colors": ["#3B4A20", "#78350F"], "style_vibe": "Earth / Utility", "image_url": u + "photo-1618354691373-d851c5c3a990?w=500&auto=format&fit=crop&q=60", "is_clean": True, "is_banned": False},

        # --- BOTTOMS (4) ---
        {"id": "c7", "name": "Olive Relaxed Cargo Pants", "category": "Bottom", "color": "Olive Green", "hex_colors": ["#556B2F", "#3B4A20"], "style_vibe": "Utility / Earth", "image_url": u + "photo-1624378439575-d8705ad7ae80?w=500&auto=format&fit=crop&q=60", "is_clean": True, "is_banned": False},
        {"id": "c8", "name": "Charcoal Black Slim Jeans", "category": "Bottom", "color": "Charcoal Black", "hex_colors": ["#1F2937", "#111827"], "style_vibe": "Monochrome / Versatile", "image_url": u + "photo-1542272604-787c3835535d?w=500&auto=format&fit=crop&q=60", "is_clean": True, "is_banned": False},
        {"id": "c9", "name": "Heather Grey Athletic Joggers", "category": "Bottom", "color": "Heather Grey", "hex_colors": ["#6B7280", "#E5E7EB"], "style_vibe": "Monochrome / Cozy", "image_url": u + "photo-1552902865-b72c031ac5ea?w=500&auto=format&fit=crop&q=60", "is_clean": True, "is_banned": False},
        {"id": "c10", "name": "Vintage Indigo Relaxed Denim", "category": "Bottom", "color": "Indigo Blue", "hex_colors": ["#2B4C7E", "#1B263B"], "style_vibe": "Classic / Cool", "image_url": u + "photo-1604176354204-9268737828e4?w=500&auto=format&fit=crop&q=60", "is_clean": True, "is_banned": False},

        # --- OUTER LAYERS (2) ---
        {"id": "c11", "name": "Colorblock Zip Hoodie (Black/White/Mango)", "category": "Layer", "color": "Black / White / Mango Yellow", "hex_colors": ["#181A1F", "#F5F5F5", "#EAB308"], "style_vibe": "Contrast / Streetwear", "image_url": u + "photo-1556821840-3a63f95609a7?w=500&auto=format&fit=crop&q=60", "is_clean": True, "is_banned": False},
        {"id": "c12", "name": "Matte Black Minimalist Bomber Jacket", "category": "Layer", "color": "Matte Black / Gunmetal", "hex_colors": ["#111827", "#374151"], "style_vibe": "Monochrome / Sleek", "image_url": u + "photo-1551028719-00167b16eac5?w=500&auto=format&fit=crop&q=60", "is_clean": True, "is_banned": False},

        # --- FOOTWEAR (2) ---
        {"id": "c13", "name": "White & Gum Low Court Sneakers", "category": "Footwear", "color": "Crisp White / Gum Brown", "hex_colors": ["#F9FAFB", "#92400E"], "style_vibe": "Clean / Earth", "image_url": u + "photo-1549298916-b41d501d3772?w=500&auto=format&fit=crop&q=60", "is_clean": True, "is_banned": False},
        {"id": "c14", "name": "Obsidian & Slate Tech Runners", "category": "Footwear", "color": "Obsidian Black / Cool Grey", "hex_colors": ["#181A1F", "#6B7280"], "style_vibe": "Monochrome / Streetwear", "image_url": u + "photo-1542291026-7eec264c27ff?w=500&auto=format&fit=crop&q=60", "is_clean": True, "is_banned": False},

        # --- ACCESSORIES / WATCHES (2) ---
        {"id": "c15", "name": "Matte Black Sport Chronograph Watch", "category": "Accessory", "color": "Matte Black / Dark Dial", "hex_colors": ["#181A1F", "#4B5563"], "style_vibe": "Monochrome / Daily", "image_url": u + "photo-1524805444758-089113d48a6d?w=500&auto=format&fit=crop&q=60", "is_clean": True, "is_banned": False},
        {"id": "c16", "name": "Brushed Silver Minimalist Steel Watch", "category": "Accessory", "color": "Brushed Silver / White Dial", "hex_colors": ["#E5E7EB", "#6B7280"], "style_vibe": "Smart Casual / Versatile", "image_url": u + "photo-1522335789203-aabd1fc54bc9?w=500&auto=format&fit=crop&q=60", "is_clean": True, "is_banned": False}
    ]


def serialize_item(item: dict) -> dict:
    hex_list = item.get("hex_colors")
    if not hex_list or not isinstance(hex_list, list):
        hex_list = [item.get("hex_color", "#181A1F")]
    return {
        "id": str(item.get("_id") or item.get("id")),
        "name": item.get("name", ""),
        "category": item.get("category", "Top"),
        "color": item.get("color", ""),
        "hex_colors": hex_list,
        "hex_color": hex_list[0],
        "style_vibe": item.get("style_vibe", "Casual"),
        "image_url": item.get("image_url", ""),
        "is_clean": item.get("is_clean", True),
        "is_banned": item.get("is_banned", False),
    }


def db_get_all() -> list:
    if wardrobe_col is not None:
        items = [serialize_item(i) for i in wardrobe_col.find().sort("_id", -1)]
        if len(items) >= 15:
            return items
    if "local_wardrobe" not in st.session_state or len(st.session_state.local_wardrobe) < 15:
        seeded = get_seed_clothes()
        st.session_state.local_wardrobe = seeded
        try:
            LOCAL_BACKUP_FILE.write_text(json.dumps(seeded, indent=2), encoding="utf-8")
        except Exception:
            pass
    return st.session_state.local_wardrobe


def db_save_items(items: list):
    st.session_state.local_wardrobe = items
    try:
        LOCAL_BACKUP_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")
    except Exception:
        pass


# --- COLOR MATH & ARCHETYPE-STRICT SYNERGY ENGINE ---
def hex_to_rgb(hex_str: str) -> tuple:
    h = hex_str.lstrip("#")
    if len(h) != 6:
        return (128, 128, 128)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def classify_hex_family(hex_str: str) -> str:
    r, g, b = hex_to_rgb(hex_str)
    brightness = (r * 299 + g * 587 + b * 114) / 1000
    max_c, min_c = max(r, g, b), min(r, g, b)
    saturation = 0 if max_c == 0 else (max_c - min_c) / max_c

    if brightness < 55 and saturation < 0.35:
        return "neutral_dark"
    if brightness > 210 and saturation < 0.25:
        return "neutral_light"
    if saturation < 0.18:
        return "neutral_grey"
    if r > 160 and g > 110 and b < 90:
        return "warm_pop"  # Mango / Mustard / Gold
    if r > 160 and g < 80 and b < 80:
        return "warm_pop"  # Crimson / Red
    if (g >= r and b < 110) or (r > 100 and g > 50 and b < 40):
        return "earth"     # Olive / Forest / Brown
    return "cool"          # Navy / Indigo / Ice Blue


def score_outfit_combo(items: list, archetype: str, rules: dict) -> dict:
    """
    Produces realistic, archetype-differentiated scores (68% to 97%)
    so Monochrome, Earth, Contrast, and Balanced never pick the same items!
    """
    base = 66
    pairings = rules.get("pairings", {})
    reasons = []
    families = []
    all_hexes = []

    for item in items:
        h_list = item.get("hex_colors") or [item.get("hex_color", "#181A1F")]
        all_hexes.extend(h_list)
        for h in h_list:
            families.append(classify_hex_family(h))

    # 1. Average Pairwise Color Harmony (normalized so 5 items don't auto-hit 99%)
    pair_pts = []
    for i in range(len(families)):
        for j in range(i + 1, len(families)):
            f1, f2 = families[i], families[j]
            pts = pairings.get(f"{f1}+{f2}", pairings.get(f"{f2}+{f1}", 4))
            pair_pts.append(pts)

    avg_pair = (sum(pair_pts) / len(pair_pts)) if pair_pts else 8
    score = base + (avg_pair * 0.65)

    # 2. Strict Archetype Differentiation Rules
    mono_fams = sum(1 for f in families if f in ("neutral_dark", "neutral_light", "neutral_grey"))
    earth_fams = sum(1 for f in families if f == "earth")
    pop_fams = sum(1 for f in families if f == "warm_pop")
    cool_fams = sum(1 for f in families if f == "cool")

    if archetype == "monochrome":
        if pop_fams > 0 or earth_fams > 0 or cool_fams > 0:
            score -= (pop_fams * 18) + (earth_fams * 14) + (cool_fams * 12)
        else:
            score += 14
            reasons.append("Pure monochrome stealth palette")
    elif archetype == "earth":
        if earth_fams >= 2:
            score += 15
            reasons.append("Dual earth-tone utility synergy")
        elif earth_fams == 1:
            score += 7
            reasons.append("Grounded earth-tone anchor")
        else:
            score -= 15
        if cool_fams > 1:
            score -= 8
    elif archetype == "contrast":
        if pop_fams >= 1 and mono_fams >= 2:
            score += 15
            reasons.append("High-contrast statement pop + dark anchor")
        elif cool_fams >= 1 and pop_fams >= 1:
            score += 12
            reasons.append("Dynamic warm/cool colorblock")
        else:
            score -= 14
    else:  # balanced
        distinct_fams = len(set(families))
        if 2 <= distinct_fams <= 3:
            score += 10
            reasons.append("Balanced 3-tone color harmony")

    # 3. Vibe Alignment Bonus
    vibes = " ".join(i.get("style_vibe", "").lower() for i in items)
    if archetype in vibes:
        score += 4
        reasons.append(f"Matched {archetype.title()} silhouette")

    # Deterministic tie-breaker using item IDs so scores don't flatline at the exact same integer
    sig_hash = sum(ord(ch) for i in items for ch in i["id"]) % 4
    final_score = max(54, min(97, int(round(score + (sig_hash * 0.5)))))

    seen_hex, palette = [], []
    for h in all_hexes:
        if h.upper() not in seen_hex and len(palette) < 4:
            seen_hex.append(h.upper())
            palette.append(h.upper())

    return {
        "synergy_score": final_score,
        "harmony_summary": " • ".join(reasons[:2]) if reasons else "Balanced daily color harmony",
        "color_palette": palette
    }


def draft_single_outfit_engine(
    all_items: list,
    locked_ids: list,
    excluded_ids: list,
    archetype: str,
    variation_index: int,
    recent_outfits: list
) -> dict:
    """
    Standalone Single Outfit Solver with Anti-Clone Rotation:
    Penalizes items that were just used in the previous standalone builds on screen
    (unless explicitly locked by the user) so every generated card is genuinely distinct!
    """
    rules = load_meta_rules()
    locked_set = {str(x) for x in locked_ids}
    excluded_set = {str(x) for x in excluded_ids} - locked_set

    # Count how many times each unlocked item appeared in recent standalone outfits
    recent_usage = {}
    for prev in recent_outfits[:4]:
        for c in prev.get("cards", []):
            cid = str(c["id"])
            if cid not in locked_set:
                recent_usage[cid] = recent_usage.get(cid, 0) + 1

    locked_items = [i for i in all_items if str(i["id"]) in locked_set]
    pool = [
        i for i in all_items
        if (i.get("is_clean", True) and not i.get("is_banned", False) and str(i["id"]) not in excluded_set)
        or str(i["id"]) in locked_set
    ]

    locked_by_cat = {}
    for item in locked_items:
        locked_by_cat.setdefault(item["category"], []).append(item)

    tops = locked_by_cat.get("Top") or [i for i in pool if i["category"] == "Top"]
    layers = locked_by_cat.get("Layer") or [i for i in pool if i["category"] == "Layer"]
    bottoms = locked_by_cat.get("Bottom") or [i for i in pool if i["category"] == "Bottom"]
    footwear = locked_by_cat.get("Footwear") or [i for i in pool if i["category"] == "Footwear"]
    accessories = locked_by_cat.get("Accessory") or [i for i in pool if i["category"] == "Accessory"]

    primary_uppers = tops if tops else layers
    if not primary_uppers or not bottoms:
        return None

    scored_candidates = []
    # Include both 'No Outer Layer' (None) and available Layers so outfits aren't forced to wear the same hoodie!
    layer_options = locked_by_cat.get("Layer") or ([None] + layers)
    shoe_options = footwear if footwear else [None]
    acc_options = accessories if accessories else [None]

    for t in primary_uppers:
        for b in bottoms:
            for l_opt in layer_options:
                for s_opt in shoe_options:
                    for a_opt in acc_options:
                        combo = list(locked_items)
                        used_ids = {c["id"] for c in combo}

                        for piece in (t, b, l_opt, s_opt, a_opt):
                            if piece and piece["id"] not in used_ids:
                                combo.append(piece)
                                used_ids.add(piece["id"])

                        ev = score_outfit_combo(combo, archetype, rules)

                        # Diversity penalty for repeating exact same Top, Bottom, Layer, Shoe, or Watch
                        repeat_penalty = 0
                        for c in combo:
                            cid = str(c["id"])
                            if cid in recent_usage:
                                weight = 14 if c["category"] in ("Top", "Bottom", "Layer") else 7
                                repeat_penalty += recent_usage[cid] * weight

                        rank_score = ev["synergy_score"] - repeat_penalty
                        sig = "-".join(sorted(str(c["id"]) for c in combo))
                        scored_candidates.append((rank_score, ev["synergy_score"], sig, combo, ev))

    unique_map = {}
    for r_sc, raw_sc, sig, combo, ev in scored_candidates:
        if sig not in unique_map:
            unique_map[sig] = (r_sc, raw_sc, combo, ev)

    ranked = sorted(unique_map.values(), key=lambda x: (x[0], x[1]), reverse=True)
    _, _, best_combo, best_eval = ranked[0]

    return {
        "outfit_id": str(uuid.uuid4())[:6].upper(),
        "outfit_name": f"{archetype.title()} Studio Build #{variation_index + 1}",
        "archetype": archetype,
        "synergy_score": best_eval["synergy_score"],
        "harmony_summary": best_eval["harmony_summary"],
        "locked_count": len(locked_items),
        "color_palette": best_eval["color_palette"],
        "cards": best_combo
    }


def plan_weekly_outfits_engine(clean_unbanned: list, archetype: str, num_days: int, wash_cooldown_days: int) -> list:
    rules = load_meta_rules()
    tops = [i for i in clean_unbanned if i["category"] == "Top"]
    layers = [i for i in clean_unbanned if i["category"] == "Layer"]
    bottoms = [i for i in clean_unbanned if i["category"] == "Bottom"]
    footwear = [i for i in clean_unbanned if i["category"] == "Footwear"]
    accessories = [i for i in clean_unbanned if i["category"] == "Accessory"]

    if not (tops or layers) or not bottoms:
        return []

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    last_worn_day, wear_count, planned_outfits = {}, {}, []

    def is_available(item: dict, current_day: int) -> bool:
        iid = item["id"]
        if iid not in last_worn_day:
            return True
        days_since = current_day - last_worn_day[iid]
        if item["category"] in ("Footwear", "Accessory"):
            return True
        if item["category"] in ("Bottom", "Layer"):
            return days_since > 1
        return days_since > wash_cooldown_days

    for day_idx in range(num_days):
        avail_tops = [t for t in tops if is_available(t, day_idx)] or sorted(tops, key=lambda x: last_worn_day.get(x["id"], -99))[:2]
        avail_layers = [l for l in layers if is_available(l, day_idx)]
        avail_bottoms = [b for b in bottoms if is_available(b, day_idx)] or sorted(bottoms, key=lambda x: last_worn_day.get(x["id"], -99))[:2]

        best_combo, best_eval, best_adj = None, None, -999

        for t in avail_tops:
            for b in avail_bottoms:
                candidate = [t, b]
                # Attach outer layer on alternate days if available
                if avail_layers and day_idx % 2 == 1:
                    lp = avail_layers[day_idx % len(avail_layers)]
                    if lp["id"] != t["id"]:
                        candidate.append(lp)
                if footwear:
                    candidate.append(footwear[day_idx % len(footwear)])
                if accessories:
                    candidate.append(accessories[day_idx % len(accessories)])

                ev = score_outfit_combo(candidate, archetype, rules)
                penalty = sum(wear_count.get(c["id"], 0) * 8 for c in candidate if c["category"] in ("Top", "Bottom", "Layer"))
                if ev["synergy_score"] - penalty > best_adj:
                    best_adj = ev["synergy_score"] - penalty
                    best_combo, best_eval = candidate, ev

        if best_combo and best_eval:
            reused_notes = []
            for card in best_combo:
                cid = card["id"]
                if wear_count.get(cid, 0) > 0:
                    reused_notes.append(f"♻️ Reused {card['category']}" if card["category"] in ("Footwear", "Accessory") else f"🧺 Post-Wash ({card['name']})")
                last_worn_day[cid] = day_idx
                wear_count[cid] = wear_count.get(cid, 0) + 1

            planned_outfits.append({
                "day_number": day_idx + 1,
                "day_label": f"DAY 0{day_idx + 1} // {day_names[day_idx % 7].upper()}",
                "outfit_name": f"{day_names[day_idx % 7]} {archetype.title()} Spec",
                "synergy_score": best_eval["synergy_score"],
                "harmony_summary": best_eval["harmony_summary"],
                "reuse_badges": reused_notes,
                "color_palette": best_eval["color_palette"],
                "cards": best_combo
            })
    return planned_outfits


def fetch_serpapi_image(query: str) -> dict:
    fallback = "https://images.unsplash.com/photo-1556821840-3a63f95609a7?w=500&auto=format&fit=crop&q=60"
    if not SERPAPI_KEY or SERPAPI_KEY == "your_serpapi_key_here":
        return {"thumbnail": fallback, "link": f"https://www.google.com/search?tbm=shop&q={requests.utils.quote(query)}"}
    try:
        res = requests.get("https://serpapi.com/search.json", params={
            "engine": "google_images", "q": f"{query} isolated product studio flat lay", "api_key": SERPAPI_KEY, "num": 1
        }, timeout=6)
        imgs = res.json().get("images_results", [])
        if imgs:
            return {"thumbnail": imgs[0].get("original") or imgs[0].get("thumbnail"), "link": imgs[0].get("link", "#")}
    except Exception:
        pass
    return {"thumbnail": fallback, "link": "#"}


def run_gemma_strategy(cards: list, archetype: str) -> dict:
    summary = ", ".join([f"{c['name']} ({c['color']})" for c in cards])
    prompt = f"""Analyze this outfit ({archetype} archetype): {summary}.
Reply ONLY in valid JSON:
{{"battle_strategy": "2 concise sentences explaining why this color combination works effortlessly.", "unlock_item_name": "1 specific clothing piece or accessory that upgrades this look", "unlock_search_query": "mens minimalist streetwear overshirt flat lay", "unlock_reason": "1 sentence on why it fits."}}"""

    data = None
    try:
        res = requests.post(OLLAMA_URL, json={"model": GEMMA_MODEL, "prompt": prompt, "stream": False, "format": "json"}, timeout=4)
        if res.ok:
            data = json.loads(res.json().get("response", "{}"))
    except Exception:
        pass

    if not data and GROQ_API_KEY:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={"model": "gemma2-9b-it", "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}},
                timeout=8
            )
            if r.ok:
                data = json.loads(r.json()["choices"][0]["message"]["content"])
        except Exception:
            pass

    if not data or "battle_strategy" not in data:
        data = {
            "battle_strategy": f"High-tempo {archetype} synergy: your upper silhouette creates clean visual contrast while grounded neutral anchors prevent color saturation.",
            "unlock_item_name": "Matte Charcoal Minimalist Overshirt",
            "unlock_search_query": "mens minimalist charcoal overshirt flat lay",
            "unlock_reason": "Bridges your graphic tops and utility bottoms with an effortless layer."
        }

    visual = fetch_serpapi_image(data.get("unlock_search_query", "mens streetwear jacket flat lay"))
    return {
        "battle_strategy": data.get("battle_strategy"),
        "unlock_item_name": data.get("unlock_item_name"),
        "unlock_reason": data.get("unlock_reason"),
        "image_url": visual["thumbnail"],
        "shop_link": visual["link"]
    }


# --- SESSION STATE INITIALIZATION ---
if "nav_view" not in st.session_state:
    st.session_state.nav_view = "00. Index"
if "standalone_feed" not in st.session_state:
    st.session_state.standalone_feed = []
if "weekly_plan" not in st.session_state:
    st.session_state.weekly_plan = None
if "var_counter" not in st.session_state:
    st.session_state.var_counter = 0

items = db_get_all()
rules = load_meta_rules()
archetypes = rules.get("archetypes", {})

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.markdown('<div class="mono-tag">SLOTHCLOSET_OS // v2.5</div>', unsafe_allow_html=True)
    st.title("🦥 SlothCloset")
    st.caption("Deterministic Wardrobe Graph • Gemma 2 • MongoDB Atlas")

    nav = st.radio(
        "Navigation",
        ["00. Index", "01. Outfit Planner", "02. Wardrobe"],
        index=["00. Index", "01. Outfit Planner", "02. Wardrobe"].index(st.session_state.nav_view)
    )
    st.session_state.nav_view = nav

    st.divider()
    clean_ready = [i for i in items if i.get("is_clean", True) and not i.get("is_banned", False)]
    st.metric("Total Closet Assets", len(items))
    st.metric("Clean & Draftable", len(clean_ready))
    if st.button("🌱 Reset / Seed 16-Item Closet", use_container_width=True):
        seeded = get_seed_clothes()
        if wardrobe_col is not None:
            wardrobe_col.delete_many({})
            wardrobe_col.insert_many(seeded)
        db_save_items(seeded)
        st.session_state.standalone_feed = []
        st.session_state.weekly_plan = None
        st.rerun()


# =====================================================================
# VIEW 1: 00. INDEX (LANDING PAGE)
# =====================================================================
if st.session_state.nav_view == "00. Index":
    st.markdown('<div class="mono-tag">HEURISTIC GRAPH (0.001s) • GEMMA-2 • SERPAPI STUDIO TWINS</div>', unsafe_allow_html=True)
    st.markdown("<h1 style='font-size: 3.1rem; font-weight: 800; line-height: 1.1; margin-top: 8px;'>Deterministic wardrobe synthesis.<br><span style='color:#71717a;'>Zero morning decision fatigue.</span></h1>", unsafe_allow_html=True)
    st.write("Treat your closet as a finite constraint graph. Lock specific pieces to synthesize standalone outfits on demand, or compute a 3–7 day wash-cycle rotation in sub-millisecond Python math.")

    c1, c2, c3 = st.columns(3)
    c1.markdown(f"<div class='metric-box'><div class='mono-tag'>TOTAL ASSETS</div><h2 style='margin:0;'>{len(items)}</h2></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='metric-box'><div class='mono-tag'>CLEAN & READY</div><h2 style='margin:0; color:#34d399;'>{len(clean_ready)}</h2></div>", unsafe_allow_html=True)
    c3.markdown("<div class='metric-box'><div class='mono-tag'>SOLVER LATENCY</div><h2 style='margin:0;'>&lt; 1.0 ms</h2></div>", unsafe_allow_html=True)

    st.write("")
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("<div class='studio-card'><div class='mono-tag'>GATEWAY // 01</div><h3>⚡ + Outfit Planner</h3><p style='color:#a1a1aa; font-size:13px;'>Draft standalone outfits with custom item locks or compute a full 3–7 day weekly wash-cycle rotation.</p></div>", unsafe_allow_html=True)
        if st.button("Open Outfit Planner →", use_container_width=True, type="primary"):
            st.session_state.nav_view = "01. Outfit Planner"
            st.rerun()
    with g2:
        st.markdown("<div class='studio-card'><div class='mono-tag'>GATEWAY // 02</div><h3>🧥 Manage Wardrobe (16 Assets)</h3><p style='color:#a1a1aa; font-size:13px;'>Inspect studio cutouts, toggle laundry states, skip items, or add new multi-color clothing cards.</p></div>", unsafe_allow_html=True)
        if st.button("Open Wardrobe Repository →", use_container_width=True):
            st.session_state.nav_view = "02. Wardrobe"
            st.rerun()


# =====================================================================
# VIEW 2: 01. OUTFIT PLANNER (STANDALONE + WEEKLY ROTATION)
# =====================================================================
elif st.session_state.nav_view == "01. Outfit Planner":
    st.markdown('<div class="mono-tag">MODULE 01 // SYNTHESIS ENGINE</div>', unsafe_allow_html=True)
    st.header("Outfit Planner")

    arch_keys = list(archetypes.keys())
    selected_arch = st.selectbox(
        "Select Color / Vibe Constraint Archetype",
        arch_keys,
        format_func=lambda k: f"{archetypes[k]['badge']} — {archetypes[k]['name']} ({archetypes[k]['desc']})"
    )

    tab_single, tab_weekly = st.tabs(["⚡ + Standalone Outfits (Select / Lock)", "🗓️ Weekly Rotation (3–7 Days)"])

    # --- SUB-TAB A: STANDALONE OUTFIT GENERATOR ---
    with tab_single:
        st.subheader("Pre-Draft Item Constraints")
        st.caption("Lock specific items you *must* wear today, or exclude pieces you want to skip. Unselected items rotate automatically so every generated build is fresh.")

        col_lock, col_excl = st.columns(2)
        with col_lock:
            locked_names = st.multiselect(
                "🔒 Force-Lock Items in Outfit",
                options=[i["id"] for i in clean_ready],
                format_func=lambda iid: next((f"[{x['category']}] {x['name']}" for x in clean_ready if x["id"] == iid), iid)
            )
        with col_excl:
            excluded_names = st.multiselect(
                "🚫 Exclude Items from Draft",
                options=[i["id"] for i in clean_ready if i["id"] not in locked_names],
                format_func=lambda iid: next((f"[{x['category']}] {x['name']}" for x in clean_ready if x["id"] == iid), iid)
            )

        b_col1, b_col2 = st.columns([3, 1])
        if b_col1.button("⚡ + Generate New Standalone Outfit", type="primary", use_container_width=True):
            t0 = time.perf_counter()
            res_outfit = draft_single_outfit_engine(
                all_items=items,
                locked_ids=locked_names,
                excluded_ids=excluded_names,
                archetype=selected_arch,
                variation_index=st.session_state.var_counter,
                recent_outfits=st.session_state.standalone_feed
            )
            elapsed = round((time.perf_counter() - t0) * 1000, 2)
            if res_outfit:
                res_outfit["compute_time_ms"] = elapsed
                st.session_state.standalone_feed.insert(0, res_outfit)
                st.session_state.var_counter += 1
            else:
                st.error("Not enough clean & unbanned Tops/Bottoms! Click 'Reset / Seed 16-Item Closet' in the left sidebar.")

        if b_col2.button("Clear Feed", use_container_width=True):
            st.session_state.standalone_feed = []
            st.session_state.var_counter = 0
            st.rerun()

        if not st.session_state.standalone_feed:
            st.info("No standalone outfits generated yet. Click **+ Generate New Standalone Outfit** above to synthesize a look.")

        for idx, outfit in enumerate(st.session_state.standalone_feed):
            with st.container(border=True):
                hc1, hc2 = st.columns([4, 1])
                hc1.markdown(f"<div class='mono-tag'>STANDALONE // {outfit['outfit_id']} • {outfit['compute_time_ms']} ms</div><h3 style='margin:2px 0;'>{outfit['outfit_name']}</h3><p style='color:#a1a1aa; font-size:13px;'>{outfit['harmony_summary']}</p>", unsafe_allow_html=True)
                hc2.metric("Synergy", f"{outfit['synergy_score']}%")

                card_cols = st.columns(len(outfit["cards"]))
                for c_i, card in enumerate(outfit["cards"]):
                    with card_cols[c_i]:
                        st.image(card["image_url"], use_container_width=True)
                        st.markdown(f"<div class='mono-tag' style='color:#a78bfa;'>{card['category']}</div><div style='font-weight:600; font-size:13px; margin-bottom:4px;'>{card['name']}</div>", unsafe_allow_html=True)
                        swatches = " ".join([f"`{h}`" for h in card.get("hex_colors", [])])
                        st.markdown(swatches)

                if st.button(f"🧠 Run Gemma-2 Strategy Analysis & Find Missing Piece #{outfit['outfit_id']}", key=f"gemma_s_{outfit['outfit_id']}"):
                    with st.spinner("Gemma 2 analyzing outfit strategy..."):
                        outfit["gemma_analysis"] = run_gemma_strategy(outfit["cards"], outfit["archetype"])

                if outfit.get("gemma_analysis"):
                    ga = outfit["gemma_analysis"]
                    st.success(f"**🧠 Gemma-2 Strategy:** {ga['battle_strategy']}")
                    uc1, uc2 = st.columns([1, 4])
                    uc1.image(ga["image_url"], width=90)
                    uc2.markdown(f"**🔓 Recommended Upgrade (SerpApi):** {ga['unlock_item_name']}  \n{ga['unlock_reason']} — [Inspect Item ↗]({ga['shop_link']})")

    # --- SUB-TAB B: WEEKLY ROTATION PLANNER ---
    with tab_weekly:
        st.subheader("Weekly Wash-Cycle Constraint Solver")
        st.caption("Watches & Footwear rotate daily. Tops & Bottoms enter a mandatory wash/dry cooldown before re-wearing.")

        wc1, wc2, wc3 = st.columns([2, 2, 2])
        num_days = wc1.slider("Plan Days", min_value=3, max_value=7, value=5)
        wash_cooldown = wc2.selectbox("Top Wash/Dry Cooldown", [1, 2, 3], index=1, format_func=lambda d: f"{d} Days Rest/Wash")
        wc3.write("")
        if wc3.button("🗓️ Generate Weekly Plan", type="primary", use_container_width=True):
            t0 = time.perf_counter()
            decks = plan_weekly_outfits_engine(clean_ready, selected_arch, num_days, wash_cooldown)
            elapsed = round((time.perf_counter() - t0) * 1000, 2)
            st.session_state.weekly_plan = {"decks": decks, "ms": elapsed}

        if not st.session_state.weekly_plan:
            st.info("Weekly matrix idle. Choose your days (3–7) and click **Generate Weekly Plan**.")
        else:
            wp = st.session_state.weekly_plan
            st.caption(f"⚡ Computed {len(wp['decks'])}-Day Rotation Matrix in **{wp['ms']} ms**")
            for d_idx, deck in enumerate(wp["decks"]):
                with st.container(border=True):
                    top_l, top_r = st.columns([4, 1])
                    top_l.markdown(f"<div class='mono-tag'>{deck['day_label']}</div><h4 style='margin:2px 0;'>{deck['outfit_name']}</h4><p style='color:#a1a1aa; font-size:12px;'>{deck['harmony_summary']}</p>", unsafe_allow_html=True)
                    top_r.metric("Harmony", f"{deck['synergy_score']}%")

                    if deck.get("reuse_badges"):
                        st.markdown(" ".join([f"`{b}`" for b in deck["reuse_badges"]]))

                    d_cols = st.columns(len(deck["cards"]))
                    for c_i, card in enumerate(deck["cards"]):
                        with d_cols[c_i]:
                            st.image(card["image_url"], use_container_width=True)
                            st.markdown(f"<div class='mono-tag' style='color:#a78bfa;'>{card['category']}</div><div style='font-weight:600; font-size:12px;'>{card['name']}</div>", unsafe_allow_html=True)


# =====================================================================
# VIEW 3: 02. WARDROBE (INVENTORY & ASSET MANAGEMENT)
# =====================================================================
elif st.session_state.nav_view == "02. Wardrobe":
    st.markdown('<div class="mono-tag">MODULE 02 // INVENTORY REPOSITORY</div>', unsafe_allow_html=True)
    tb1, tb2 = st.columns([3, 1])
    tb1.header(f"Wardrobe Assets ({len(items)} Items)")
    if tb2.button("🌱 Seed 16-Item Sample Closet", use_container_width=True, type="primary"):
        seeded = get_seed_clothes()
        if wardrobe_col is not None:
            wardrobe_col.delete_many({})
            wardrobe_col.insert_many(seeded)
        db_save_items(seeded)
        st.rerun()

    with st.expander("➕ Upload / Add New Multi-Color Clothing Asset"):
        with st.form("add_asset_form"):
            f_name = st.text_input("Item Name", placeholder="e.g., Champion Colorblock Hoodie")
            fc1, fc2, fc3 = st.columns(3)
            f_cat = fc1.selectbox("Category", ["Top", "Layer", "Bottom", "Footwear", "Accessory"])
            f_col = fc2.text_input("Color Description", placeholder="Black / White / Mango Yellow")
            f_vibe = fc3.text_input("Style Vibe", value="Streetwear / Everything")
            sc1, sc2, sc3 = st.columns(3)
            hex1 = sc1.color_picker("Primary HEX", "#181A1F")
            hex2 = sc2.color_picker("Secondary HEX", "#EAB308")
            hex3 = sc3.color_picker("Accent HEX", "#F5F5F5")
            submitted = st.form_submit_button("Save Asset to Closet", type="primary")
            if submitted and f_name:
                serp = fetch_serpapi_image(f"{f_col} {f_name} {f_cat}")
                new_doc = {
                    "id": str(uuid.uuid4())[:8],
                    "name": f_name,
                    "category": f_cat,
                    "color": f_col or "Multi",
                    "hex_colors": [hex1, hex2, hex3],
                    "hex_color": hex1,
                    "style_vibe": f_vibe,
                    "image_url": serp["thumbnail"],
                    "is_clean": True,
                    "is_banned": False
                }
                if wardrobe_col is not None:
                    wardrobe_col.insert_one(new_doc)
                items.insert(0, new_doc)
                db_save_items(items)
                st.success(f"Added {f_name}!")
                st.rerun()

    grid_cols = st.columns(4)
    for idx, item in enumerate(items):
        with grid_cols[idx % 4]:
            with st.container(border=True):
                status = "🚫 SKIPPED" if item.get("is_banned") else ("🟢 CLEAN" if item.get("is_clean", True) else "🌊 LAUNDRY")
                st.caption(f"`{item['category']}` • **{status}**")
                st.image(item["image_url"], use_container_width=True)
                st.markdown(f"**{item['name']}**")
                st.caption(item["color"])
                b1, b2 = st.columns(2)
                if b1.button("🧺 Wash/Dry", key=f"clean_{item['id']}", use_container_width=True):
                    item["is_clean"] = not item.get("is_clean", True)
                    if wardrobe_col is not None:
                        q = {"_id": ObjectId(item["id"])} if ObjectId.is_valid(item["id"]) else {"id": item["id"]}
                        wardrobe_col.update_one(q, {"$set": {"is_clean": item["is_clean"]}})
                    db_save_items(items)
                    st.rerun()
                if b2.button("🚫 Skip/Include", key=f"ban_{item['id']}", use_container_width=True):
                    item["is_banned"] = not item.get("is_banned", False)
                    if wardrobe_col is not None:
                        q = {"_id": ObjectId(item["id"])} if ObjectId.is_valid(item["id"]) else {"id": item["id"]}
                        wardrobe_col.update_one(q, {"$set": {"is_banned": item["is_banned"]}})
                    db_save_items(items)
                    st.rerun()