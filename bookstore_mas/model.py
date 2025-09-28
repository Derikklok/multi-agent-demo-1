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

from .ontology import onto, create_sample_data, list_inventory
from .agents import BookAgent, CustomerAgent, EmployeeAgent
from .message_bus import MessageBus


class LibraryModel(Model):
    def __init__(self, restock_threshold=1):
        super().__init__()
        self.schedule = _RandomActivation(self)
        self.current_step = 0
        self.restock_threshold = restock_threshold
        self.message_bus = MessageBus()

        create_sample_data()

        uid = 0
        for b in onto.Book.instances():
            self.schedule.add(BookAgent(uid, self, b)); uid += 1
        for c in onto.Customer.instances():
            self.schedule.add(CustomerAgent(uid, self, c)); uid += 1
        for e in onto.Employee.instances():
            self.schedule.add(EmployeeAgent(uid, self, e)); uid += 1

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
