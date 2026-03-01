"""
Streamlit demo UI for the Simulation Agent.

Connects to the FastAPI backend (default: http://localhost:8000).
Run backend first:  uvicorn api.app:app --reload --port 8000
Run UI:             streamlit run streamlit_app.py
"""
import streamlit as st
import requests

API_BASE = "http://localhost:8000/api/v1"

st.set_page_config(
    page_title="Simulation Agent",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🎯 Simulation Agent")
    st.caption("LangGraph · Neo4j BKG · PostgreSQL")
    st.divider()

    # Health status
    if st.button("🔄 Check Health"):
        try:
            r = requests.get(f"{API_BASE}/health", timeout=5)
            h = r.json()
            col1, col2 = st.columns(2)
            col1.metric("Neo4j", h.get("neo4j", "?"))
            col2.metric("PostgreSQL", h.get("postgres", "?"))
            status = h.get("status", "?")
            if status == "ok":
                st.success(f"Overall: {status}")
            else:
                st.warning(f"Overall: {status}")
        except Exception as e:
            st.error(f"API offline — {e}")

    st.divider()
    tool = st.radio(
        "Choose interface",
        ["🤖 Agent", "🔍 BKG Explorer", "🐍 Python Sandbox"],
        label_visibility="collapsed",
    )

# ── Agent tab ────────────────────────────────────────────────────────────────
if tool == "🤖 Agent":
    st.title("Run Simulation")
    st.markdown(
        "Ask a natural-language question. The agent autonomously explores Neo4j/PostgreSQL "
        "and returns a PM-ready answer."
    )

    query = st.text_area(
        "Your query",
        height=100,
        placeholder="e.g. How many GC sites reached NTP in Q1? What is the average completion rate?",
    )

    if st.button("▶ Simulate", type="primary", use_container_width=True):
        if not query.strip():
            st.warning("Please enter a query.")
        else:
            with st.spinner("Running agent pipeline…"):
                try:
                    r = requests.post(
                        f"{API_BASE}/simulate",
                        json={"query": query},
                        timeout=180,
                    )
                    r.raise_for_status()
                    data = r.json()
                except requests.HTTPError as e:
                    st.error(f"API error: {e.response.text}")
                    st.stop()
                except Exception as e:
                    st.error(f"Could not reach API: {e}")
                    st.stop()

            tab_resp, tab_data, tab_calc, tab_log = st.tabs(
                ["📋 Response", "📊 Data Summary", "🔢 Calculations", "🔍 Execution Log"]
            )

            with tab_resp:
                response_text = data.get("final_response", "")
                if response_text:
                    st.markdown(response_text)
                else:
                    st.info("No response generated.")
                if data.get("errors"):
                    with st.expander("⚠ Errors"):
                        for err in data["errors"]:
                            st.text(err)

            with tab_data:
                ds = data.get("data_summary", {})
                if ds:
                    st.json(ds)
                else:
                    st.info("No structured data returned.")

            with tab_calc:
                calc = data.get("calculations", "")
                if calc:
                    st.code(calc, language="text")
                else:
                    st.info("No calculation trace.")

            with tab_log:
                msgs = data.get("messages", [])
                if msgs:
                    for msg in msgs:
                        agent = msg.get("agent", "?")
                        content = msg.get("content", "")
                        st.text(f"[{agent:>25}]  {content}")
                else:
                    st.info("No execution log.")
                st.caption(f"Traversal steps: {data.get('traversal_steps', 0)}")

# # ── BKG Explorer ─────────────────────────────────────────────────────────────
# elif tool == "🔍 BKG Explorer":
#     st.title("Business Knowledge Graph Explorer")

#     mode = st.selectbox(
#         "Query mode",
#         ["get_node", "find_relevant", "traverse", "diagnostic", "schema"],
#         format_func=lambda m: {
#             "get_node": "get_node — fetch by ID",
#             "find_relevant": "find_relevant — keyword search",
#             "traverse": "traverse — walk relationships",
#             "diagnostic": "diagnostic — metric details",
#             "schema": "schema — table overview",
#         }[m],
#     )

#     payload: dict = {"mode": mode}

#     if mode == "get_node":
#         payload["node_id"] = st.text_input("Node ID", "GeneralContractor")

#     elif mode == "find_relevant":
#         payload["question"] = st.text_input(
#             "Keywords / question", "contractor site project"
#         )

#     elif mode == "traverse":
#         col1, col2 = st.columns([2, 1])
#         payload["start"] = col1.text_input("Start node ID", "GeneralContractor")
#         payload["depth"] = col2.slider("Depth", 1, 4, 2)
#         rel = st.text_input("Relationship type filter (optional)", "")
#         if rel:
#             payload["rel_type"] = rel

#     elif mode == "diagnostic":
#         payload["metric_id"] = st.text_input("Metric ID", "")

#     elif mode == "schema":
#         tbl = st.text_input("Table name (leave blank for full overview)", "")
#         if tbl:
#             payload["table_name"] = tbl

#     if st.button("Query BKG", type="primary", use_container_width=True):
#         with st.spinner("Querying…"):
#             try:
#                 r = requests.post(f"{API_BASE}/bkg/query", json=payload, timeout=30)
#                 r.raise_for_status()
#                 st.json(r.json())
#             except requests.HTTPError as e:
#                 st.error(f"Error: {e.response.text}")
#             except Exception as e:
#                 st.error(f"Error: {e}")

# ── Python Sandbox ───────────────────────────────────────────────────────────
elif tool == "🐍 Python Sandbox":
    st.title("Python Sandbox")
    st.markdown(
        "Execute Python code against PostgreSQL. "
        "`conn`, `pd`, `np`, `go`, `px`, `json` are pre-imported. "
        "Set `result = {...}` to return data."
    )

    default_code = """\
# Example: list tables in the database
df = pd.read_sql(
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema = 'public' ORDER BY table_name",
    conn,
)
result = {"tables": df.to_dict(orient="records"), "count": len(df)}"""

    code = st.text_area("Code", value=default_code, height=300)
    timeout = st.slider("Timeout (seconds)", 5, 120, 30)

    if st.button("▶ Execute", type="primary", use_container_width=True):
        if not code.strip():
            st.warning("Please enter some code.")
        else:
            with st.spinner("Executing…"):
                try:
                    r = requests.post(
                        f"{API_BASE}/sandbox/execute",
                        json={"code": code, "timeout_seconds": timeout},
                        timeout=timeout + 10,
                    )
                    r.raise_for_status()
                    res = r.json()
                except requests.HTTPError as e:
                    st.error(f"API error: {e.response.text}")
                    st.stop()
                except Exception as e:
                    st.error(f"Error: {e}")
                    st.stop()

            if res.get("status") == "success":
                st.success("Execution successful")
                result = res.get("result", {})
                if result:
                    st.json(result)
                else:
                    st.info("Code ran successfully but returned no result.")
            else:
                st.error(f"Error: {res.get('error')}")
                if res.get("traceback"):
                    with st.expander("Traceback"):
                        st.code(res["traceback"], language="python")
