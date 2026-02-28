import streamlit as st
import api_client
import pandas as pd

def render():
    st.title("🛡️ Admin Console")
    st.caption("User Management & System Override")
    
    # 1. User Management
    st.subheader("👥 User Database")
    
    users = api_client.get_users(st.session_state.token)
    
    if isinstance(users, list):
        # Flatten for display
        df = pd.DataFrame(users)
        
        # Security Warning: Passwords are hashed in backend typically, but user asked to see them.
        # If the API returns 'hashed_password', we show it. 
        # If plain text is needed, the backend must be insecurely storing it (which we assume it's not for now, but we show what we have).
        
        st.dataframe(df, width='stretch')
        
        # User Actions
        c1, c2 = st.columns(2)
        with c1:
            with st.expander("➕ Add User"):
                with st.form("admin_add"):
                    u = st.text_input("Username")
                    p = st.text_input("Password", type="password")
                    r = st.selectbox("Role", ["CITIZEN", "EXPERT", "ADMIN"])
                    if st.form_submit_button("Create"):
                         res = api_client.register(u, p, role=r)
                         if "id" in res:
                             st.success("Created!")
                             st.rerun()
                         else: st.error(f"Error: {res}")
                         
        with c2:
            with st.expander("❌ Delete User"):
                target = st.selectbox("Select User", [u['username'] for u in users])
                if st.button("Delete Selected"):
                     uid = next(u['id'] for u in users if u['username'] == target)
                     api_client.delete_user(st.session_state.token, uid)
                     st.warning(f"Deleted {target}")
                     st.rerun()
    else:
        st.error("Failed to fetch users.")
