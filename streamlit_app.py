import streamlit as st
import io, csv, json
import pandas as pd
import altair as alt
from datetime import datetime
from owlready2 import destroy_entity
from bookstore_mas.model import LibraryModel
from bookstore_mas.ontology import onto, _first, reset_ontology, run_reasoner_safe, get_inventory_for_book

# ----- Helpers -----

def inventory_rows():
    rows = []
    for b in onto.Book.instances():
        title = _first(b.hasTitle, b.name)
        qty = int(_first(b.availableQuantity, 0) or 0)
        thr = int(_first(b.restockThreshold, 0) or 0)
        if qty < thr:
            state = "Low"
        elif qty == thr:
            state = "At threshold"
        else:
            state = "OK"
        rows.append({
            "Title": title,
            "Author": _first(b.hasAuthor, ""),
            "Genre": _first(b.hasGenre, ""),
            "Qty": qty,
            "Threshold": thr,
            "State": state,
            "Price": float(_first(b.hasPrice, 0) or 0),
        })
    return rows


def orders_rows():
    rows = []
    for o in onto.Order.instances():
        rows.append({
            "Order ID": o.name,
            "Buyer": _first(_first(o.hasBuyer).hasName, _first(o.hasBuyer).name) if _first(o.hasBuyer) else "",
            "Item": _first(_first(o.hasItem).hasTitle, _first(o.hasItem).name) if _first(o.hasItem) else "",
            "Qty": int(_first(o.hasQuantity, 0) or 0),
            "Unit Price": float(_first(o.hasUnitPrice, 0) or 0),
            "Time": str(_first(o.orderTime, "")),
        })
    return rows


def low_stock_fallback(restock_default: int):
    lows = []
    for b in onto.Book.instances():
        q = int(_first(b.availableQuantity, 0) or 0)
        t = int(_first(b.restockThreshold, restock_default) or restock_default)
        if q < t:
            lows.append(_first(b.hasTitle, b.name))
    return lows


def record_histories():
    """Record inventory quantities, thresholds, new purchases, and new UI events for the current step."""
    step = st.session_state.model.current_step
    # Inventory history per book
    for b in onto.Book.instances():
        st.session_state.inv_history.append({
            "step": step,
            "Title": _first(b.hasTitle, b.name),
            "Qty": int(_first(b.availableQuantity, 0) or 0),
            "Threshold": int(_first(b.restockThreshold, st.session_state.restock_threshold) or st.session_state.restock_threshold),
        })
    # New orders detected in this step
    current_ids = {o.name for o in onto.Order.instances()}
    new_ids = current_ids - st.session_state.last_order_ids
    if new_ids:
        counts = {}
        for oid in new_ids:
            o = onto.search_one(iri=f"*{oid}") or next((x for x in onto.Order.instances() if x.name == oid), None)
            if not o:  # safety
                continue
            title = _first(_first(o.hasItem).hasTitle, _first(o.hasItem).name) if _first(o.hasItem) else ""
            counts[title] = counts.get(title, 0) + int(_first(o.hasQuantity, 0) or 0)
        for title, cnt in counts.items():
            st.session_state.purchases_history.append({
                "step": step,
                "Title": title,
                "Count": cnt,
            })
    st.session_state.last_order_ids = current_ids
    # Capture new UI events from the model
    evts = st.session_state.model.ui_events
    new_events = evts[st.session_state.events_seen:]
    st.session_state.events_seen = len(evts)
    if new_events:
        st.session_state.event_feed.extend(new_events)


def event_badge(evt_type: str) -> str:
    colors = {
        "purchase": "#2563eb",        # blue
        "low_stock_trigger": "#f59e0b", # amber
        "restock": "#16a34a",         # green
        "out_of_stock": "#dc2626",    # red
    }
    label = {
        "purchase": "Purchase",
        "low_stock_trigger": "Low stock",
        "restock": "Restock",
        "out_of_stock": "Out of stock",
    }.get(evt_type, evt_type)
    color = colors.get(evt_type, "#6b7280")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:999px;font-size:12px;">{label}</span>'


def render_event(evt: dict) -> str:
    t = evt.get("type")
    step = evt.get("step")
    badge = event_badge(t)
    if t == "purchase":
        return f"{badge} <b>Step {step}</b>: {evt.get('customer')} bought '<b>{evt.get('book')}</b>' (qty {evt.get('qty_before')}→{evt.get('qty_after')}, thr {evt.get('threshold')})"
    if t == "low_stock_trigger":
        return f"{badge} <b>Step {step}</b>: '<b>{evt.get('book')}</b>' fell below threshold (qty {evt.get('qty')}, thr {evt.get('threshold')}) — restock requested"
    if t == "restock":
        return f"{badge} <b>Step {step}</b>: {evt.get('employee')} restocked '<b>{evt.get('book')}</b>' (+{evt.get('added')}, {evt.get('qty_before')}→{evt.get('qty_after')})"
    if t == "out_of_stock":
        return f"{badge} <b>Step {step}</b>: {evt.get('customer')} tried to buy '<b>{evt.get('book')}</b>' but stock was {evt.get('qty')}"
    return f"{badge} <b>Step {step}</b>"


def build_snapshot() -> dict:
    data = {
        "settings": {
            "restock_threshold": st.session_state.get("restock_threshold", 1),
            "restock_amount": st.session_state.get("restock_amount", 3),
        },
        "books": [],
        "customers": [],
        "employees": [],
        "orders": [],
    }
    for b in onto.Book.instances():
        data["books"].append({
            "id": b.name,
            "title": _first(b.hasTitle, b.name),
            "author": _first(b.hasAuthor, ""),
            "genre": _first(b.hasGenre, ""),
            "price": float(_first(b.hasPrice, 0) or 0),
            "qty": int(_first(b.availableQuantity, 0) or 0),
            "threshold": int(_first(b.restockThreshold, 0) or 0),
        })
    for c in onto.Customer.instances():
        data["customers"].append({"id": c.name, "name": _first(c.hasName, c.name)})
    for e in onto.Employee.instances():
        data["employees"].append({"id": e.name, "name": _first(e.hasName, e.name)})
    for o in onto.Order.instances():
        buyer = _first(o.hasBuyer)
        item = _first(o.hasItem)
        data["orders"].append({
            "id": o.name,
            "buyer_id": buyer.name if buyer else None,
            "item_id": item.name if item else None,
            "qty": int(_first(o.hasQuantity, 0) or 0),
            "unit_price": float(_first(o.hasUnitPrice, 0) or 0),
            "time": str(_first(o.orderTime, "")),
        })
    return data


def load_snapshot(data: dict, replace: bool = True):
    if replace:
        # Clear all current instances
        reset_ontology()
    # Recreate books + inventory
    existing_ids = set(x.name for x in onto.Book.instances())
    id_map_books = {}
    for rec in data.get("books", []):
        bid = rec.get("id") or f"book_{rec.get('title','book').lower().replace(' ','_')}"
        if bid in existing_ids:
            # ensure uniqueness
            base = bid
            i = 1
            while f"{base}_{i}" in existing_ids:
                i += 1
            bid = f"{base}_{i}"
        b = onto.Book(bid)
        b.hasTitle = rec.get("title") or bid
        if rec.get("author"): b.hasAuthor = rec["author"]
        if rec.get("genre"): b.hasGenre = rec["genre"]
        b.hasPrice = float(rec.get("price", 0))
        b.availableQuantity = int(rec.get("qty", 0))
        b.restockThreshold = int(rec.get("threshold", 0))
        inv = onto.Inventory(f"inv_{bid}")
        inv.tracksBook = b
        inv.currentQuantity = int(rec.get("qty", 0))
        existing_ids.add(bid)
        id_map_books[rec.get("id", bid)] = b
    # Recreate customers
    existing_cids = set(x.name for x in onto.Customer.instances())
    id_map_customers = {}
    for rec in data.get("customers", []):
        cid = rec.get("id") or f"customer_{(rec.get('name') or 'c').lower().replace(' ','_')}"
        if cid in existing_cids:
            base = cid; i=1
            while f"{base}_{i}" in existing_cids:
                i+=1
            cid = f"{base}_{i}"
        c = onto.Customer(cid)
        if rec.get("name"): c.hasName = rec["name"]
        existing_cids.add(cid)
        id_map_customers[rec.get("id", cid)] = c
    # Recreate employees
    existing_eids = set(x.name for x in onto.Employee.instances())
    id_map_employees = {}
    for rec in data.get("employees", []):
        eid = rec.get("id") or f"employee_{(rec.get('name') or 'e').lower().replace(' ','_')}"
        if eid in existing_eids:
            base=eid; i=1
            while f"{base}_{i}" in existing_eids:
                i+=1
            eid = f"{base}_{i}"
        e = onto.Employee(eid)
        if rec.get("name"): e.hasName = rec["name"]
        existing_eids.add(eid)
        id_map_employees[rec.get("id", eid)] = e
    # Recreate orders and purchases relation
    for rec in data.get("orders", []):
        oid = rec.get("id") or f"order_{len(onto.Order.instances())+1}"
        # ensure uniqueness
        exists = {x.name for x in onto.Order.instances()}
        if oid in exists:
            base=oid; i=1
            while f"{base}_{i}" in exists:
                i+=1
            oid = f"{base}_{i}"
        o = onto.Order(oid)
        # Link buyer & item
        buyer = id_map_customers.get(rec.get("buyer_id"))
        item = id_map_books.get(rec.get("item_id"))
        if buyer: o.hasBuyer = buyer
        if item: o.hasItem = item
        if buyer and item:
            # maintain purchases relation for convenience
            if item not in (buyer.purchases or []):
                buyer.purchases.append(item)
        o.hasQuantity = int(rec.get("qty", 1) or 1)
        o.hasUnitPrice = float(rec.get("unit_price", 0) or 0)
        t = rec.get("time")
        if t:
            try:
                # allow plain str storage; keep as string if not parseable
                o.orderTime = t
            except Exception:
                o.orderTime = str(t)
    # Update settings / model
    settings = data.get("settings", {})
    st.session_state.restock_threshold = int(settings.get("restock_threshold", st.session_state.get("restock_threshold", 1)))
    st.session_state.restock_amount = int(settings.get("restock_amount", st.session_state.get("restock_amount", 3)))
    # Rebuild model to reflect new ontology
    st.session_state.model = LibraryModel(
        restock_threshold=st.session_state.restock_threshold,
        restock_amount=st.session_state.restock_amount,
    )
    st.session_state.steps = 0
    st.session_state.inv_history = []
    st.session_state.purchases_history = []
    st.session_state.last_order_ids = set()
    st.session_state.event_feed = []
    st.session_state.events_seen = 0

# ----- App state -----

if "restock_threshold" not in st.session_state:
    st.session_state.restock_threshold = 1
if "restock_amount" not in st.session_state:
    st.session_state.restock_amount = 3
if "model" not in st.session_state:
    reset_ontology()
    st.session_state.model = LibraryModel(
        restock_threshold=st.session_state.restock_threshold,
        restock_amount=st.session_state.restock_amount,
    )
    st.session_state.steps = 0
    st.session_state.inv_history = []
    st.session_state.purchases_history = []
    st.session_state.last_order_ids = set()
    st.session_state.event_feed = []
    st.session_state.events_seen = 0

# ----- UI -----

st.set_page_config(page_title="Bookstore MAS", layout="wide")
st.title("Bookstore Management System - MAS + Ontology")

with st.expander("Setup: define inventory and participants", expanded=False):
    # Add book form
    st.subheader("Books")
    with st.form("add_book_form", clear_on_submit=True):
        colA, colB, colC = st.columns([2,2,1])
        with colA:
            in_title = st.text_input("Title", placeholder="e.g., Python Basics")
            in_author = st.text_input("Author", placeholder="e.g., Jane Smith")
            in_genre = st.text_input("Genre", placeholder="e.g., Programming")
        with colB:
            in_price = st.number_input("Price", min_value=0.0, step=0.5, value=10.0)
            in_qty = st.number_input("Quantity", min_value=0, step=1, value=1)
            in_thr = st.number_input("Restock threshold", min_value=0, step=1, value=1)
        submitted = st.form_submit_button("Add book")
        if submitted:
            title = in_title.strip()
            if not title:
                st.warning("Please enter a title")
            else:
                # Build a safe unique ID
                base = ''.join(ch.lower() if ch.isalnum() else '_' for ch in title).strip('_')
                if not base:
                    base = 'book'
                bid = f"book_{base}"
                # ensure uniqueness
                existing = {b.name for b in onto.Book.instances()}
                suffix = 1
                new_id = bid
                while new_id in existing:
                    suffix += 1
                    new_id = f"{bid}_{suffix}"
                b = onto.Book(new_id)
                b.hasTitle = title
                if in_author:
                    b.hasAuthor = in_author
                if in_genre:
                    b.hasGenre = in_genre
                b.hasPrice = float(in_price)
                b.availableQuantity = int(in_qty)
                b.restockThreshold = int(in_thr)
                inv = onto.Inventory(f"inv_{new_id}")
                inv.tracksBook = b
                inv.currentQuantity = int(in_qty)
                st.success(f"Added book '{title}' (qty {int(in_qty)}, thr {int(in_thr)})")
    # Existing books & delete
    books_df = pd.DataFrame([{ 'ID': b.name, 'Title': _first(b.hasTitle,b.name)} for b in onto.Book.instances()])
    if not books_df.empty:
        sel = st.multiselect("Select books to delete", options=books_df['Title'].tolist())
        if st.button("Delete selected books"):
            del_count = 0
            for b in list(onto.Book.instances()):
                if _first(b.hasTitle, b.name) in sel:
                    # delete inventory first, then book
                    inv = get_inventory_for_book(b)
                    if inv is not None:
                        destroy_entity(inv)
                    destroy_entity(b)
                    del_count += 1
            st.success(f"Deleted {del_count} book(s)")
    else:
        st.info("No books yet.")

    st.markdown("---")
    # Customers
    st.subheader("Customers")
    col1, col2 = st.columns([2,1])
    with col1:
        cust_name = st.text_input("New customer name", key="cust_name")
    with col2:
        if st.button("Add customer"):
            if not cust_name.strip():
                st.warning("Enter a name")
            else:
                cname = cust_name.strip()
                cid = f"customer_{''.join(ch.lower() if ch.isalnum() else '_' for ch in cname).strip('_') or 'c'}"
                # ensure uniqueness
                exists = {c.name for c in onto.Customer.instances()}
                i=1; nid=cid
                while nid in exists:
                    i+=1; nid=f"{cid}_{i}"
                c = onto.Customer(nid)
                c.hasName = cname
                st.success(f"Added customer '{cname}'")
    custs = [ _first(c.hasName, c.name) for c in onto.Customer.instances() ]
    if custs:
        del_custs = st.multiselect("Delete customers", options=custs, key="del_custs")
        if st.button("Delete selected customers"):
            d=0
            for c in list(onto.Customer.instances()):
                if _first(c.hasName, c.name) in del_custs:
                    destroy_entity(c); d+=1
            st.success(f"Deleted {d} customer(s)")
    else:
        st.caption("No customers yet.")

    st.markdown("---")
    # Employees
    st.subheader("Employees")
    col3, col4 = st.columns([2,1])
    with col3:
        emp_name = st.text_input("New employee name", key="emp_name")
    with col4:
        if st.button("Add employee"):
            if not emp_name.strip():
                st.warning("Enter a name")
            else:
                ename = emp_name.strip()
                eid = f"employee_{''.join(ch.lower() if ch.isalnum() else '_' for ch in ename).strip('_') or 'e'}"
                exists = {e.name for e in onto.Employee.instances()}
                i=1; nid=eid
                while nid in exists:
                    i+=1; nid=f"{eid}_{i}"
                e = onto.Employee(nid)
                e.hasName = ename
                st.success(f"Added employee '{ename}'")
    emps = [ _first(e.hasName, e.name) for e in onto.Employee.instances() ]
    if emps:
        del_emps = st.multiselect("Delete employees", options=emps, key="del_emps")
        if st.button("Delete selected employees"):
            d=0
            for e in list(onto.Employee.instances()):
                if _first(e.hasName, e.name) in del_emps:
                    destroy_entity(e); d+=1
            st.success(f"Deleted {d} employee(s)")
    else:
        st.caption("No employees yet.")

with st.sidebar:
    st.header("Controls")
    rt = st.number_input("Restock threshold", min_value=0, max_value=100, value=st.session_state.restock_threshold, step=1)
    ra = st.number_input("Restock amount", min_value=0, max_value=100, value=st.session_state.restock_amount, step=1)
    colA, colB = st.columns(2)
    with colA:
        reset_keep = st.button("Reset simulation\n(keep data)")
    with colB:
        reset_sample = st.button("Load sample\n(reset all)")

    if reset_keep:
        st.session_state.restock_threshold = int(rt)
        st.session_state.restock_amount = int(ra)
        st.session_state.model = LibraryModel(
            restock_threshold=st.session_state.restock_threshold,
            restock_amount=st.session_state.restock_amount,
        )
        st.session_state.steps = 0
        st.session_state.inv_history = []
        st.session_state.purchases_history = []
        st.session_state.last_order_ids = set()
        st.session_state.event_feed = []
        st.session_state.events_seen = 0
        st.success("Simulation reset (kept current data).")

    if reset_sample:
        st.session_state.restock_threshold = int(rt)
        st.session_state.restock_amount = int(ra)
        reset_ontology()
        st.session_state.model = LibraryModel(
            restock_threshold=st.session_state.restock_threshold,
            restock_amount=st.session_state.restock_amount,
        )
        st.session_state.steps = 0
        st.session_state.inv_history = []
        st.session_state.purchases_history = []
        st.session_state.last_order_ids = set()
        st.session_state.event_feed = []
        st.session_state.events_seen = 0
        st.success("Loaded sample data and reset simulation.")

    st.markdown("---")
    step_once = st.button("Step once")
    step_n = st.number_input("Run N steps", min_value=1, max_value=1000, value=10, step=1)
    run_n = st.button("Run N steps ▶")
    st.markdown("---")
    if st.button("Run reasoner (SWRL)"):
        run_reasoner_safe()
        st.toast("Reasoner executed (see terminal logs for details)")

# Step controls
if step_once:
    st.session_state.model.step()
    st.session_state.steps += 1
    record_histories()
if run_n:
    for _ in range(int(step_n)):
        st.session_state.model.step()
        st.session_state.steps += 1
        record_histories()

# Summary metrics
col1, col2, col3 = st.columns(3)
col1.metric("Steps", st.session_state.steps)
col2.metric("Current step (model)", st.session_state.model.current_step)
col3.metric("Restock threshold", st.session_state.restock_threshold)

# Data + Exports
left, right = st.columns(2)
with left:
    st.subheader("Inventory")
    inv_df = pd.DataFrame(inventory_rows())
    st.dataframe(inv_df, use_container_width=True)
    # Export inventory CSV
    inv_buf = io.StringIO()
    writer = csv.DictWriter(inv_buf, fieldnames=list(inv_df.columns))
    writer.writeheader()
    for row in inv_df.to_dict(orient="records"):
        writer.writerow(row)
    st.download_button(
        label="Download Inventory CSV",
        data=inv_buf.getvalue().encode("utf-8"),
        file_name="inventory.csv",
        mime="text/csv",
    )
    lows = low_stock_fallback(st.session_state.restock_threshold)
    st.caption(f"Low-stock (fallback): {lows if lows else 'None'}")

with right:
    st.subheader("Orders")
    orders_df = pd.DataFrame(orders_rows())
    st.dataframe(orders_df, use_container_width=True)
    # Export orders CSV
    ord_buf = io.StringIO()
    if not orders_df.empty:
        writer = csv.DictWriter(ord_buf, fieldnames=list(orders_df.columns))
        writer.writeheader()
        for row in orders_df.to_dict(orient="records"):
            writer.writerow(row)
    else:
        ord_buf.write("Order ID,Buyer,Item,Qty,Unit Price,Time\n")
    st.download_button(
        label="Download Orders CSV",
        data=ord_buf.getvalue().encode("utf-8"),
        file_name="orders.csv",
        mime="text/csv",
    )

# Charts
st.subheader("Charts")
chart_left, chart_right = st.columns(2)
with chart_left:
    st.caption("Current stock vs threshold")
    if not inv_df.empty:
        inv_df_chart = inv_df.copy()
        def state_color(state: str) -> str:
            return {"Low": "#dc2626", "At threshold": "#f59e0b", "OK": "#16a34a"}.get(state, "#6b7280")
        inv_df_chart["Color"] = inv_df_chart["State"].map(state_color)
        bar = alt.Chart(inv_df_chart).mark_bar().encode(
            x=alt.X("Title:N", sort=None),
            y=alt.Y("Qty:Q"),
            color=alt.Color("State:N", scale=alt.Scale(domain=["Low","At threshold","OK"], range=["#dc2626","#f59e0b","#16a34a"])),
            tooltip=["Title","Qty","Threshold","State","Price"],
        )
        # Threshold rule per bar is not trivial; show as points overlayed for clarity
        thr_points = alt.Chart(inv_df_chart).mark_point(shape="triangle-down", size=120, color="#f59e0b").encode(
            x=alt.X("Title:N"), y=alt.Y("Threshold:Q"), tooltip=["Title","Threshold"],
        )
        st.altair_chart((bar + thr_points), use_container_width=True)
    else:
        st.info("No inventory to chart.")

with chart_right:
    st.caption("Inventory over steps vs threshold")
    inv_hist_df = pd.DataFrame(st.session_state.get("inv_history", []))
    if not inv_hist_df.empty:
        qty_line = alt.Chart(inv_hist_df).mark_line(point=True, color="#2563eb").encode(
            x=alt.X("step:Q", title="Step"),
            y=alt.Y("Qty:Q"),
            color=alt.Color("Title:N", legend=alt.Legend(title="Book")),
            tooltip=["step:Q","Title:N","Qty:Q","Threshold:Q"],
        )
        thr_line = alt.Chart(inv_hist_df).mark_line(strokeDash=[6,4], color="#f59e0b").encode(
            x=alt.X("step:Q"), y=alt.Y("Threshold:Q"), color=alt.Color("Title:N", legend=None),
        )
        st.altair_chart(qty_line + thr_line, use_container_width=True)
    else:
        st.info("Step the simulation to build the time series.")

st.subheader("Purchases over time")
p_hist_df = pd.DataFrame(st.session_state.get("purchases_history", []))
if not p_hist_df.empty:
    bars = alt.Chart(p_hist_df).mark_bar().encode(
        x=alt.X("step:Q", title="Step"),
        y=alt.Y("Count:Q", title="Purchases"),
        color=alt.Color("Title:N", title="Book"),
        tooltip=["step:Q", "Title:N", "Count:Q"],
    )
    st.altair_chart(bars, use_container_width=True)
else:
    st.info("No purchases recorded yet. Step the simulation to generate data.")

# Purchases summary
st.subheader("Purchases by customer")
rows = []
for c in onto.Customer.instances():
    rows.append({
        "Customer": _first(c.hasName, c.name),
        "Purchases": ", ".join(_first(b.hasTitle, b.name) for b in (c.purchases or [])),
    })
st.table(rows)

# Event timeline
st.subheader("Event timeline")
with st.container(border=True):
    if st.session_state.event_feed:
        for evt in reversed(st.session_state.event_feed[-30:]):  # show last 30 events
            st.markdown(render_event(evt), unsafe_allow_html=True)
    else:
        st.info("No events yet. Step the simulation to see purchases, low-stock triggers, and restocks.")

# Legend
with st.expander("Legend: colors and thresholds"):
    st.markdown(
        "- State colors: <span style='color:#16a34a;'>OK</span>, <span style='color:#f59e0b;'>At threshold</span>, <span style='color:#dc2626;'>Low</span><br>"
        "- Bars show current quantity; orange triangles mark each title's threshold.<br>"
        "- Time series: blue line = quantity, orange dashed = threshold.<br>"
        "- Event badges: blue=purchase, orange=low stock trigger, green=restock, red=out-of-stock.",
        unsafe_allow_html=True,
    )

st.caption("Tip: Use the sidebar to step or run multiple steps, adjust thresholds, and reset the simulation. Colors and badges highlight threshold-driven behavior in real time.")

with st.expander("Save / Load", expanded=False):
    st.subheader("Save current data")
    snap = build_snapshot()
    json_bytes = json.dumps(snap, indent=2).encode("utf-8")
    st.download_button("Download JSON snapshot", data=json_bytes, file_name="bookstore_snapshot.json", mime="application/json")
    st.caption("Includes settings, books + inventory, customers, employees, and orders.")

    st.subheader("Load data from JSON")
    up = st.file_uploader("Choose a snapshot JSON file", type=["json"])
    if up is not None:
        try:
            incoming = json.loads(up.read().decode("utf-8"))
            st.success("File parsed. Choose a load option below.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Load (replace all)"):
                    load_snapshot(incoming, replace=True)
                    st.success("Loaded snapshot and reset simulation.")
            with c2:
                if st.button("Load (append)"):
                    load_snapshot(incoming, replace=False)
                    st.success("Appended snapshot and reset simulation.")
        except Exception as e:
            st.error(f"Failed to parse JSON: {e}")
