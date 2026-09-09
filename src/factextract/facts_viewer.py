import streamlit as st
from pydantic import ValidationError
from typing import Optional

from factextract import module, store
from factextract.config import Config, get_config, set_config
from factextract.schema import Fact, Island


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
        return f"{days // 365}y"
    if days >= 30:
        return f"{days // 30}mo"
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
            f"""<div style="border-left: 4px solid {color}; padding: 12px 16px; margin: 10px 0; border-radius: 0 8px 8px 0; background: #f8f9fa;">
                <strong>{icon} {island.relation_type}</strong><br><em>{island.reason}</em>
            </div>""",
            unsafe_allow_html=True,
        )
        for fact in facts:
            render_fact(fact)
        st.divider()


def render_settings() -> None:
    with st.sidebar:
        st.header("Settings")
        cfg = get_config()
        graph_db_path = st.text_input("Graph DB path", value=str(cfg.graph_db_path))
        metadata_db_path = st.text_input("Metadata DB path", value=str(cfg.metadata_db_path))
        data_dir = st.text_input("Data directory", value=str(cfg.data_dir))
        llm_model = st.text_input("LLM model", value=cfg.llm_model)
        llm_base_url = st.text_input("LLM base URL", value=cfg.llm_base_url or "")
        if st.button("Apply settings", use_container_width=True):
            try:
                new_cfg = Config(
                    graph_db_path=graph_db_path,
                    metadata_db_path=metadata_db_path,
                    data_dir=data_dir,
                    llm_model=llm_model,
                    llm_base_url=llm_base_url or None,
                    ingest=cfg.ingest,
                )
            except ValidationError as e:
                st.error(f"Invalid settings: {e}")
                return
            set_config(new_cfg)
            store.init_db()
            st.success("Settings applied.")
            st.rerun()


def render_pipelines() -> None:
    st.subheader("Pipelines")
    c1, c2, c3 = st.columns(3)
    if c1.button("1. Ingest sources", use_container_width=True):
        with st.spinner("Scanning data dir..."):
            n = len(module.run_source_ingestion())
        st.success(f"Stored {n} sources.")
    if c2.button("2. Extract facts", use_container_width=True):
        with st.spinner("Extracting facts (LLM)..."):
            n = len(module.run_fact_extraction())
        st.success(f"Stored {n} facts.")
    if c3.button("3. Extract islands", use_container_width=True):
        with st.spinner("Grouping into islands (agent)..."):
            n = len(module.run_island_extraction())
        st.success(f"Stored {n} islands.")
    st.divider()


def sidebar_filter() -> tuple[Optional[str], str]:
    with st.sidebar:
        st.header("Filters")
        category = st.radio("Category", options=["All", "Corroboration", "Contradiction", "Weak", "Unaffiliated"], index=0)
        search = st.text_input("Search", placeholder="Keywords...")
        return category, search


def main():
    st.set_page_config(page_title="Fact Viewer", page_icon="🔍", layout="wide")
    st.title("Fact Extraction Viewer")
    get_config()
    store.init_db()
    render_settings()
    render_pipelines()
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


if __name__ == "__main__":
    main()
