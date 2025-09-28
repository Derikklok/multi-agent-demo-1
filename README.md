# Bookstore MAS (Multi-Agent System)

A tiny agent-based simulation of a bookstore using an ontology (Owlready2) and a Mesa-compatible scheduler. Customers randomly buy books; employees restock when inventory drops below a threshold. It runs with multiple Mesa versions and falls back to a small built-in scheduler if Mesa’s scheduler module isn’t available.

- Language: Python 3.10+
- Dependencies: Mesa (2.x/3.x), Owlready2
- Entry point: `bookstore_mas/run.py`

## Project layout
- `bookstore_mas/ontology.py` — Ontology (Book, Customer, Employee, Order, Inventory, LowStockBook), sample data, helpers (`_first`, `create_order`, `get_inventory_for_book`, `run_reasoner_safe`, `list_inventory`, `list_purchases`). Includes SWRL rules.
- `bookstore_mas/agents.py` — Agent classes: `BookAgent`, `CustomerAgent`, `EmployeeAgent`, and a minimal `Agent` base. Customers create orders; employees restock books and inventory.
- `bookstore_mas/message_bus.py` — Simple in-memory message bus for restock requests.
- `bookstore_mas/model.py` — `LibraryModel` wires everything together, resolves the scheduler across Mesa versions, ensures per-book restock thresholds, runs the reasoner (optional), prints summaries.
- `bookstore_mas/run.py` — Command-line runner.
- `pyproject.toml` — Declares dependencies.

## Quickstart (Windows, with uv)
Prerequisites:
- Python 3.10+
- uv installed (https://docs.astral.sh/uv/)

From the project root:

```bat
uv sync
uv run python -m bookstore_mas.run --steps 6
```

You should see an initial inventory, step-by-step purchases/restocks, a final inventory, a purchase summary, and (if a reasoner is available) a low-stock classification.

## How it works
- Ontology (Owlready2)
  - Classes: `Book`, `Customer`, `Employee`, `Order`, `Inventory`, `LowStockBook` (SWRL-inferred).
  - Data properties (Functional): `hasName`, `hasTitle`, `hasAuthor`, `hasGenre`, `availableQuantity`, `currentQuantity` (Inventory), `hasPrice`, `restockThreshold` (Book), `hasQuantity`, `hasUnitPrice`, `orderTime` (Order).
  - Object properties: `borrows`, `worksAt`, `purchases` (Customer→Book), `hasBuyer` (Order→Customer), `hasItem` (Order→Book), `tracksBook` (Inventory→Book).
  - `create_sample_data()` seeds books (title/author/genre/price/quantity/threshold), inventory per book, customers, and an employee.
  - `_first(val, default)` safely reads values as list or scalar.

- SWRL rules (in `ontology.py`)
  - Purchases inference:
    ```python
    rule_purchases.set_as_rule("Order(?o), hasBuyer(?o, ?c), hasItem(?o, ?b) -> purchases(?c, ?b)")
    ```
  - Low-stock classification:
    ```python
    rule_low_stock.set_as_rule(
        "Book(?b), availableQuantity(?b, ?q), restockThreshold(?b, ?t), swrlb:lessThan(?q, ?t) -> LowStockBook(?b)"
    )
    ```
  - `run_reasoner_safe()` tries Pellet or the default reasoner and skips gracefully if unavailable.

- Agents
  - Minimal local `Agent` base to avoid mesa.Agent init issues.
  - `CustomerAgent.step()`:
    - Picks a random `BookAgent`.
    - Decrements `Book.availableQuantity` and matching `Inventory.currentQuantity`.
    - Creates an `Order` via `create_order(customer, book, qty=1)`.
    - If below the threshold (book-specific `restockThreshold` or model default), publishes a `restock_request`.
  - `EmployeeAgent.step()`:
    - Consumes `restock_request`.
    - Increases `Book.availableQuantity` and `Inventory.currentQuantity` by `restock_amount`.

- Message Bus
  - `publish(message: dict)` and `get_messages(msg_type)` support decoupled agent communication.

- Model and Scheduler
  - `LibraryModel` tracks `current_step`, `restock_threshold`, `message_bus`, and a scheduler.
  - Sets `restockThreshold` per book if missing.
  - Uses Mesa’s `RandomActivation` if available; otherwise, a tiny fallback with `add()`, `agents`, and random `step()`.
  - After running steps: prints final inventory, runs the reasoner (optional), prints a purchase summary, and lists SWRL-inferred `LowStockBook` instances if available.

- Runner
  - `bookstore_mas/run.py` parses `--steps` and runs the model.

## Assignment tasks mapping
1) Setup and Imports — Done
- Dependencies in `pyproject.toml` (Mesa and Owlready2). Scheduler resolution adapts to Mesa versions.

2) Ontology Definition — Done (extendable)
- Implemented: `Book`, `Customer`, `Employee`, `Order`, `Inventory`, and properties (`hasAuthor`, `hasGenre`, `availableQuantity`, `currentQuantity`, `hasPrice`, `purchases`, `worksAt`, `hasBuyer`, `hasItem`, `hasQuantity`, `hasUnitPrice`, `orderTime`, `restockThreshold`, `tracksBook`).

3) Agent-Based Simulation — Done
- Customers browse randomly and purchase if available.
- Employees restock low inventory.
- Book agents expose ontology-backed price/stock/genre.

4) SWRL Rules — Done
- Purchases inference and low-stock classification rules included; reasoner invoked at end if available.

5) Message Bus — Done
- Agents publish/consume messages for restocking.

6) MAS Model and Agents — Done
- Full Mesa-compatible model with agents and scheduler.

7) Run Simulation — Done
- Use `--steps` to control iterations.

8) Inspection and Summary — Done
- Final inventory, purchase summary, and (if reasoner) low-stock classification.

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
      # Fallback class if Mesa paths are unavailable
  ```
- Fallback scheduler (simplified):
  ```python
  class _RandomActivationFallback:
      def __init__(self, model):
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
- SWRL rules (`bookstore_mas/ontology.py`):
  ```python
  rule_purchases.set_as_rule("Order(?o), hasBuyer(?o, ?c), hasItem(?o, ?b) -> purchases(?c, ?b)")
  rule_low_stock.set_as_rule(
      "Book(?b), availableQuantity(?b, ?q), restockThreshold(?b, ?t), swrlb:lessThan(?q, ?t) -> LowStockBook(?b)"
  )
  ```
- Order creation (`create_order`):
  ```python
  order = onto.Order(oid)
  order.hasBuyer = customer
  order.hasItem = book
  order.hasQuantity = 1
  order.hasUnitPrice = float(_first(book.hasPrice, 0) or 0)
  order.orderTime = datetime.now()
  customer.purchases.append(book)
  ```
- Inventory linkage and updates:
  ```python
  inv = get_inventory_for_book(book)
  if inv is not None:
      inv.currentQuantity = max(int(_first(inv.currentQuantity, 0) or 0) - 1, 0)
  # In employee restock:
  inv.currentQuantity = int(_first(inv.currentQuantity, 0) or 0) + self.restock_amount
  ```

## Troubleshooting
- Mesa import errors: The project dynamically resolves the scheduler and falls back to a local implementation. If you want to require Mesa’s scheduler, pin Mesa ≥ 3.0 and use `from mesa.scheduler import RandomActivation`.
- Reasoner not found: `run_reasoner_safe()` will skip if Pellet/Java isn’t available.
- Owlready2 TypeError: Assign scalars (not lists) to Functional DataProperties.
- `uv` not found: Install uv (e.g., `pipx install uv`) or use `pip install -e .`.

## Further extensions
- Add additional properties (e.g., discounts, genres hierarchies).
- Capture detailed order history and export summaries.
- Visualization: integrate Mesa’s visualization or dashboards.
