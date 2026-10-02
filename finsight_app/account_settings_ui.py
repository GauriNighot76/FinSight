"""Settings for the authenticated FinSight login account, not financial accounts."""
from services import auth_service


def render_account_settings(st, token):
    st.subheader("Account Settings")
    session = auth_service.validate_session(token)
    if not session.get("success"):
        st.error("Sign in to view account settings.")
        return
    st.write("Name:", session["user"]["username"])
    st.write("Email:", session["user"]["email"])
    requirements = auth_service.get_account_deletion_requirements(token)
    if not requirements.get("success"):
        st.error(requirements.get("message", "Account settings could not be loaded."))
        return
    with st.expander(":red[Danger Zone — Delete Account]"):
        st.write("Deleting your FinSight account will sign you out and remove your access to FinSight. "
                 "Historical records are retained. Delete any active businesses you own first.")
        if not st.session_state.get("account_delete_pending"):
            if st.button("Delete Account", key="account_delete_open"):
                st.session_state["account_delete_pending"] = True
                st.rerun()
            return
        # Form clears sensitive input after every submission; it is never copied to persistent state.
        with st.form("account_delete_confirmation", clear_on_submit=True):
            confirmation = st.text_input("Type DELETE MY ACCOUNT to continue:")
            password = st.text_input("Current Password", type="password") if requirements["requires_password"] else None
            cancel, confirm = st.columns(2)
            cancelled = cancel.form_submit_button("Cancel")
            submitted = confirm.form_submit_button("Delete Account")
        if cancelled:
            st.session_state.pop("account_delete_pending", None)
            st.rerun()
        if submitted:
            if confirmation.strip() != "DELETE MY ACCOUNT":
                st.error("Type DELETE MY ACCOUNT exactly to confirm.")
                return
            if requirements["requires_password"] and not password:
                st.error("Enter your current password.")
                return
            result = auth_service.delete_account(token, confirmation, password)
            if not result.get("success"):
                st.error(result.get("message", "Account could not be deleted."))
                for name in result.get("owned_businesses", []):
                    st.text(f"• {name}")
                return
            for key in list(st.session_state):
                del st.session_state[key]
            st.session_state["account_deleted_message"] = result["message"]
            st.rerun()
