import streamlit as st
import os
import uuid
import api_client
from datetime import datetime

def render(is_overlay=False):
    if not is_overlay:
        st.markdown("### 🤖 ADIPHAS Health Advisory Chat")
    
    # 1. State Management (Conversations)
    if "chat_threads" not in st.session_state:
        st.session_state.chat_threads = {}
    if "active_thread_id" not in st.session_state:
        st.session_state.active_thread_id = None
        
    # Check Auth (Required for backend chat)
    if not st.session_state.get("authenticated"):
        st.warning("🔐 Please login to access the bio-aware Advisory Chat.")
        return

    # 2. Main Chat Panel - Consolidated Header
    header_col1, header_col2, header_col3 = st.columns([2, 1, 1])
    
    with header_col1:
        # Use a selectbox for thread switching instead of sidebar radio
        if st.session_state.chat_threads:
            thread_options = list(st.session_state.chat_threads.keys())
            
            # Auto-selection logic
            if not st.session_state.get("active_thread_id") or st.session_state.active_thread_id not in thread_options:
                st.session_state.active_thread_id = thread_options[-1]
            
            def fmt_thread(tid):
                return st.session_state.chat_threads[tid]["name"]
                
            st.selectbox(
                "Active Conversation",
                options=thread_options,
                format_func=fmt_thread,
                key="active_thread_id",
                label_visibility="collapsed"
            )
        else:
            st.info("Start a new conversation below 👇")

    with header_col2:
        selected_model = st.selectbox(
            "AI Mode",
            ["Balanced (Gemini)", "Deep Reasoning (Hunter/Step)", "Resilient (Universal Fallback)"],
            index=0,
            label_visibility="collapsed"
        )
    
    with header_col3:
        if st.button("➕ New Chat", use_container_width=True):
            new_id = str(uuid.uuid4())[:8]
            st.session_state.chat_threads[new_id] = {
                "name": f"Chat {len(st.session_state.chat_threads)+1}",
                "messages": [],
                "mode": selected_model,
                "timestamp": datetime.now()
            }
            st.session_state.active_thread_id = new_id
            if not is_overlay: st.rerun()

    # --- Overlay Auto-Init ---
    if is_overlay and not st.session_state.chat_threads:
        new_id = "quick_chat"
        st.session_state.chat_threads[new_id] = {
            "name": "Quick Assistant",
            "messages": [],
            "mode": "Balanced (Gemini)",
            "timestamp": datetime.now()
        }
        st.session_state.active_thread_id = new_id

    if not st.session_state.chat_threads:
        if is_overlay:
            st.info("Please start a new chat session.")
            return
        st.stop()
        
    if not st.session_state.active_thread_id:
        # Final safety net
        st.session_state.active_thread_id = list(st.session_state.chat_threads.keys())[-1]
        if not is_overlay: st.rerun()

    active_thread = st.session_state.chat_threads[st.session_state.active_thread_id]
    
    # Thread Actions (Rename/Delete)
    t_act1, t_act2, t_act3 = st.columns([3, 1, 1])
    with t_act1:
        st.caption(f"🧵 Mode: `{active_thread['mode']}` | Created: {active_thread['timestamp'].strftime('%H:%M')}")
    with t_act3:
        if st.button("🗑️ Delete", type="secondary", use_container_width=True):
            del st.session_state.chat_threads[st.session_state.active_thread_id]
            st.session_state.active_thread_id = None
            if not is_overlay: st.rerun()


    # Render History
    for msg in active_thread["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Accept Input
    user_input = st.chat_input("Ask about disease outbreaks, symptoms, or health advisories...")

    if user_input:
        # Save user message
        active_thread["messages"].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Name the thread based on the first prompt (Dynamic Renaming)
        if len(active_thread["messages"]) == 1:
            short_name = " ".join(user_input.split()[:4])
            active_thread["name"] = f"{short_name}..."

        # Stream AI Response
        with st.chat_message("assistant"):
            with st.spinner("Retrieving local & global intelligence..."):
                # Hybrid RAG Context Retrieval
                rag_res = api_client.advisory_search(user_input)
                context_str = ""
                if rag_res and not rag_res.get("error"):
                    source = rag_res.get("source", "unknown")
                    results = rag_res.get("results", [])
                    if results:
                        context_str = "\n\n[CONTEXT FROM ADIPHAS INTELLIGENCE]\n"
                        for r in results[:3]:
                            c = r.get("content") or r.get("snippet") or str(r)
                            context_str += f"- {c}\n"
                        context_str += "\nUse the above context to inform your response if relevant. Refine your advice based on these real-time signals."

                try:
                    # Determine reasoning mode
                    enable_reasoning = (active_thread["mode"] == "Deep Reasoning (Hunter/Step)")
                    
                    # Use backend-orchestrated chat
                    chat_res = api_client.advisory_chat(
                        active_thread["messages"], 
                        st.session_state.token, 
                        enable_reasoning=enable_reasoning
                    )
                    
                    if chat_res and not chat_res.get("error"):
                        reply = chat_res.get("reply", "⚠️ AI connection interrupted.")
                    else:
                        reply = f"⚠️ Backend Error: {chat_res.get('detail', 'Unknown error')}"
                except Exception as e:
                    reply = f"⚠️ Chat system error: {str(e)}"
            st.markdown(reply)
            if context_str:
                with st.expander("📚 Sources Used (RAG)"):
                    st.caption(f"Source: {source.upper()}")
                    if results:
                        for r in results[:3]:
                            st.write(r.get("content") or r.get("snippet") or str(r))

        active_thread["messages"].append({"role": "assistant", "content": reply})
        if not is_overlay: st.rerun() # Rerun to update the sidebar title if it changed

