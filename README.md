# Bookstore MAS (Multi‑Agent System)

A small ontology‑driven, agent‑based bookstore simulation. Customers buy books; employees restock when quantities drop below a threshold. You can run it headless (CLI) or interact with a visual dashboard (Streamlit) that shows thresholds, colors, and a live event timeline.

- Python: 3.10+
- Core libs: Owlready2 (ontology), Mesa (agent scheduler; dynamic import with fallback)
- Entrypoints: `bookstore_mas/run.py` (CLI) and `streamlit_app.py` (dashboard)

## Quickstart (Windows, uv)
From the project root:

```bat
uv sync
```

Run the CLI simulation:
```bat
uv run python -m bookstore_mas.run --steps 6
```

Launch the visual dashboard (recommended):
```bat
uv run streamlit run streamlit_app.py
```
Open the URL shown (usually http://localhost:8501).

## What you’ll see in the dashboard
- Inventory table
  - Columns: Title, Qty, Threshold, State, Price
  - State colors show threshold behavior at a glance:
    - OK: quantity > threshold (green)
    - At threshold: quantity == threshold (amber)
    - Low: quantity < threshold (red)
- Current stock vs threshold (bar chart)
  - Bars = current quantity, colored by State
  - Orange triangles = each title’s threshold
- Inventory over steps (time series)
  - Blue line = quantity over time
  - Orange dashed line = threshold over time
- Purchases over time (bar chart)
  - Purchases per step, colored by book
- Event timeline (live)
  - Each step shows “what just happened,” with colored badges:
    - Purchase (blue): who bought what; qty_before → qty_after; active threshold
    - Low stock trigger (orange): qty_after < threshold ⇒ restock requested
    - Restock (green): employee restocked; how much; new quantity
    - Out of stock (red): a customer tried to buy but quantity was 0

Tip: use “Step once” or “Run N steps” to evolve the sim and see charts/timeline update.

## Data entry and controls
- Setup panel (top of page)
  - Add books: Title (required), Author, Genre, Price, Quantity, Restock threshold
  - Add customers / employees by name
  - Delete selected entries
- Sidebar controls
  - Restock threshold and Restock amount (applied on reset)
  - Reset simulation (keep data): rebuilds the model using your current data
  - Load sample (reset all): clears and reloads the sample ontology
  - Step once / Run N steps; optional “Run reasoner (SWRL)”

## Save / load your data
- Save
  - “Download JSON snapshot” includes settings, books + inventory, customers, employees, and orders
- Load
  - Choose a JSON snapshot; load by Replace (wipe and load) or Append (merge)
- Exports
  - Inventory CSV and Orders CSV buttons under each table

## How the simulation works (brief)
- Ontology (`bookstore_mas/ontology.py`)
  - Classes: Book, Customer, Employee, Order, Inventory
  - Data props: hasTitle/Author/Genre/Price, availableQuantity, restockThreshold, currentQuantity (Inventory), hasQuantity/hasUnitPrice/orderTime (Order)
  - Object props: purchases (Customer→Book), hasBuyer (Order→Customer), hasItem (Order→Book), tracksBook (Inventory→Book)
  - SWRL examples: purchases inference; low‑stock rule (guarded). Dashboard also uses a Python fallback for low‑stock detection.
- Agents (`bookstore_mas/agents.py`)
  - Customer: randomly selects a book, purchases if in stock, reduces quantity, emits low‑stock trigger when qty_after < threshold
  - Employee: listens for restock requests and replenishes by restock_amount
  - Both publish structured UI events so the timeline explains actions as they happen
- Model (`bookstore_mas/model.py`)
  - Dynamic scheduler import for Mesa (with a minimal fallback)
  - Per‑book restockThreshold is honored; a model default applies when missing

## Troubleshooting
- Reasoner not available: SWRL is optional; the app logs and continues with Python fallback for low‑stock.
- Missing UI data: step the simulation to populate history lines and event timeline.
- uv not found: install uv (e.g., via pipx), or use `pip install -e .` and run `python -m bookstore_mas.run` / `streamlit run streamlit_app.py`.

## Project layout
- `bookstore_mas/ontology.py` — Ontology, sample data, helpers (incl. `_first`, `create_order`, `get_inventory_for_book`, `run_reasoner_safe`)
- `bookstore_mas/agents.py` — Customer/Employee/Book agents (with UI events)
- `bookstore_mas/message_bus.py` — Simple pub/sub for restock requests
- `bookstore_mas/model.py` — LibraryModel (scheduler wiring, thresholds, summaries)
- `bookstore_mas/run.py` — CLI runner
- `streamlit_app.py` — Interactive dashboard (charts, colors, event timeline, data entry, save/load)
- `pyproject.toml` — Dependencies
