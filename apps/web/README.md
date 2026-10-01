# Interactive Research Decks

> A spatial 3D card triage and literature exploration system designed to transform overwhelming lists of papers and articles into tactile, finite physical decks.

[![React](https://img.shields.io/badge/React-19.0-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-v4-38B2AC?logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![Motion](https://img.shields.io/badge/Motion-12.2-FF0055?logo=framer&logoColor=white)](https://motion.dev/)
[![Vite](https://img.shields.io/badge/Vite-6.2-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)

---

## 1. Overview & Design Philosophy

Modern digital interfaces often present search results and research discoveries as infinite, flat, scrolling feeds. This creates cognitive fatigue and robs users of a physical sense of progress, deck boundaries, and spatial orientation.

**Interactive Research Decks** reimagines literature triage through physical spatial metaphors:
- **Finite Deck Boundaries**: Every query returns a defined deck with explicit **Head** (Card 1) and **Tail** (Card $N$) anchors, eliminating infinite scroll fatigue.
- **Tactile Progression**: Viewed items cleanly recede into an underlying depth tray ("sent back"), while upcoming items remain stacked in an upper tail peeking above the head.
- **Physical Triage Workflows**: Quickly sort candidates into **Kept** (for deep dive) or **Discarded** bins using single-keystroke shortcuts (`K`/`D`), direct swipe actions, or procedural audio feedback.
- **High-Density Legibility**: High-contrast, clean light-mode typography pairing crisp sans-serif headings with clear domain provenance, match percentage, and read times.

---

## 2. Architecture & How It Works

### 2.1 Spatial 3D Deck Engine (`VerticalCascadingHand.tsx`)
The vertical cascading view creates a 3D turntable using CSS 3D transforms (`perspective: 1200px`, `transformStyle: 'preserve-3d'`) combined with hardware-accelerated declarative animations via `motion/react`:

$$\begin{aligned}
\text{Active Head} (offset = 0) &: y = 36\text{px},\; \text{rotX} = 0^{\circ},\; z = 30\text{px},\; \text{scale} = 1.00,\; z\text{Index} = 50 \\
\text{Upper Tail} (offset > 0) &: y = 36 - 68 \cdot offset\text{px},\; \text{rotX} = \min(3.5 \cdot offset, 14^{\circ}),\; z = -20 \cdot offset\text{px} \\
\text{Viewed Tray} (offset < 0) &: y = 36 + 52 \cdot |offset|\text{px},\; \text{rotX} = -5 \cdot |offset|^{\circ},\; z = -35 \cdot |offset|\text{px}
\end{aligned}$$

#### Key Engineering Decisions:
1. **Zero CSS-JS Transition Clashing**: Removed CSS `transition-all` declarations on animated cards. When JS drives frame-by-frame 3D matrix transforms, CSS transitions fight the interpolation and cause micro-stutter. Motion styles are declared purely in `style` with `willChange: 'transform, opacity'`.
2. **Cubic-Bezier Easing Curve**: Replaced oscillatory springs with an `ease: [0.25, 1, 0.5, 1]` deceleration curve over 320ms, providing a fluid gliding feel with zero overshoot or jumpiness.
3. **Trackpad Inertia Dampening**: High-precision trackpads fire hundreds of delta events per second after a swipe. A calibrated 300ms lock prevents trackpad inertia from triggering rapid, jarring double-skips mid-flight.

---

### 2.2 Alternative Exploration Modes
- **Horizontal Ribbon Deck (`HorizontalRibbonDeck.tsx`)**: Lateral stream with horizontal card overlap, edge fade gradients, and smooth horizontal wheel snapping.
- **3D Cover Flow (`CoverFlowDeck.tsx`)**: Classic angled perspective carousel featuring center card elevation, bilateral angled rotation ($\pm 35^{\circ}$), and depth attenuation.

---

### 2.3 Synthesized Zero-Asset Haptics & Audio (`src/utils/haptics.ts`)
Rather than loading heavyweight audio asset files (`.mp3` / `.wav`), the application generates procedural mechanical audio directly via the native browser **Web Audio API**:
- **Snap**: Triangle wave sweeping from 320Hz down to 140Hz with an exponential decay ramp (45ms).
- **Slide**: Low-frequency sine wave glide (180Hz $\rightarrow$ 90Hz) simulating a card moving across cardstock.
- **Keep**: High chime (440Hz $\rightarrow$ 880Hz) providing positive tactile confirmation.
- **Discard**: Low damped thud (160Hz $\rightarrow$ 60Hz) confirming dismissal.
- **Haptics**: Leverages `navigator.vibrate([15])` on supported mobile devices for physical impulse feedback.

---

### 2.4 Deep Reader Pane (`ReaderView.tsx`)
Selecting any card opens an in-depth reader modal with:
- Full abstract and multi-paragraph article synthesis.
- Bulleted key findings with structured iconography.
- Direct classification tags and source metadata (author, institution, publication date).
- Instant triage actions (Keep / Discard / Close) with keyboard escape handling.

---

## 3. Tech Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Runtime & Framework** | [React 19](https://react.dev/) | Modern concurrent UI architecture and state primitives |
| **Language** | [TypeScript 5.8](https://www.typescriptlang.org/) | Strict type safety, shared interfaces, and compile-time verification |
| **Animation Engine** | [Motion](https://motion.dev/) (`motion/react` v12) | 60/120fps hardware-accelerated 3D transforms & gesture orchestration |
| **Styling** | [Tailwind CSS v4](https://tailwindcss.com/) | Utility-first styling with `@tailwindcss/vite` engine |
| **Icons** | [Lucide React](https://lucide.dev/) | Clean, accessible vector icons |
| **Tactile Feedback** | Web Audio API + Vibration API | Low-latency, zero-asset synthesized sound & physical haptics |
| **Build Tooling** | [Vite 6](https://vitejs.dev/) | Lightning-fast development server and optimized production bundling |

---

## 4. Project Structure

```text
├── index.html                    # Application entry HTML with SEO and viewport metadata
├── metadata.json                 # AI Studio configuration & permissions manifest
├── package.json                  # Project dependencies, scripts, and engine specifications
├── tsconfig.json                 # TypeScript compiler configuration (strict mode)
├── vite.config.ts                # Vite build configuration with Tailwind CSS v4 plugin
└── src/
    ├── main.tsx                  # React root mount entry point
    ├── App.tsx                   # Main state coordinator (filtering, triage bins, deck modes)
    ├── index.css                 # Tailwind v4 import and global font declarations
    ├── types.ts                  # Domain models (ResearchCard, DeckMode, DeckState)
    ├── components/
    │   ├── VerticalCascadingHand.tsx  # Primary 3D cascading deck with physical upper tail
    │   ├── HorizontalRibbonDeck.tsx   # Lateral ribbon card stream
    │   ├── CoverFlowDeck.tsx          # 3D Cover Flow angled perspective carousel
    │   ├── ReaderView.tsx             # Full distraction-free paper reader pane
    │   ├── LeftSidebar.tsx            # Navigation, mode selector, category filters, haptic toggles
    │   └── FloatingTray.tsx           # Collapsible drawer for Kept and Discarded card collections
    ├── data/
    │   └── researchData.ts       # Structured research paper data with findings & metadata
    └── utils/
        └── haptics.ts            # Procedural Web Audio API synthesizer and vibration engine
```

---

## 5. Keyboard Navigation & Shortcuts

| Key | Action | Context |
| :--- | :--- | :--- |
| <kbd>↓</kbd> / <kbd>→</kbd> | Next card in deck | All deck modes |
| <kbd>↑</kbd> / <kbd>←</kbd> | Previous card in deck | All deck modes |
| <kbd>Enter</kbd> / <kbd>Space</kbd> | Open full reader view | Active card in deck |
| <kbd>K</kbd> / <kbd>S</kbd> | **Keep** card to saved tray | Active card or reader |
| <kbd>D</kbd> | **Discard** card from deck | Active card or reader |
| <kbd>Esc</kbd> | Close reader / Dismiss tray | Active modal or drawer |

---

## 6. Local Setup & Installation Guide

This repository contains a full-stack system: a **Node.js/Express** backend with **Vite & React 19** on the frontend, integrating directly with a local or remote **SearXNG** metasearch engine and an optional **Playwright** scraping agent.

### 6.1 Prerequisites

Ensure you have the following installed on your computer:
- **Node.js**: v18.0.0 or higher ([Download](https://nodejs.org/))
- **npm**: v9.0.0 or higher
- **Git**: For cloning the repository
- **Docker** *(Optional, recommended)*: For running a local SearXNG metasearch instance
- **Python 3.9+** *(Optional)*: Only if you intend to run the standalone `scripts/research_agent.py` script

---

### 6.2 Step-by-Step Local Setup

#### Step 1: Clone the Repository
```bash
git clone https://github.com/<your-username>/interactive-research-decks.git
cd interactive-research-decks
```

#### Step 2: Install Node.js Dependencies
```bash
npm install
```

#### Step 3: Configure Environment Variables
Copy the `.env.example` file to create your local `.env`:
```bash
cp .env.example .env
```
Inspect `.env` and verify the settings:
```env
# URL for your SearXNG metasearch endpoint (default: http://localhost:8080/search)
SEARXNG_URL=http://localhost:8080/search

# (Optional) Gemini API Key if testing AI capabilities in the future
GEMINI_API_KEY=
```

---

### 6.3 Setting Up SearXNG Locally

The research deck queries SearXNG via `/api/search` with automated pagination. You can run SearXNG locally using Docker in two minutes.

#### Option A: Quick Docker Container (Recommended)
```bash
docker run -d --name searxng \
  -p 8080:8080 \
  -e "SEARXNG_BASE_URL=http://localhost:8080/" \
  -e "INSTANCE_NAME=research-deck" \
  searxng/searxng
```

#### Option B: Enable JSON Output in SearXNG
> **Critical Requirement**: SearXNG requires JSON output to be explicitly enabled in its `settings.yml` for API queries to function.

If you are mounting a custom `settings.yml` or running SearXNG via docker-compose:
```yaml
# In your searxng/settings.yml:
search:
  formats:
    - html
    - json   # <-- Ensure 'json' format is included!
```

#### Step 4: Verify SearXNG is Running
Test the local endpoint with `curl`:
```bash
curl "http://localhost:8080/search?q=quantum+computing&format=json"
```
If this returns a JSON payload with a `"results"` array, your local SearXNG instance is ready.

*(Note: If SearXNG is not running or offline, the application automatically uses a built-in query-aware fallback generator so you can still test and navigate the 3D decks without interruption).*

---

### 6.4 Running the Web Application

#### Start the Development Server
```bash
npm run dev
```
- The backend Express server boots on `http://localhost:3000`
- Vite's middleware compiles and serves the React frontend with HMR
- Open [http://localhost:3000](http://localhost:3000) in your web browser

#### Verify Health & Connectivity
```bash
# Verify Express and SearXNG configuration
curl http://localhost:3000/api/health
```
Response:
```json
{
  "status": "ok",
  "searxngUrl": "http://localhost:8080/search",
  "features": ["searxng_paginated_search", "as_is_page_proxy", "concurrent_batching"]
}
```

---

### 6.5 (Optional) Running the Python Research Agent

If you want to run batch automated crawls using the included standalone Python Playwright agent (`scripts/research_agent.py`):

```bash
# 1. Create and activate a Python virtual environment
python3 -m venv venv

# On macOS/Linux:
source venv/bin/activate

# On Windows:
# .\venv\Scripts\activate

# 2. Install required Python packages
pip install httpx playwright rich

# 3. Install Playwright browser binaries
playwright install chromium

# 4. Execute a batch research query
python scripts/research_agent.py "distributed consensus algorithms" --limit 10 --output results.json
```

---

### 6.6 Production Build & Deployment

To verify production bundling and run the compiled CommonJS standalone server:

```bash
# 1. Compile client assets to dist/ and bundle server.ts to dist/server.cjs
npm run build

# 2. Start the production Node.js server
npm start
```
The production server will listen on `http://localhost:3000`.

---

### 6.7 Troubleshooting & FAQ

- **Port 3000 already in use**:
  Kill any lingering process using port 3000:
  - macOS/Linux: `lsof -ti:3000 | xargs kill -9`
  - Windows: `netstat -ano | findstr :3000` then `taskkill /PID <PID> /F`

- **SearXNG returns 403 or 404 on API requests**:
  Ensure that `json` is enabled in `formats` under `search` in your SearXNG `settings.yml`. Restart the SearXNG container after modifying settings.

- **External pages fail to render in "Live Page (As-Is)"**:
  Certain high-security websites (e.g. Google Search, Twitter/X) deploy frame-busting scripts that refuse iframe execution. For these sites, click **Open Tab** in the navigation bar to inspect the source page directly.

---

## 7. Engineering Best Practices Implemented

- **Performance-First Transforms**: Uses only `translate3d`, `rotateX`, `scale`, and `opacity` to avoid triggering browser layout/reflow cycles during transitions.
- **Defensive Wheel Handling**: Uses passive event prevention and delta locks to eliminate jitter on trackpads with inertia physics.
- **Zero Asset Latency**: Audio feedback does not require network fetches for sound files; audio nodes are constructed and scheduled via `AudioContext` in sub-millisecond time.
- **Accessibility (a11y)**: Complete keyboard navigation, explicit ARIA roles (`role="region"`, `role="listitem"`), descriptive `aria-label` attributes, and WCAG AA compliant contrast ratios across all cards.
