import os
import time
import streamlit as st
from db import (
    init_db, add_item, get_all_items, get_clean_items,
    toggle_laundry_status, mark_all_clean, delete_item, seed_demo_wardrobe
)
from ai_engine import check_ollama_health, auto_tag_image, generate_outfit_deck

st.set_page_config(
    page_title="SlothCloset | Local AI Wardrobe Deck-Builder",
    page_icon="🦥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Dark UI Styling for Card Decks
st.markdown("""
<style>
    .deck-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .clean-badge {
        background-color: #238636;
        color: white;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
    }
    .wet-badge {
        background-color: #da3633;
        color: white;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
    }
    .unlock-box {
        background: linear-gradient(135deg, #1f242d 0%, #2d1f3d 100%);
        border: 1px solid #8957e5;
        border-radius: 12px;
        padding: 18px;
        margin-top: 16px;
    }
</style>
""", unsafe_allow_html=True)

init_db()
os.makedirs("wardrobe_images", exist_ok=True)

# --- SIDEBAR: OLLAMA STATUS & LAZY CONTROLS ---
with st.sidebar:
    st.title("🦥 SlothCloset")
    st.caption("100% Offline, Open-Weight Wardrobe Deck Builder. Zero Cloud Uploads.")
    
    health = check_ollama_health()
    if health["online"]:
        st.success("🟢 Local Ollama Engine: Online")
        installed_models = health["models"] if health["models"] else ["llama3.2:3b"]
    else:
        st.error("🔴 Ollama Offline! Run `ollama serve` in terminal.")
        installed_models = ["llama3.2:3b", "moondream"]

    default_text_idx = next((i for i, m in enumerate(installed_models) if "llama" in m or "qwen" in m), 0)
    selected_text_model = st.selectbox("Deck Builder LLM (Local)", installed_models, index=default_text_idx)
    
    default_vis_idx = next((i for i, m in enumerate(installed_models) if "moondream" in m or "vision" in m), 0)
    selected_vision_model = st.selectbox("Vision Auto-Tagger (Optional)", installed_models, index=default_vis_idx)

    st.divider()
    st.subheader("⚡ Sloth Shortcuts")
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if st.button("🌱 Seed Demo Closet", use_container_width=True, help="Instantly add 8 sample college items"):
            seed_demo_wardrobe()
            st.toast("8 demo clothes added to your closet!", icon="🦥")
            st.rerun()
    with col_s2:
        if st.button("🧺 Wash All Clothes", use_container_width=True, help="Mark every item as Clean & Ready"):
            mark_all_clean()
            st.toast("Laundry day complete! All items marked Clean.", icon="✨")
            st.rerun()

    st.divider()
    st.markdown(
        "**Why Local Open-Weight AI?**\n"
        "- **Privacy Guard:** Bedroom & laundry photos never leave your laptop.\n"
        "- **Zero Cost:** Unlimited daily outfit generations with $0 API bills.\n"
        "- **Offline Ready:** Works in hostel dead-zones with zero Wi-Fi."
    )

# --- MAIN TABS ---
tab_deck, tab_closet, tab_add = st.tabs([
    "🃏 1. Outfit Deck Builder",
    "🧺 2. Closet & Laundry Toggles",
    "📸 3. Add Clothes (Vision AI)"
])

all_items = get_all_items()
clean_items = get_clean_items()

# ==========================================
# TAB 1: OUTFIT DECK BUILDER (CLASH ROYALE STYLE)
# ==========================================
with tab_deck:
    st.header("🃏 Build Today's Outfit Deck")
    st.write(f"Currently **{len(clean_items)} Clean Items** available out of **{len(all_items)} total** in your closet.")

    if len(clean_items) < 2:
        st.warning("Your clean closet is looking bare! Click **'🌱 Seed Demo Closet'** in the left sidebar or mark items clean in Tab 2.")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            occasion = st.selectbox(
                "🎯 Where are you going?",
                [
                    "College Lectures (Survive the Day)",
                    "Casual Hangout / Cafe",
                    "Date / Looking Presentable",
                    "Hackathon / 24hr Coding Grind",
                    "Party / Night Out"
                ]
            )
        with c2:
            weather = st.selectbox(
                "🌦️ Weather Vibe",
                ["Pleasant / Mild", "Hot & Humid", "Chilly / AC Lab", "Monsoon / Rainy"]
            )
        with c3:
            laziness = st.slider("🦥 Sloth Meter (Laziness Level)", 1, 10, 8)

        if st.button("🎲 Generate Optimal Outfit Deck (Local LLM)", type="primary", use_container_width=True):
            with st.spinner(f"Running local `{selected_text_model}` to compute color synergy..."):
                deck = generate_outfit_deck(
                    clean_items=clean_items,
                    occasion=occasion,
                    laziness_level=laziness,
                    weather=weather,
                    text_model=selected_text_model
                )

            if "error" in deck:
                st.error(deck["error"])
            else:
                st.subheader(f"🏆 Deck: {deck.get('deck_name', 'The Effortless Sloth Combo')}")
                
                m1, m2 = st.columns([1, 3])
                with m1:
                    score = deck.get("synergy_score", 85)
                    st.metric("⚡ Deck Synergy Score", f"{score} / 100")
                with m2:
                    st.info(f"**Color & Vibe Check:** {deck.get('color_harmony_reason', '')}")
                    st.success(f"**Sloth Verdict:** {deck.get('sloth_justification', '')}")

                st.markdown("#### 👕 Selected Cards in This Outfit:")
                picked_ids = deck.get("selected_item_ids", [])
                picked_items = [item for item in clean_items if item["id"] in picked_ids]
                
                # Fallback if model returned slightly mismatched IDs
                if not picked_items:
                    picked_items = clean_items[:3]

                cols = st.columns(len(picked_items))
                for idx, p_item in enumerate(picked_items):
                    with cols[idx]:
                        st.markdown(f"""
                        <div class="deck-card">
                            <span class="clean-badge">{p_item['category']}</span>
                            <h4 style="margin-top:10px; margin-bottom:4px;">{p_item['name']}</h4>
                            <p style="color:#8b949e; margin:0;">🎨 Color: <b>{p_item['color']}</b></p>
                            <p style="color:#8b949e; margin:0;">✨ Vibe: {p_item['style_vibe']}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        if p_item["image_path"] and os.path.exists(p_item["image_path"]):
                            st.image(p_item["image_path"], use_container_width=True)

                # Unlock Card Feature
                unlock = deck.get("unlock_card", {})
                if unlock:
                    st.markdown(f"""
                    <div class="unlock-box">
                        <h4 style="margin:0 0 8px 0; color:#d2a8ff;">🔓 Next Wardrobe Card to Unlock: {unlock.get('missing_item', 'Neutral Layer')}</h4>
                        <p style="margin:0; color:#c9d1d9;"><b>Deck Expansion Potential:</b> {unlock.get('combos_unlocked', '')}</p>
                    </div>
                    """, unsafe_allow_html=True)

# ==========================================
# TAB 2: CLOSET INVENTORY & LAUNDRY TOGGLES
# ==========================================
with tab_closet:
    st.header("🧺 Your Closet & 1-Click Laundry Toggles")
    st.caption("Toggle clothes between **Clean / Ready** and **In Laundry / Wet** so the AI never recommends dirty clothes.")

    if not all_items:
        st.info("Your closet is empty! Use the **Seed Demo Closet** button on the sidebar or add items in Tab 3.")
    else:
        grid_cols = st.columns(3)
        for index, item in enumerate(all_items):
            with grid_cols[index % 3]:
                status_badge = '<span class="clean-badge">✅ Clean & Ready</span>' if item["is_clean"] else '<span class="wet-badge">🌊 In Laundry / Wet</span>'
                st.markdown(f"""
                <div class="deck-card">
                    {status_badge}
                    <h4 style="margin-top:10px; margin-bottom:4px;">{item['name']}</h4>
                    <p style="color:#8b949e; font-size:0.9rem; margin:0;">
                        📂 {item['category']} | 🎨 {item['color']} | ✨ {item['style_vibe']}
                    </p>
                </div>
                """, unsafe_allow_html=True)
                
                if item["image_path"] and os.path.exists(item["image_path"]):
                    st.image(item["image_path"], use_container_width=True)

                b_col1, b_col2 = st.columns([3, 1])
                with b_col1:
                    btn_label = "Toss in Laundry 🧺" if item["is_clean"] else "Mark Dry & Clean ✨"
                    if st.button(btn_label, key=f"toggle_{item['id']}", use_container_width=True):
                        toggle_laundry_status(item["id"], item["is_clean"])
                        st.rerun()
                with b_col2:
                    if st.button("🗑️", key=f"del_{item['id']}", help="Delete item"):
                        delete_item(item["id"])
                        st.rerun()

# ==========================================
# TAB 3: ADD CLOTHES (LOCAL VISION AUTO-TAGGER)
# ==========================================
with tab_add:
    st.header("📸 Add Clothes to Local Storage")
    st.write("Upload a photo to auto-extract tags with your local vision model, or add items manually.")

    uploaded_file = st.file_uploader("Drop a photo of your shirt, pants, or sneakers (Stored 100% locally)", type=["jpg", "jpeg", "png", "webp"])

    if "draft_item" not in st.session_state:
        st.session_state.draft_item = {
            "name": "",
            "category": "Top",
            "color": "",
            "style_vibe": "Casual / Streetwear"
        }

    if uploaded_file is not None:
        img_col, action_col = st.columns([1, 2])
        with img_col:
            st.image(uploaded_file, caption="Local Preview", use_container_width=True)
        with action_col:
            if st.button("🔍 Auto-Tag Photo with Local Vision AI", type="secondary"):
                with st.spinner(f"Analyzing garment locally with `{selected_vision_model}`..."):
                    tags = auto_tag_image(uploaded_file.getvalue(), vision_model=selected_vision_model)
                    st.session_state.draft_item = tags
                    if "error" in tags:
                        st.warning(f"Vision model note: {tags['error']}. You can still edit tags manually below!")
                    else:
                        st.success("Auto-tagged locally! Verify or save below.")

    with st.form("add_garment_form"):
        name_val = st.text_input("Garment Name", value=st.session_state.draft_item.get("name", ""), placeholder="e.g., Mustard Yellow Graphic Tee")
        
        categories = ["Top", "Bottom", "Layer / Jacket", "Footwear", "Accessory"]
        default_cat = st.session_state.draft_item.get("category", "Top")
        cat_idx = categories.index(default_cat) if default_cat in categories else 0
        cat_val = st.selectbox("Category", categories, index=cat_idx)
        
        color_val = st.text_input("Primary Color", value=st.session_state.draft_item.get("color", ""), placeholder="e.g., Olive Green")
        vibe_val = st.text_input("Style Vibe", value=st.session_state.draft_item.get("style_vibe", ""), placeholder="e.g., Casual / College")

        submitted = st.form_submit_button("💾 Save to Local Closet", type="primary")
        if submitted:
            if not name_val or not color_val:
                st.error("Give it a quick name and color first!")
            else:
                saved_path = ""
                if uploaded_file is not None:
                    ext = uploaded_file.name.split(".")[-1]
                    filename = f"item_{int(time.time())}.{ext}"
                    saved_path = os.path.join("wardrobe_images", filename)
                    with open(saved_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                add_item(name_val, cat_val, color_val, vibe_val, saved_path)
                st.success(f"Added **{name_val}** to your closet!")
                st.session_state.draft_item = {"name": "", "category": "Top", "color": "", "style_vibe": "Casual"}
                time.sleep(0.5)
                st.rerun()