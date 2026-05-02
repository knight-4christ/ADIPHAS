import streamlit as st
import os
import uuid
import api_client
from datetime import datetime
from modules import now_wat

def render(is_overlay=False):
    if not is_overlay:
        st.markdown("### 🤖 ADIPHAS Health Advisory Chat")
        st.caption("AI-powered clinical assistant and symptom analyzer. Uses Hybrid-RAG to fuse local health alerts with global medical knowledge.")
    
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
    header_col1, header_col2, header_col3, header_col4 = st.columns([2, 1, 0.7, 0.8])
    
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
        web_search_on = st.toggle("🌐 Web", value=True, help="Include live internet results via Tavily")
    
    with header_col4:
        if st.button("➕ New Chat", width="stretch"):
            new_id = str(uuid.uuid4())[:8]
            st.session_state.chat_threads[new_id] = {
                "name": f"Chat {len(st.session_state.chat_threads)+1}",
                "messages": [],
                "mode": selected_model,
                "timestamp": now_wat()
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
            "timestamp": now_wat()
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
    
    # Thread Actions (Rename/Delete/Download)
    t_act1, t_act3, t_act4 = st.columns([4, 1, 1])
    with t_act1:
        st.caption(f"🧵 Mode: `{active_thread['mode']}` | Created: {active_thread['timestamp'].strftime('%H:%M')}")
    with t_act3:
        if active_thread["messages"]:
            conv_text_plain = "\n".join([f"{'You' if m['role'] == 'user' else 'AI'}: {m['content']}" for m in active_thread["messages"]])
            st.download_button(
                "📝 Text",
                data=conv_text_plain,
                file_name=f"adiphas_chat_{now_wat().strftime('%Y%m%d_%H%M')}.txt",
                mime="text/plain",
                width="stretch",
                key=f"dl_chat_txt_{st.session_state.active_thread_id}"
            )
    with t_act4:
        if st.button("🗑️ Delete", type="secondary", width="stretch"):
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
            with st.spinner("🔍 Retrieving local & global intelligence..." if web_search_on else "🔍 Searching local knowledge base..."):
                # Hybrid RAG Context Retrieval (force_combine toggled by Web Search switch)
                rag_res = api_client.advisory_search(user_input, force_combine=web_search_on)
                context_str = ""
                source = "unknown"
                results = []
                if rag_res and not rag_res.get("error"):
                    source = rag_res.get("source", "unknown")
                    results = rag_res.get("results", [])
                    if results:
                        context_str = "\n\n[CONTEXT FROM ADIPHAS INTELLIGENCE]\n"
                        for r in results[:5]:
                            c = r.get("content") or r.get("snippet") or str(r)
                            context_str += f"- {c}\n"
                        if source == "combined":
                            context_str += "\nThe above includes BOTH local disease surveillance data AND live internet intelligence. Use all available context to inform your response."
                        elif source == "web_search":
                            context_str += "\nThe above is from LIVE internet sources. Use these real-time signals to inform your response."
                        else:
                            context_str += "\nThe above is from the local ADIPHAS knowledge base. Use it to inform your response if relevant."

                try:
                    # Determine reasoning mode
                    enable_reasoning = (active_thread["mode"] == "Deep Reasoning (Hunter/Step)")
                    
                    # Use backend-orchestrated chat
                    user_loc = st.session_state.get("user_location", "Unknown Location")
                    chat_res = api_client.advisory_chat(
                        active_thread["messages"], 
                        st.session_state.token, 
                        enable_reasoning=enable_reasoning,
                        context=context_str,
                        location=user_loc
                    )
                    
                    if chat_res and not chat_res.get("error"):
                        reply = chat_res.get("reply", "⚠️ AI connection interrupted.")
                    else:
                        reply = f"⚠️ Backend Error: {chat_res.get('detail', 'Unknown error')}"
                except Exception as e:
                    reply = f"⚠️ Chat system error: {str(e)}"
            st.markdown(reply)
            if context_str:
                # Label sources clearly
                source_labels = {
                    "combined": "🌐 Combined (Local RAG + Live Web)",
                    "web_search": "🌐 Live Web Intelligence (Tavily)",
                    "local_rag": "📁 Local Knowledge Base (RAG)",
                    "local_rag_fallback": "📁 Local Knowledge Base (Fallback)",
                }
                source_label = source_labels.get(source, f"Source: {source.upper()}")
                
                with st.expander(f"📚 Sources Used — {source_label}"):
                    st.caption(f"Retrieved at {now_wat().strftime('%H:%M:%S on %b %d, %Y')}")
                    if results:
                        for r in results[:5]:
                            content = r.get("content") or r.get("snippet") or str(r)
                            url = r.get("url", "")
                            if url:
                                st.markdown(f"🔗 [{url}]({url})")
                            st.write(content[:300] + "..." if len(str(content)) > 300 else content)
                            st.divider()

        active_thread["messages"].append({"role": "assistant", "content": reply})
        if not is_overlay: st.rerun() # Rerun to update the sidebar title if it changed

