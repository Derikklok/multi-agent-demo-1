import streamlit as st
import io, csv
import pandas as pd
import altair as alt
from bookstore_mas.model import LibraryModel
from bookstore_mas.ontology import onto, _first, reset_ontology, run_reasoner_safe

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

with st.sidebar:
    st.header("Controls")
    rt = st.number_input("Restock threshold", min_value=0, max_value=100, value=st.session_state.restock_threshold, step=1)
    ra = st.number_input("Restock amount", min_value=0, max_value=100, value=st.session_state.restock_amount, step=1)
    apply = st.button("Apply settings (reset)")
    if apply:
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
        st.success("Simulation reset with new settings.")

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
