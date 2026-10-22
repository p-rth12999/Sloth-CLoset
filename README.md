🎯 The Problem
Every morning comes with the exact same friction: staring into a dark wardrobe, suffering from choice paralysis, and wasting mental energy trying to figure out what pants go with what shirt. Existing wardrobe apps are bloated, invasive, and require sending personal photos of your clothes and room to third-party cloud servers.

💡 The Solution: SlothCloset Studio
Inspired by Clash Royale deck-building systems and RoyaleAPI asset management, SlothCloset treats your wardrobe like a card game deck. It lets you build a Weekly Outfit Rotation in under a millisecond using offline heuristic math, features a Ban/Skip List Veto, handles Wash-Cycle Cooldowns, and leverages Google Gemma 2 (via Ollama) for deep local AI styling advice.

✨ Key Features
🃏 RoyaleAPI-Style Weekly Rotation: Automatically plans 3 to 7 days of unique non-overlapping outfits at once.

⚡ Sub-Millisecond Python Heuristic Graph: Zero-LLM latency for the core color-matching engine (~0.5ms compute time).

🧺 Smart Wash-Cycle Cooldown: Configurable 1–3 day laundry/rest buffer for tops and bottoms, while accessories and footwear (watches, sneakers) automatically reuse daily.

🚫 Skip & Veto List: Temporarily ban any clothing card from being drafted if you don't feel like wearing it today.

🎨 Multi-Color Swatch Engine: Supports multi-color garments (e.g., a Black, White, and Mango Yellow hoodie) and auto-extracts dominant HEX codes from uploaded pictures.

✂️ Local AI Cutout & Studio Twins: Strips messy photo backgrounds locally using open-weight rembg (U2Net) or pulls clean studio catalog twins via SerpApi.

🧠 Gemma 2 Tactical AI Stylist: Optional, non-blocking local AI assistant that writes witty Clash Royale-style battle reports for your outfits and recommends a "5th-Card Unlock" shopping item.

🏗️ System Architecture
Plaintext
┌───────────────────────────┐         ┌───────────────────────────┐
│     Tailwind + Alpine     │ ──────> │       FastAPI (Python)    │
│    (Dark Studio UI)       │         │  (Hybrid Atlas/Local JSON)│
└───────────────────────────┘         └─────────────┬─────────────┘
                                                    │
                 ┌──────────────────────────────────┴──────────────────────────────────┐
                 ▼                                                                     ▼
    ┌───────────────────────────┐                                         ┌───────────────────────────┐
    │   Python Heuristic Engine │                                         │    Local Ollama (Gemma 2) │
    │    (0.001s Duel Solver)   │                                         │   (Optional Strategy AI)  │
    └───────────────────────────┘                                         └───────────────────────────┘
🛠️ Tech Stack & Hacktoberfest Prize Alignment
Backend & API: Python, FastAPI, Uvicorn, PyMongo

Frontend: Single-Page App with Tailwind CSS & Alpine.js

Local Open-Weight AI: Google Gemma 2 (gemma2:2b) running locally via Ollama (Best Use of Gemma track)

Data Layer: MongoDB Atlas M0 Cluster + Local JSON fallback (Best Use of MongoDB Atlas track)

Visuals & Search: SerpApi Google Images API for clean studio catalog twins (Best Use of SerpApi track)

Edge Processing: rembg (U2Net) for local image background removal

🚀 Getting Started Locally (100% Offline-First)
1. Clone the Repository
Bash
git clone https://github.com/YOUR_USERNAME/SlothCloset.git
cd SlothCloset
2. Set Up Python Environment
Bash
python -m venv venv
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1
# On macOS/Linux:
# source venv/bin/activate

pip install fastapi uvicorn pymongo python-dotenv python-multipart requests pillow rembg onnxruntime
3. Configure Your .env File
Create a .env file in the root directory:

Code snippet
MONGO_URI="mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority"
SERPAPI_KEY="your_serpapi_key_here"
GEMMA_MODEL="gemma2:2b"
(Note: If you leave MONGO_URI blank or skip MongoDB Atlas, the app automatically falls back to local JSON storage!)

4. Ensure Local Ollama is Running
Make sure you have Ollama installed and Gemma 2 pulled:

Bash
ollama pull gemma2:2b
ollama serve
5. Launch the Server
Bash
uvicorn main:app --reload
Open http://127.0.0.1:8000 in your browser, click 🌱 Seed 11-Item Closet, and enjoy your automated weekly wardrobe rotation!