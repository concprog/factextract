import streamlit as st
from typing import Optional

from .schema import Fact, Island, Source
from . import store


RELATION_COLORS = {
    "Corroboration": "#2196F3",
    "Contradiction": "#F44336",
    "Weak": "#FF9800",
}

RELATION_ICONS = {
    "Corroboration": "✅",
    "Contradiction": "⚠️",
    "Weak": "❓",
}


def format_window(seconds: int) -> str:
    days = seconds // 86400
    if days >= 365:
        years = days // 365
        return f"{years}y"
    if days >= 30:
        months = days // 30
        return f"{months}mo"
    return f"{days}d"


def render_fact(fact: Fact) -> None:
    with st.container():
        st.markdown(f"**{fact.content}**")
        st.caption(
            f"Source: {fact.source.title} | "
            f"Valid: {fact.time.strftime('%Y-%m-%d')} for {format_window(fact.window)}"
        )


def render_island(island: Island, facts: list[Fact]) -> None:
    color = RELATION_COLORS.get(island.relation_type, "#757575")
    icon = RELATION_ICONS.get(island.relation_type, "📌")

    with st.container():
        st.markdown(
            f"""<div style="
                border-left: 4px solid {color};
                padding: 12px 16px;
                margin: 10px 0;
                border-radius: 0 8px 8px 0;
                background: #f8f9fa;
            ">
                <strong>{icon} {island.relation_type}</strong><br>
                <em>{island.reason}</em>
            </div>""",
            unsafe_allow_html=True,
        )
        for fact in facts:
            render_fact(fact)
        st.divider()


def sidebar_filter() -> tuple[Optional[str], str]:
    with st.sidebar:
        st.header("Filters")
        category = st.radio(
            "Category",
            options=["All", "Corroboration", "Contradiction", "Weak", "Unaffiliated"],
            index=0,
        )
        search = st.text_input("Search", placeholder="Keywords...")
        return category, search


def main():
    st.set_page_config(page_title="Fact Viewer", page_icon="🔍", layout="wide")
    st.title("Fact Extraction Viewer")

    category, search = sidebar_filter()

    islands_with_facts = store.get_islands_with_facts()
    unaffiliated = store.get_unaffiliated_facts()

    filtered_islands: list[tuple[Island, list[Fact]]] = []
    filtered_unaffiliated: list[Fact] = []

    for island, facts in islands_with_facts:
        if category in ("All", island.relation_type):
            if search:
                matching = [f for f in facts if search.lower() in f.content.lower()]
                if matching or search.lower() in island.reason.lower():
                    filtered_islands.append((island, matching or facts))
            else:
                filtered_islands.append((island, facts))

    if category in ("All", "Unaffiliated"):
        if search:
            filtered_unaffiliated = [f for f in unaffiliated if search.lower() in f.content.lower()]
        else:
            filtered_unaffiliated = unaffiliated

    total_facts = sum(len(f) for _, f in filtered_islands) + len(filtered_unaffiliated)

    col1, col2, col3 = st.columns(3)
    col1.metric("Islands", len(filtered_islands))
    col2.metric("Unaffiliated Facts", len(filtered_unaffiliated))
    col3.metric("Total Facts", total_facts)

    st.divider()

    if category in ("All", "Unaffiliated") and filtered_unaffiliated:
        st.subheader("Unaffiliated Facts")
        for fact in filtered_unaffiliated:
            render_fact(fact)
        st.divider()

    for island, facts in filtered_islands:
        render_island(island, facts)

    if not filtered_islands and not filtered_unaffiliated:
        st.info("No facts match your filters.")

    st.download_button(
        label="Export JSON",
        data=st.session_state.get("export_data", "{}"),
        file_name="facts_export.json",
        mime="application/json",
    )


if __name__ == "__main__":
    main()
