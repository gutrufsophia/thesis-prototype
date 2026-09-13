# Comprehensive Context Guide for IDE Agent: CulturaEduca Health Storytelling Engine

## 1. Project Identity & Architecture Baseline
This project is an advanced Software Engineering thesis (TCC) aimed at developing a spatial Data Storytelling prototype[cite: 8]. 
**Crucial Context:** The host platform, CulturaEduca, is an existing participatory Geographic Information System (GIS) that already maps social, cultural, and educational units[cite: 9]. This thesis does *not* build the platform from scratch. Instead, it develops an isolated, high-performance prototype dedicated exclusively to a new **Health Data Layer**, which will subsequently be integrated into the legacy production environment[cite: 8].

The prototype operates on a strict **Zero-Cost, High-Performance Architecture**:
*   **Backend & Spatial Engine:** C++17 (using `libcurl` for HTTP and `libpqxx` for database connections).
*   **Database:** Supabase (PostgreSQL + PostGIS).
*   **LLM Gateway:** `llmgateway.io` routing OpenAI-standard payloads to Groq (`gpt-oss-20b`) and Google AI Studio (`gemini-1.5-flash`).
*   **Frontend (Prototype):** Vanilla JS, HTML, CSS, and Leaflet.js.

## 2. The Core Scientific Problem: The Granularity Gap
The fundamental issue this system solves is spatial data incompatibility in public health[cite: 9]. 
*   **The Gap:** While sociodemographic data is highly granular (available at the census tract level), health metrics (e.g., epidemiological data from DataSUS) are typically aggregated at much larger macro-scales, such as administrative districts[cite: 9]. 
*   **The Solution:** Large Language Models (LLMs) are used not as analytical engines, but as translation interfaces[cite: 9]. The AI processes the structured data of both the micro-region (the health unit) and the macro-region, generating narratives that explicitly state scale limitations, thereby preventing user misinterpretation[cite: 9].

## 3. Data Engineering & Domain Modeling
The backend will consume data from Brazilian public health databases, processed via an ETL pipeline:
*   **Data Sources:** CNES (health facilities, beds, equipment), IBGE (census tracts), and SINAN (district-level epidemiological reports focusing on social determinant diseases like Dengue, Leptospirosis, and Tuberculosis)[cite: 7].
*   **Spatial Domain:** The database tables must guarantee exact territorial relationships between the health facility (point), the census tract (polygon), and the administrative district (multipolygon)[cite: 7].

## 4. Algorithmic Supremacy (C++ Backend Directives)
To meet the academic standards of top-tier universities (Tsinghua/Nanjing), spatial processing cannot be blindly delegated to SQL queries (e.g., `ST_Intersects`)[cite: 7].
*   **In-Memory Spatial Indexing:** The backend must fetch coordinates and polygons into application memory and implement classic space partitioning algorithms (Quadtrees or R-Trees) natively in C++[cite: 7].
*   **Complexity Benchmarking:** The code must calculate and compare the time complexity of the C++ spatial search against the raw PostGIS database execution[cite: 7, 8].
*   **Memory Optimization (Strict Rule):** When implementing request queues and processing buffers, the agent must structure containers strictly using `std::vector` or adjacency lists[cite: 8]. **The use of structures like `std::deque` is explicitly forbidden** to maintain cache locality and prevent unpredictable performance drops[cite: 8].

## 5. Knowledge Graph & Semantic Translation
Chinese research labs highly value the semantic organization of data for LLMs[cite: 7].
*   **Graph Modeling:** The backend must model a logical layer where Health Units and Census Tracts are **Nodes**[cite: 7]. Geometric relationships (e.g., "is within a 2km radius of") and infrastructure attributes become **Edges**[cite: 7].
*   **Payload Delivery:** The JSON payload sent to the LLM Gateway must represent the topological neighborhood of this graph, not a flat CSV/Table[cite: 7].

## 6. Data Storytelling & Bias Mitigation Rules
The AI's generated text must adhere to strict narrative structures to prevent analytical bias[cite: 9]:
*   **Flow:** (1) Unit Service Data -> (2) Surroundings Health Indicators -> (3) Critical Contextualization[cite: 9].
*   **Clinical Profiling Guardrails:** The system must contextualize outcomes. For example, if a unit has a high mortality rate, the narrative must investigate if the unit's profile is focused on critical cases or palliative care, preventing premature judgments about service quality[cite: 9]. It must also address patient flow (local demand vs. regional referral hub)[cite: 9].

## 7. Deterministic Guardrails & AI Testing (The Scientific Core)
The primary scientific contribution of this thesis is a zero-hallucination framework[cite: 7].
*   **Strict Separation of Concerns:** Statistical deviations and spatial correlations are strictly calculated by the C++ backend[cite: 7]. The LLM acts exclusively as a language engine via Constrained Decoding (rigid JSON schemas)[cite: 7].
*   **Chain of Thought (CoT):** The system prompt must enforce CoT reasoning, requiring the AI to logically cross-reference sanitation and morbidity before finalizing the narrative[cite: 7].
*   **Numeric Parser (Hard Fail Logic):** A C++ middleware must run *after* the LLM generates the text[cite: 7]. It must extract every numeric or statistical value from the AI's output and perform an exact match against the original Knowledge Graph payload[cite: 7]. If any divergence is found, the system must trigger a "Hard Fail", discard the response, and log an hallucination error[cite: 7, 8]. 

## 8. Development & CI/CD Standards
*   **Language:** All code, comments, variables, and documentation must be in English[cite: 7].
*   **Testing:** The Guardrail numeric parser requires absolute approval in unit tests (minimum 80% coverage)[cite: 7, 8]. The deployment pipeline must fail if the API approves any unsupported data[cite: 8].
*   **Performance:** Integration tests must validate algorithmic scalability and ensure polygon intersection calculations sustain concurrent requests efficiently[cite: 8].
*   **Git Flow:** Use Conventional Commits and logical branches (e.g., `feature/health-storytelling`, `feature/guardrails`)[cite: 7, 8].