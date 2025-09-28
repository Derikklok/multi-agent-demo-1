from mesa import Model
from importlib import import_module

# Resolve RandomActivation across Mesa versions with a minimal fallback

def _resolve_random_activation():
    candidates = [
        ("mesa.time", "RandomActivation"),      # Mesa <= 2.x
        ("mesa.scheduler", "RandomActivation"), # Mesa 3.x
        ("mesa.timekeeping", "RandomActivation"),
    ]
    for mod_name, attr in candidates:
        try:
            mod = import_module(mod_name)
            ra = getattr(mod, attr)
            return ra
        except Exception:
            continue

    # Fallback scheduler
    import random as _random

    class _RandomActivationFallback:  # type: ignore
        def __init__(self, model):
            self.model = model
            self._agents = []

        @property
        def agents(self):
            return list(self._agents)

        def add(self, agent):
            self._agents.append(agent)

        def step(self):
            _random.shuffle(self._agents)
            for a in list(self._agents):
                a.step()

    return _RandomActivationFallback

_RandomActivation = _resolve_random_activation()

from .ontology import onto, create_sample_data, list_inventory, _first, run_reasoner_safe, list_purchases, LOW_STOCK_RULE_ENABLED
from .agents import BookAgent, CustomerAgent, EmployeeAgent
from .message_bus import MessageBus


class LibraryModel(Model):
    def __init__(self, restock_threshold=1, restock_amount=3):
        super().__init__()
        self.schedule = _RandomActivation(self)
        self.current_step = 0
        self.restock_threshold = restock_threshold
        self.restock_amount = restock_amount
        self.message_bus = MessageBus()
        # UI event sink for Streamlit: agents append dict events here
        self.ui_events: list[dict] = []

        create_sample_data()

        # Ensure each book has a restock threshold set (use model default if missing)
        for b in onto.Book.instances():
            if _first(b.restockThreshold, None) is None:
                b.restockThreshold = self.restock_threshold

        uid = 0
        for b in onto.Book.instances():
            self.schedule.add(BookAgent(uid, self, b)); uid += 1
        for c in onto.Customer.instances():
            self.schedule.add(CustomerAgent(uid, self, c)); uid += 1
        for e in onto.Employee.instances():
            # Pass configured restock amount
            self.schedule.add(EmployeeAgent(uid, self, e, restock_amount=self.restock_amount)); uid += 1

    def step(self):
        self.schedule.step()
        self.current_step += 1

    def run(self, steps=5):
        print("Initial inventory:")
        list_inventory()

        for i in range(steps):
            print(f"\n--- Simulation step {i+1} ---")
            self.step()

        print("\nFinal inventory:")
        list_inventory()

        # Optional: run reasoner to apply SWRL rules
        run_reasoner_safe()

        # Summary of purchases (explicit + inferred)
        print("\nPurchase summary:")
        list_purchases()

        # SWRL low-stock classification (if reasoner available) with Python fallback
        titles_swrl = []
        try:
            titles_swrl = [ _first(b.hasTitle, b.name) for b in onto.LowStockBook.instances() ]
        except Exception:
            titles_swrl = []

        if titles_swrl:
            print(f"Low-stock classification (SWRL): {titles_swrl}")
        else:
            # Fallback classification based on numeric comparison
            fallback = []
            for b in onto.Book.instances():
                q = int(_first(b.availableQuantity, 0) or 0)
                t = int(_first(b.restockThreshold, self.restock_threshold) or self.restock_threshold)
                if q < t:
                    fallback.append(_first(b.hasTitle, b.name))
            print(f"Low-stock classification (fallback): {fallback}")
