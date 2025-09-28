from owlready2 import *
from datetime import datetime
import uuid

ONTO_URI = "http://example.org/bookstore.owl"
onto = get_ontology(ONTO_URI)

with onto:
    # Core classes
    class Book(Thing): pass
    class Customer(Thing): pass
    class Employee(Thing): pass

    # Assignment extensions
    class Order(Thing): pass
    class Inventory(Thing): pass
    class LowStockBook(Book): pass  # will be inferred by SWRL when below threshold

    # Data properties (Functional)
    class hasName(DataProperty, FunctionalProperty): pass
    class hasTitle(DataProperty, FunctionalProperty): pass
    class hasAuthor(DataProperty, FunctionalProperty): pass
    class hasGenre(DataProperty, FunctionalProperty): pass
    class availableQuantity(DataProperty, FunctionalProperty): pass
    class currentQuantity(DataProperty, FunctionalProperty): pass  # for Inventory
    class hasPrice(DataProperty, FunctionalProperty): pass
    class restockThreshold(DataProperty, FunctionalProperty): pass
    class hasQuantity(DataProperty, FunctionalProperty): pass      # for Order quantity
    class hasUnitPrice(DataProperty, FunctionalProperty): pass     # for Order unit price
    class orderTime(DataProperty, FunctionalProperty): pass        # datetime

    # Object properties
    class borrows(ObjectProperty): pass
    class worksAt(ObjectProperty): pass
    class purchases(ObjectProperty): pass            # Customer -> Book
    class hasBuyer(ObjectProperty, FunctionalProperty): pass  # Order -> Customer
    class hasItem(ObjectProperty, FunctionalProperty): pass   # Order -> Book
    class tracksBook(ObjectProperty, FunctionalProperty): pass # Inventory -> Book

    # Register SWRL namespaces and map prefixes so built-ins like swrlb:lessThan resolve
    swrl  = onto.world.get_namespace("http://www.w3.org/2003/11/swrl#")
    swrlb = onto.world.get_namespace("http://www.w3.org/2003/11/swrlb#")
    onto.world._namespaces["swrl"] = swrl
    onto.world._namespaces["swrlb"] = swrlb

    # SWRL-like rules
    # If there exists an Order linking a customer and a book, infer purchases(customer, book)
    rule_purchases = Imp()
    rule_purchases.set_as_rule("Order(?o), hasBuyer(?o, ?c), hasItem(?o, ?b) -> purchases(?c, ?b)")

    # Classify a book as LowStockBook when availableQuantity < restockThreshold
    try:
        rule_low_stock = Imp()
        rule_low_stock.set_as_rule(
            "Book(?b), availableQuantity(?b, ?q), restockThreshold(?b, ?t), swrlb:lessThan(?q, ?t) -> LowStockBook(?b)"
        )
    except Exception as e:
        print("Warning: SWRL low-stock rule not registered:", e)


def _first(val, default=None):
    try:
        # Owlready2 properties are list-like; handle both list and scalar
        return val[0] if val else default
    except Exception:
        return val if val is not None else default


def get_inventory_for_book(book: onto.Book):
    for inv in onto.Inventory.instances():
        if _first(inv.tracksBook) == book:
            return inv
    return None


def create_order(customer: onto.Customer, book: onto.Book, quantity: int = 1):
    """Create an Order instance linked to customer and book; also set unit price and timestamp."""
    oid = f"order_{uuid.uuid4().hex[:8]}"
    order = onto.Order(oid)
    order.hasBuyer = customer
    order.hasItem = book
    order.hasQuantity = int(quantity)
    unit_price = float(_first(book.hasPrice, 0) or 0)
    order.hasUnitPrice = unit_price
    order.orderTime = datetime.now()
    # Also record direct relation for convenience
    if book not in (customer.purchases or []):
        customer.purchases.append(book)
    return order


def run_reasoner_safe():
    """Attempt to run a reasoner to compute SWRL inferences; ignore if Java/engine is unavailable."""
    try:
        from owlready2 import sync_reasoner_pellet
        sync_reasoner_pellet(infer_property_values=True)
        print("Reasoner ran successfully (pellet)")
    except Exception as e:
        try:
            from owlready2 import sync_reasoner
            sync_reasoner()
            print("Reasoner ran successfully")
        except Exception:
            print("Reasoner not available; skipping SWRL inference (this is optional)")


def create_sample_data():
    """Initial sample data for simulation"""
    # Books
    b1 = Book("book_python")
    b1.hasTitle = "Python Basics"
    b1.hasAuthor = "Jane Smith"
    b1.hasGenre = "Programming"
    b1.availableQuantity = 2
    b1.hasPrice = 10.0
    b1.restockThreshold = 1

    b2 = Book("book_hp")
    b2.hasTitle = "Harry Potter"
    b2.hasAuthor = "J.K. Rowling"
    b2.hasGenre = "Fantasy"
    b2.availableQuantity = 1
    b2.hasPrice = 12.5
    b2.restockThreshold = 1

    # Inventory for each book
    i1 = Inventory("inv_python")
    i1.tracksBook = b1
    i1.currentQuantity = _first(b1.availableQuantity, 0) or 0

    i2 = Inventory("inv_hp")
    i2.tracksBook = b2
    i2.currentQuantity = _first(b2.availableQuantity, 0) or 0

    # Customers
    c1 = Customer("customer_alice")
    c1.hasName = "Alice"

    c2 = Customer("customer_bob")
    c2.hasName = "Bob"

    # Employees
    e1 = Employee("employee_emma")
    e1.hasName = "Emma"


def list_inventory():
    for b in onto.Book.instances():
        qty = int(_first(b.availableQuantity, 0) or 0)
        title = _first(b.hasTitle, b.name)
        print(f"- {title}: qty={qty}")


def list_purchases():
    for c in onto.Customer.instances():
        name = _first(c.hasName, c.name)
        items = [ _first(b.hasTitle, b.name) for b in (c.purchases or []) ]
        print(f"Customer {name} purchases: {items}")
