# Bookstore MAS (Multi-Agent System)

A tiny agent-based simulation of a bookstore using an ontology (Owlready2) and a Mesa-compatible scheduler. Customers randomly borrow books; employees restock when inventory drops below a threshold. It’s designed to run with multiple Mesa versions and will use a small built-in scheduler if Mesa’s scheduler module isn’t available.

- Language: Python 3.10+
- Dependencies: Mesa (2.x/3.x), Owlready2
- Entry point: `bookstore_mas/run.py`

## Project layout
- `bookstore_mas/ontology.py` — Ontology (Book, Customer, Employee) and sample data. Also includes `list_inventory()` and a helper `_first()`.
- `bookstore_mas/agents.py` — Agent classes: `BookAgent`, `CustomerAgent`, `EmployeeAgent`, and a minimal `Agent` base.
- `bookstore_mas/message_bus.py` — Simple in-memory message bus for restock requests.
- `bookstore_mas/model.py` — `LibraryModel` wires everything together and resolves the scheduler across Mesa versions or falls back to a tiny local scheduler.
- `bookstore_mas/run.py` — Command-line runner.
- `pyproject.toml` — Declares dependencies.

## Quickstart (with uv)
Prerequisites:
- Python 3.10+
- uv installed (https://docs.astral.sh/uv/)

From the project root:

```bat
uv sync
uv run python -m bookstore_mas.run --steps 6
```

You should see an initial inventory, a few borrowing/restocking logs, and a final inventory.

## How it works
- Ontology (Owlready2)
  - Defines classes: `Book`, `Customer`, `Employee`.
  - Data properties marked as `FunctionalProperty` (single value): `hasName`, `hasTitle`, `hasGenre`, `availableQuantity`, `hasPrice`.
  - `create_sample_data()` populates a small in-memory dataset.
  - Important: these Functional properties are assigned scalars (e.g., `b1.hasTitle = "Python Basics"`, not lists). Owlready2 allows list-like reading, but assigning lists to Functional properties can raise `TypeError`.
  - `_first(val, default)` reads either the first item if the property is a list-like or returns the scalar value if not.

- Agents
  - Minimal local `Agent` base supplies `unique_id` and `model` so we don’t depend on `mesa.Agent.__init__` (avoids an `object.__init__` TypeError in some setups).
  - `BookAgent`: wraps an ontology `Book` instance.
  - `CustomerAgent.step()`:
    - Finds all `BookAgent`s and picks one at random.
    - Reads `availableQuantity` via `_first(...)` and decrements it when borrowing.
    - If the new quantity is below `restock_threshold`, publishes a `restock_request` on the `MessageBus`.
  - `EmployeeAgent.step()`:
    - Consumes `restock_request` messages.
    - Increases `availableQuantity` by `restock_amount` and logs the restock action.

- Message Bus
  - `MessageBus.publish(message: dict)` appends to a queue.
  - `get_messages(msg_type)` returns and removes messages of the requested type.

- Model and Scheduler
  - `LibraryModel` holds the scheduler, agents, and counters. It advances one step by calling `self.schedule.step()` and increments `current_step`.
  - Scheduler resolution is dynamic; it tries these in order:
    1. `mesa.time.RandomActivation` (Mesa ≤ 2.x)
    2. `mesa.scheduler.RandomActivation` (Mesa 3.x)
    3. `mesa.timekeeping.RandomActivation` (alternate)
  - If none are available, a tiny local RandomActivation-like class is used (supports `add(agent)`, `agents` property, and random order in `step()`).

- Runner
  - `bookstore_mas/run.py` parses `--steps` and runs the model.

## Important code lines explained
- Dynamic scheduler resolution (`bookstore_mas/model.py`):
  ```python
  from importlib import import_module

  def _resolve_random_activation():
      candidates = [
          ("mesa.time", "RandomActivation"),
          ("mesa.scheduler", "RandomActivation"),
          ("mesa.timekeeping", "RandomActivation"),
      ]
      for mod_name, attr in candidates:
          try:
              mod = import_module(mod_name)
              return getattr(mod, attr)
          except Exception:
              continue
      # Fallback class returned if Mesa paths are unavailable
  ```
  Why: Mesa changed internal module paths across versions. This keeps the project running without you having to pin a specific Mesa.

- Fallback scheduler (simplified):
  ```python
  class _RandomActivationFallback:
      def __init__(self, model):
          self.model = model
          self._agents = []
      @property
      def agents(self):
          return list(self._agents)
      def add(self, agent):
          self._agents.append(agent)
      def step(self):
          random.shuffle(self._agents)
          for a in list(self._agents):
              a.step()
  ```
  Why: Provides the minimal behavior we need (random activation) if Mesa’s scheduler module is not present.

- Functional DataProperties set to scalars (`bookstore_mas/ontology.py`):
  ```python
  b1.hasTitle = "Python Basics"   # not ["Python Basics"]
  b1.availableQuantity = 2         # not [2]
  ```
  Why: Owlready2 Functional properties are single-valued. Assigning lists can raise `TypeError: unhashable type: 'list'`.

- Safe property reads (`bookstore_mas/ontology.py`):
  ```python
  def _first(val, default=None):
      try:
          return val[0] if val else default
      except Exception:
          return val if val is not None else default
  ```
  Why: Owlready2 values can be list-like or scalar depending on context; this avoids indexing errors.

- Customer borrow + restock request (`bookstore_mas/agents.py`):
  ```python
  qty = int(_first(book_agent.book.availableQuantity, 0) or 0)
  if qty > 0:
      book_agent.book.availableQuantity = qty - 1
      if qty - 1 < self.model.restock_threshold:
          self.model.message_bus.publish({"type": "restock_request", "book": book_agent.book})
  ```
  Why: Updates inventory and triggers restock when below threshold.

- Employee restock (`bookstore_mas/agents.py`):
  ```python
  msgs = self.model.message_bus.get_messages("restock_request")
  for msg in msgs:
      book = msg["book"]
      qty = int(_first(book.availableQuantity, 0) or 0)
      book.availableQuantity = qty + self.restock_amount
  ```
  Why: Processes message bus and increases inventory.

## Troubleshooting
- Mesa import errors: This project dynamically resolves the scheduler and falls back to a tiny local implementation. If you want to rely strictly on Mesa’s scheduler, pin Mesa ≥ 3.0 and switch directly to `from mesa.scheduler import RandomActivation` in `model.py`.
- Owlready2 TypeError: Ensure you assign scalars (not lists) to Functional DataProperties.
- `uv` not found: Install uv (e.g., `pipx install uv`) or use `pip install -e .` to install dependencies from `pyproject.toml`.

## Development tips
- Deterministic runs: seed Python’s `random` at model init if you want reproducible results.
- Pin Mesa: If you standardize on one Mesa version, you can remove the dynamic import and fallback scheduler to simplify the code.
- Visualization: Consider adding Mesa’s visualization components or exporting logs for analysis.

