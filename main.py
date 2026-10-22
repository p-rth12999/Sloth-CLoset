import os
import re
import io
import time
import json
import uuid
import base64
from pathlib import Path
import requests
from PIL import Image
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv

try:
    from rembg import remove as rembg_remove
    REMBG_AVAILABLE = True
except ImportError:
    REMBG_AVAILABLE = False

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
RULES_PATH = BASE_DIR / "meta_rules.json"
LOCAL_BACKUP_FILE = BASE_DIR / "wardrobe_local.json"

load_dotenv(dotenv_path=ENV_PATH, override=True)

app = FastAPI(title="SlothCloset | Weekly Wardrobe Planner")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

MONGO_URI = os.getenv("MONGO_URI", "").strip().strip('"').strip("'")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip().strip('"').strip("'")
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "gemma2:2b").strip().strip('"').strip("'")
OLLAMA_URL = "http://localhost:11434/api/generate"

wardrobe_col = None
if MONGO_URI and "<" not in MONGO_URI:
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=4000)
        client.admin.command("ping")
        wardrobe_col = client["slothcloset_db"]["wardrobe"]
        print(f"✅ Connected to MongoDB Atlas! | Local Cutout (rembg): {REMBG_AVAILABLE}")
    except Exception as e:
        print(f"⚠️ MongoDB fallback active: {e}")


def load_meta_rules() -> dict:
    if RULES_PATH.exists():
        return json.loads(RULES_PATH.read_text(encoding="utf-8"))
    return {"base_score": 65, "pairings": {}, "archetypes": {}}


# --- COLOR MATH & HEURISTIC SYNERGY ENGINE (0.001s) ---
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
    if r > 160 and g > 120 and b < 90:
        return "warm_pop"
    if r > 160 and g < 80 and b < 80:
        return "warm_pop"
    if g >= r and b < 110:
        return "earth"
    return "cool"


def score_outfit_combo(items: list, archetype: str, rules: dict) -> dict:
    score = rules.get("base_score", 65)
    pairings = rules.get("pairings", {})
    reasons = []

    families = []
    all_hexes = []
    for item in items:
        h_list = item.get("hex_colors") or [item.get("hex_color", "#181A1F")]
        all_hexes.extend(h_list)
        for h in h_list[:2]:
            families.append(classify_hex_family(h))

    pair_bonus = 0
    for i in range(len(families)):
        for j in range(i + 1, len(families)):
            f1, f2 = families[i], families[j]
            key1, key2 = f"{f1}+{f2}", f"{f2}+{f1}"
            pts = pairings.get(key1, pairings.get(key2, 6))
            pair_bonus += pts

    score += min(24, max(-20, pair_bonus // max(1, len(families) - 1)))

    if any(len(i.get("hex_colors", [])) > 1 for i in items):
        score += 5
        reasons.append("Multi-color accent bridge")

    vibes = [i.get("style_vibe", "").lower() for i in items]
    if len(set(vibes)) == 1 and vibes[0]:
        score += 8
        reasons.append("Unified style vibe")
    elif any(k in " ".join(vibes) for k in ["everything", "versatile", "clean", "daily"]):
        score += 5
        reasons.append("Versatile core staples")

    if archetype == "monochrome":
        mono_count = sum(1 for f in families if f in ("neutral_dark", "neutral_light", "neutral_grey"))
        pop_count = sum(1 for f in families if f in ("warm_pop", "cool"))
        score += (mono_count * 7) - (pop_count * 12)
        reasons.append("Monochrome tone alignment")
    elif archetype == "earth":
        earth_count = sum(1 for f in families if f in ("earth", "warm_pop", "neutral_dark"))
        score += earth_count * 6
        reasons.append("Earth-Tone palette boost")
    elif archetype == "contrast":
        has_pop = "warm_pop" in families or "cool" in families
        has_dark = "neutral_dark" in families
        has_light = "neutral_light" in families
        if has_pop and (has_dark or has_light):
            score += 14
            reasons.append("High-contrast statement pop")
        else:
            score -= 8

    final_score = max(50, min(99, int(score)))

    seen_hex = []
    palette = []
    labels = ["Primary Tone", "Base Anchor", "Accent Pop", "Bridge Shade"]
    for h in all_hexes:
        if h.upper() not in seen_hex and len(palette) < 4:
            seen_hex.append(h.upper())
            palette.append({
                "name": labels[len(palette)],
                "hex": h.upper(),
                "family": classify_hex_family(h).replace("_", " ").title()
            })

    return {
        "synergy_score": final_score,
        "harmony_summary": " • ".join(reasons[:2]) if reasons else "Balanced daily color harmony",
        "color_palette": palette
    }


def plan_weekly_outfits_engine(
    clean_unbanned: list,
    archetype: str = "balanced",
    num_days: int = 5,
    wash_cooldown_days: int = 2
) -> list:
    """
    Weekly Outfit Planner with Wash-Cycle Cooldown & Asset Reuse:
    - Footwear & Accessories (Watches, Shades): 0-day cooldown (reusable daily).
    - Bottoms & Outer Layers: 1-day cooldown (can re-wear after 1 rest day).
    - Tops: `wash_cooldown_days` (default 2 days for laundry/drying before re-wearing).
    """
    rules = load_meta_rules()
    tops = [i for i in clean_unbanned if i["category"] == "Top"]
    layers = [i for i in clean_unbanned if i["category"] == "Layer"]
    bottoms = [i for i in clean_unbanned if i["category"] == "Bottom"]
    footwear = [i for i in clean_unbanned if i["category"] == "Footwear"]
    accessories = [i for i in clean_unbanned if i["category"] == "Accessory"]

    if not (tops or layers) or not bottoms:
        return []

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    last_worn_day = {}  # item_id -> day_idx
    wear_count = {}     # item_id -> count across the week
    planned_outfits = []

    def is_available(item: dict, current_day: int) -> bool:
        iid = item["id"]
        if iid not in last_worn_day:
            return True
        days_since = current_day - last_worn_day[iid]
        cat = item["category"]
        if cat in ("Footwear", "Accessory"):
            return True  # Watches & shoes can be reused anytime!
        if cat in ("Bottom", "Layer"):
            return days_since > 1  # 1-day rest/wash buffer
        # Tops require full wash cooldown (e.g. 2 days gap -> worn Day 0, available Day 3)
        return days_since > wash_cooldown_days

    for day_idx in range(num_days):
        avail_tops = [t for t in tops if is_available(t, day_idx)]
        avail_layers = [l for l in layers if is_available(l, day_idx)]
        avail_bottoms = [b for b in bottoms if is_available(b, day_idx)]

        # Graceful fallback if closet is small and everything is in wash cooldown
        if not avail_tops and not avail_layers:
            avail_tops = sorted(tops + layers, key=lambda x: last_worn_day.get(x["id"], -99))[:2]
        if not avail_bottoms:
            avail_bottoms = sorted(bottoms, key=lambda x: last_worn_day.get(x["id"], -99))[:2]

        primary_uppers = avail_tops if avail_tops else avail_layers

        best_combo = None
        best_eval = None
        best_adjusted_score = -999

        for t in primary_uppers:
            for b in avail_bottoms:
                candidate = [t, b]

                # Add Layer if available and provides good contrast/warmth
                if avail_layers and t["category"] != "Layer":
                    layer_pick = avail_layers[day_idx % len(avail_layers)]
                    if layer_pick["id"] != t["id"] and day_idx % 2 == 0:
                        candidate.append(layer_pick)

                # Always attach Footwear (reusable asset)
                if footwear:
                    shoe_pick = footwear[day_idx % len(footwear)]
                    candidate.append(shoe_pick)

                # Attach Accessory like Watch / Shades (reusable asset)
                if accessories:
                    acc_pick = accessories[day_idx % len(accessories)]
                    candidate.append(acc_pick)

                evaluation = score_outfit_combo(candidate, archetype, rules)
                # Slight freshness penalty for already-worn items so every day feels unique
                freshness_penalty = sum(wear_count.get(c["id"], 0) * 4 for c in candidate if c["category"] in ("Top", "Bottom"))
                adj_score = evaluation["synergy_score"] - freshness_penalty

                if adj_score > best_adjusted_score:
                    best_adjusted_score = adj_score
                    best_combo = candidate
                    best_eval = evaluation

        if best_combo and best_eval:
            reused_notes = []
            for card in best_combo:
                cid = card["id"]
                prev_wears = wear_count.get(cid, 0)
                if prev_wears > 0:
                    if card["category"] in ("Footwear", "Accessory"):
                        reused_notes.append(f"♻️ Reused {card['category']} ({card['name']})")
                    else:
                        reused_notes.append(f"🧺 Post-Wash Reuse ({card['name']})")
                last_worn_day[cid] = day_idx
                wear_count[cid] = prev_wears + 1

            planned_outfits.append({
                "day_number": day_idx + 1,
                "day_label": f"Day {day_idx + 1} • {day_names[day_idx % 7]}",
                "outfit_name": f"{day_names[day_idx % 7]} {archetype.title()} Rotation",
                "archetype": archetype,
                "synergy_score": best_eval["synergy_score"],
                "harmony_summary": best_eval["harmony_summary"],
                "reuse_badges": reused_notes,
                "color_palette": best_eval["color_palette"],
                "cards": best_combo,
                "gemma_analysis": None
            })

    return planned_outfits


# --- IMAGE PROCESSING & SERPAPI ---
def process_photo_to_studio_asset(raw_bytes: bytes, use_ai_cutout: bool = True) -> dict:
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    img.thumbnail((700, 700))

    if use_ai_cutout and REMBG_AVAILABLE:
        try:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            cutout_bytes = rembg_remove(buf.getvalue())
            img = Image.open(io.BytesIO(cutout_bytes)).convert("RGBA")
        except Exception as e:
            print("rembg fallback:", e)

    small = img.copy()
    small.thumbnail((120, 120))
    opaque_pixels = [(r, g, b) for (r, g, b, a) in small.getdata() if a > 128]

    extracted_hex = ["#181A1F", "#EAB308", "#F5F5F5"]
    if opaque_pixels:
        pixel_img = Image.new("RGB", (len(opaque_pixels), 1))
        pixel_img.putdata(opaque_pixels)
        quantized = pixel_img.quantize(colors=4, method=Image.Quantize.MEDIANCUT)
        palette = quantized.getpalette()
        counts = sorted(quantized.getcolors(), reverse=True)
        hex_list = []
        for _, idx in counts[:3]:
            r, g, b = palette[idx * 3: idx * 3 + 3]
            hex_list.append(f"#{r:02X}{g:02X}{b:02X}")
        if hex_list:
            extracted_hex = hex_list

    out_buf = io.BytesIO()
    img.save(out_buf, format="PNG")
    b64_png = base64.b64encode(out_buf.getvalue()).decode("utf-8")
    return {"data_url": f"data:image/png;base64,{b64_png}", "hex_colors": extracted_hex}


def fetch_serpapi_image(query: str) -> dict:
    fallback_svg = "https://images.unsplash.com/photo-1556821840-3a63f95609a7?w=500&auto=format&fit=crop&q=60"
    if not SERPAPI_KEY or SERPAPI_KEY == "your_serpapi_key_here":
        return {
            "thumbnail": fallback_svg,
            "link": "#",
            "source": "Offline Preview"
        }
    try:
        params = {
            "engine": "google_images",
            "q": f"{query} isolated product studio flat lay",
            "api_key": SERPAPI_KEY,
            "num": 1,
            "ijn": 0
        }
        res = requests.get("https://serpapi.com/search.json", params=params, timeout=8)
        images = res.json().get("images_results", [])
        if images:
            return {
                "thumbnail": images[0].get("original") or images[0].get("thumbnail"),
                "link": images[0].get("link", "#"),
                "source": images[0].get("source", "SerpApi Studio Twin")
            }
    except Exception as e:
        print("SerpApi warning:", e)
    return {"thumbnail": fallback_svg, "link": "#", "source": "Default Preview"}


def serialize_item(item) -> dict:
    hex_list = item.get("hex_colors")
    if not hex_list or not isinstance(hex_list, list):
        hex_list = [item.get("hex_color", "#6366f1")]
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
        return [serialize_item(i) for i in wardrobe_col.find().sort("_id", -1)]
    if LOCAL_BACKUP_FILE.exists():
        return [serialize_item(i) for i in json.loads(LOCAL_BACKUP_FILE.read_text(encoding="utf-8"))]
    return []


def db_save_local(items: list):
    LOCAL_BACKUP_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def serve_ui():
    """Reads index.html and auto-cleans any accidental Markdown [url](url) corruption."""
    html_path = BASE_DIR / "static" / "index.html"
    raw_html = html_path.read_text(encoding="utf-8")
    clean_html = re.sub(r"\[(https?://[^\]]+)\]\(\1\)", r"\1", raw_html)
    return HTMLResponse(content=clean_html)


@app.get("/api/inventory")
def get_inventory():
    rules = load_meta_rules()
    return {
        "items": db_get_all(),
        "archetypes": rules.get("archetypes", {}),
        "rembg_available": REMBG_AVAILABLE
    }


@app.post("/api/seed")
def seed_wardrobe():
    """Seeds 11 multi-color clothes + reusable Watch & Sneakers for 3-7 Day Rotation."""
    u = "https://images.unsplash.com/"
    sample_clothes = [
        {
            "id": str(uuid.uuid4())[:8],
            "name": "Colorblock Zip Hoodie (Black/White/Mango)",
            "category": "Layer",
            "color": "Black / White / Mango Yellow",
            "hex_colors": ["#181A1F", "#F5F5F5", "#EAB308"],
            "style_vibe": "Streetwear / Everything",
            "image_url": u + "photo-1556821840-3a63f95609a7?w=500&auto=format&fit=crop&q=60",
            "is_clean": True,
            "is_banned": False
        },
        {
            "id": str(uuid.uuid4())[:8],
            "name": "Navy & Crimson Jersey Tee",
            "category": "Top",
            "color": "Navy / Crimson / Gold",
            "hex_colors": ["#1B263B", "#D90429", "#FFB703"],
            "style_vibe": "Sporty / Streetwear",
            "image_url": u + "photo-1576566588028-4147f3842f27?w=500&auto=format&fit=crop&q=60",
            "is_clean": True,
            "is_banned": False
        },
        {
            "id": str(uuid.uuid4())[:8],
            "name": "Ice Blue Striped Half-Sleeve Shirt",
            "category": "Top",
            "color": "Ice Blue / Crisp White",
            "hex_colors": ["#BFDBFE", "#FFFFFF"],
            "style_vibe": "Smart Casual / Date",
            "image_url": u + "photo-1596755094514-f87e34085b2c?w=500&auto=format&fit=crop&q=60",
            "is_clean": True,
            "is_banned": False
        },
        {
            "id": str(uuid.uuid4())[:8],
            "name": "Mustard Graphic Street Tee",
            "category": "Top",
            "color": "Mustard Gold / Black",
            "hex_colors": ["#E1AD01", "#181A1F"],
            "style_vibe": "Streetwear / Casual",
            "image_url": u + "photo-1521572163474-6864f9cf17ab?w=500&auto=format&fit=crop&q=60",
            "is_clean": True,
            "is_banned": False
        },
        {
            "id": str(uuid.uuid4())[:8],
            "name": "Matte Black Oversized Heavy Tee",
            "category": "Top",
            "color": "Pitch Black",
            "hex_colors": ["#181A1F", "#374151"],
            "style_vibe": "Monochrome / Everything",
            "image_url": u + "photo-1583743814966-8936f5b7be1a?w=500&auto=format&fit=crop&q=60",
            "is_clean": True,
            "is_banned": False
        },
        {
            "id": str(uuid.uuid4())[:8],
            "name": "Olive Relaxed Cargo Pants",
            "category": "Bottom",
            "color": "Olive Green",
            "hex_colors": ["#556B2F", "#3B4A20"],
            "style_vibe": "Utility / Everything",
            "image_url": u + "photo-1624378439575-d8705ad7ae80?w=500&auto=format&fit=crop&q=60",
            "is_clean": True,
            "is_banned": False
        },
        {
            "id": str(uuid.uuid4())[:8],
            "name": "Charcoal Black Slim Jeans",
            "category": "Bottom",
            "color": "Charcoal Black",
            "hex_colors": ["#1F2937", "#111827"],
            "style_vibe": "Versatile / Everything",
            "image_url": u + "photo-1542272604-787c3835535d?w=500&auto=format&fit=crop&q=60",
            "is_clean": True,
            "is_banned": False
        },
        {
            "id": str(uuid.uuid4())[:8],
            "name": "Heather Grey Athletic Joggers",
            "category": "Bottom",
            "color": "Heather Grey",
            "hex_colors": ["#6B7280", "#E5E7EB"],
            "style_vibe": "Cozy / Streetwear",
            "image_url": u + "photo-1552902865-b72c031ac5ea?w=500&auto=format&fit=crop&q=60",
            "is_clean": True,
            "is_banned": False
        },
        {
            "id": str(uuid.uuid4())[:8],
            "name": "Vintage Indigo Relaxed Denim",
            "category": "Bottom",
            "color": "Indigo Blue",
            "hex_colors": ["#2B4C7E", "#1B263B"],
            "style_vibe": "Classic / Daily",
            "image_url": u + "photo-1604176354204-9268737828e4?w=500&auto=format&fit=crop&q=60",
            "is_clean": True,
            "is_banned": False
        },
        {
            "id": str(uuid.uuid4())[:8],
            "name": "White & Black Low Court Sneakers",
            "category": "Footwear",
            "color": "Crisp White / Black",
            "hex_colors": ["#F9FAFB", "#181A1F"],
            "style_vibe": "Clean / Everything",
            "image_url": u + "photo-1549298916-b41d501d3772?w=500&auto=format&fit=crop&q=60",
            "is_clean": True,
            "is_banned": False
        },
        {
            "id": str(uuid.uuid4())[:8],
            "name": "Matte Black Sport Chronograph Watch",
            "category": "Accessory",
            "color": "Matte Black / Silver",
            "hex_colors": ["#181A1F", "#9CA3AF"],
            "style_vibe": "Daily / Everything",
            "image_url": u + "photo-1524805444758-089113d48a6d?w=500&auto=format&fit=crop&q=60",
            "is_clean": True,
            "is_banned": False
        }
    ]
    if wardrobe_col is not None:
        wardrobe_col.delete_many({})
        wardrobe_col.insert_many(sample_clothes)
    else:
        db_save_local(sample_clothes)
    return {"message": "Seeded 11 items (including reusable Watch & Sneakers)!"}


@app.post("/api/analyze-photo")
async def analyze_uploaded_photo(photo: UploadFile = File(...)):
    raw_bytes = await photo.read()
    return process_photo_to_studio_asset(raw_bytes, use_ai_cutout=True)


@app.post("/api/inventory/add")
async def add_clothing_item(
    name: str = Form(...),
    category: str = Form(...),
    color: str = Form(...),
    hex_colors_json: str = Form('["#6366f1"]'),
    style_vibe: str = Form("Everything"),
    asset_mode: str = Form("serpapi_twin"),
    photo: UploadFile = File(None)
):
    try:
        hex_colors = json.loads(hex_colors_json)
    except Exception:
        hex_colors = ["#6366f1"]

    if asset_mode == "serpapi_twin" or not (photo and photo.filename):
        serp_res = fetch_serpapi_image(f"{color} {name} {category}")
        img_data_url = serp_res["thumbnail"]
    else:
        raw_bytes = await photo.read()
        processed = process_photo_to_studio_asset(raw_bytes, use_ai_cutout=True)
        img_data_url = processed["data_url"]

    doc = {
        "id": str(uuid.uuid4())[:8],
        "name": name,
        "category": category,
        "color": color,
        "hex_colors": hex_colors,
        "hex_color": hex_colors[0],
        "style_vibe": style_vibe,
        "image_url": img_data_url,
        "is_clean": True,
        "is_banned": False
    }
    if wardrobe_col is not None:
        wardrobe_col.insert_one(doc)
    else:
        items = db_get_all()
        items.insert(0, doc)
        db_save_local(items)
    return {"status": "added"}


@app.post("/api/inventory/toggle-clean/{item_id}")
def toggle_clean_status(item_id: str):
    if wardrobe_col is not None:
        query = {"_id": ObjectId(item_id)} if ObjectId.is_valid(item_id) else {"id": item_id}
        item = wardrobe_col.find_one(query)
        if item:
            wardrobe_col.update_one(query, {"$set": {"is_clean": not item.get("is_clean", True)}})
    else:
        items = db_get_all()
        for i in items:
            if str(i.get("id")) == item_id:
                i["is_clean"] = not i.get("is_clean", True)
        db_save_local(items)
    return {"status": "toggled_clean"}


@app.post("/api/inventory/toggle-ban/{item_id}")
def toggle_ban_status(item_id: str):
    if wardrobe_col is not None:
        query = {"_id": ObjectId(item_id)} if ObjectId.is_valid(item_id) else {"id": item_id}
        item = wardrobe_col.find_one(query)
        if item:
            wardrobe_col.update_one(query, {"$set": {"is_banned": not item.get("is_banned", False)}})
    else:
        items = db_get_all()
        for i in items:
            if str(i.get("id")) == item_id:
                i["is_banned"] = not i.get("is_banned", False)
        db_save_local(items)
    return {"status": "toggled_ban"}


@app.delete("/api/inventory/{item_id}")
def delete_item(item_id: str):
    if wardrobe_col is not None:
        query = {"_id": ObjectId(item_id)} if ObjectId.is_valid(item_id) else {"id": item_id}
        wardrobe_col.delete_one(query)
    else:
        items = [i for i in db_get_all() if str(i.get("id")) != item_id]
        db_save_local(items)
    return {"status": "deleted"}


# --- INSTANT WEEKLY OUTFIT PLANNER ENDPOINT (3 TO 7 DAYS + WASH COOLDOWN) ---
@app.post("/api/plan-weekly-outfits")
def plan_weekly_outfits(payload: dict):
    t0 = time.perf_counter()
    archetype = payload.get("archetype", "balanced")
    num_days = int(payload.get("num_days", 5))
    wash_cooldown = int(payload.get("wash_cooldown", 2))

    all_items = db_get_all()
    eligible = [i for i in all_items if i.get("is_clean", True) and not i.get("is_banned", False)]

    outfits = plan_weekly_outfits_engine(
        clean_unbanned=eligible,
        archetype=archetype,
        num_days=max(3, min(7, num_days)),
        wash_cooldown_days=max(1, min(3, wash_cooldown))
    )
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    if not outfits:
        raise HTTPException(
            status_code=400,
            detail="Not enough Clean & Unbanned Tops/Bottoms! Unban items or click 'Seed 11-Item Closet'."
        )

    return {
        "compute_time_ms": elapsed_ms,
        "num_days": num_days,
        "wash_cooldown": wash_cooldown,
        "archetype": archetype,
        "decks": outfits
    }


@app.post("/api/analyze-deck")
def analyze_deck_with_gemma(payload: dict):
    cards = payload.get("cards", [])
    archetype = payload.get("archetype", "balanced")
    card_summary = ", ".join([f"{c['name']} ({c['color']})" for c in cards])

    prompt = f"""You are a smart Wardrobe Stylist powered by Google Gemma 2.
Analyze this outfit ({archetype} style): {card_summary}.
Reply ONLY in valid JSON:
{{
  "battle_strategy": "2 concise sentences explaining why this color combination works effortlessly.",
  "unlock_item_name": "1 specific new clothing piece or accessory to buy that pairs with this outfit",
  "unlock_search_query": "mens minimalist streetwear jacket or accessory flat lay",
  "unlock_reason": "1 sentence on how it expands the wardrobe."
}}"""

    try:
        res = requests.post(
            OLLAMA_URL,
            json={
                "model": GEMMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "keep_alive": "24h",
                "options": {"temperature": 0.4, "num_ctx": 768, "num_predict": 180}
            },
            timeout=60
        )
        raw = res.json().get("response", "{}")
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().strip("`")
        s, e = cleaned.find("{"), cleaned.rfind("}")
        data = json.loads(cleaned[s:e+1] if s != -1 and e != -1 else "{}")
    except Exception:
        data = {
            "battle_strategy": f"Effortless {archetype} synergy: your multi-color top provides visual contrast while dark neutral bottoms keep the silhouette clean.",
            "unlock_item_name": "Matte Black Minimalist Overshirt",
            "unlock_search_query": "mens minimalist matte black overshirt flat lay",
            "unlock_reason": "Adds a versatile layer that bridges your graphic tees and cargos."
        }

    visual = fetch_serpapi_image(data.get("unlock_search_query", "mens streetwear jacket flat lay"))
    return {
        "battle_strategy": data.get("battle_strategy", ""),
        "unlock_card": {
            "item_name": data.get("unlock_item_name", "Minimalist Layer"),
            "reason": data.get("unlock_reason", ""),
            "image_url": visual["thumbnail"],
            "shop_link": visual["link"]
        }
    }