from owlready2 import *

ONTO_URI = "http://example.org/bookstore.owl"
onto = get_ontology(ONTO_URI)

with onto:
    class Book(Thing): pass
    class Customer(Thing): pass
    class Employee(Thing): pass

    class hasName(DataProperty, FunctionalProperty): pass
    class hasTitle(DataProperty, FunctionalProperty): pass
    class hasGenre(DataProperty, FunctionalProperty): pass
    class availableQuantity(DataProperty, FunctionalProperty): pass
    class hasPrice(DataProperty, FunctionalProperty): pass

    class borrows(ObjectProperty): pass
    class worksAt(ObjectProperty): pass


def create_sample_data():
    """Initial sample data for simulation"""
    b1 = Book("book_python")
    b1.hasTitle = "Python Basics"
    b1.hasGenre = "Programming"
    b1.availableQuantity = 2
    b1.hasPrice = 10.0

    b2 = Book("book_hp")
    b2.hasTitle = "Harry Potter"
    b2.hasGenre = "Fantasy"
    b2.availableQuantity = 1
    b2.hasPrice = 12.5

    c1 = Customer("customer_alice")
    c1.hasName = "Alice"

    c2 = Customer("customer_bob")
    c2.hasName = "Bob"

    e1 = Employee("employee_emma")
    e1.hasName = "Emma"


def _first(val, default=None):
    try:
        # Owlready2 properties are list-like; handle both list and scalar
        return val[0] if val else default
    except Exception:
        return val if val is not None else default


def list_inventory():
    for b in onto.Book.instances():
        qty = _first(b.availableQuantity, 0) or 0
        title = _first(b.hasTitle, b.name)
        print(f"- {title}: qty={int(qty)}")
