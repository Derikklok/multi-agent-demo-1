# Minimal local Agent base to avoid dependency on mesa.Agent init quirks
class Agent:
    def __init__(self, unique_id, model):
        self.unique_id = unique_id
        self.model = model

    def step(self):
        pass

import random
from .ontology import _first, get_inventory_for_book, create_order

class BookAgent(Agent):
    def __init__(self, unique_id, model, book_onto):
        super().__init__(unique_id, model)
        self.book = book_onto

    def step(self):
        return


class CustomerAgent(Agent):
    def __init__(self, unique_id, model, customer_onto):
        super().__init__(unique_id, model)
        self.customer = customer_onto

    def _iter_schedule_agents(self):
        src = getattr(self.model.schedule, "agents", [])
        if isinstance(src, dict):
            return list(src.values())
        try:
            # If it's a set or other iterable
            return list(src)
        except Exception:
            return []

    def step(self):
        all_agents = self._iter_schedule_agents()
        book_agents = [a for a in all_agents if isinstance(a, BookAgent)]
        if not book_agents:
            return

        book_agent = random.choice(book_agents)
        book = book_agent.book
        qty = int(_first(book.availableQuantity, 0) or 0)

        if qty > 0:
            # Decrement book stock
            book.availableQuantity = qty - 1
            # Decrement inventory stock if present
            inv = get_inventory_for_book(book)
            if inv is not None:
                inv_qty = int(_first(inv.currentQuantity, 0) or 0)
                inv.currentQuantity = max(inv_qty - 1, 0)

            # Create an order linking customer and book
            create_order(self.customer, book, 1)

            print(
                f"[Step {self.model.current_step}] {_first(self.customer.hasName, '?')} "
                f"purchased '{_first(book.hasTitle, book.name)}' -> qty {qty-1}"
            )

            # Determine threshold from book or model
            thresh = int(_first(book.restockThreshold, self.model.restock_threshold) or self.model.restock_threshold)
            if qty - 1 < thresh:
                self.model.message_bus.publish({
                    "type": "restock_request",
                    "book": book
                })
        else:
            print(
                f"[Step {self.model.current_step}] {_first(self.customer.hasName, '?')} tried to purchase "
                f"'{_first(book.hasTitle, book.name)}' but it's out of stock"
            )


class EmployeeAgent(Agent):
    def __init__(self, unique_id, model, employee_onto, restock_amount=3):
        super().__init__(unique_id, model)
        self.employee = employee_onto
        self.restock_amount = restock_amount

    def step(self):
        msgs = self.model.message_bus.get_messages("restock_request")
        for msg in msgs:
            book = msg["book"]
            qty = int(_first(book.availableQuantity, 0) or 0)
            new_qty = qty + self.restock_amount
            # Update book stock
            book.availableQuantity = new_qty

            # Update inventory stock if present
            inv = get_inventory_for_book(book)
            if inv is not None:
                inv_qty = int(_first(inv.currentQuantity, 0) or 0)
                inv.currentQuantity = inv_qty + self.restock_amount

            print(
                f"[Step {self.model.current_step}] {_first(self.employee.hasName, '?')} restocked "
                f"'{_first(book.hasTitle, book.name)}' -> qty {new_qty}"
            )
