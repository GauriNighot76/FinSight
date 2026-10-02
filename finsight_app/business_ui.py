"""Business onboarding and management UI for the authenticated workspace."""

from typing import Any

from services import business_service


BUSINESS_TYPES = [
    "Select business type",
    "Retail",
    "Medical / Pharmacy",
    "Hotel / Hospitality",
    "Clinic / Healthcare",
    "Services",
    "Manufacturing",
    "Trading / Wholesale",
    "Restaurant / Food",
    "E-commerce",
    "Professional Services",
    "Education",
    "Technology",
    "Agriculture / Agribusiness",
    "Construction",
    "Logistics",
    "Other",
]


def _clear_business_draft(st: Any) -> None:
    for key in (
        "business_create_step",
        "business_draft",
        "business_name_input",
        "business_type_input",
        "business_type_other",
        "business_legal_input",
        "business_email_input",
        "business_phone_input",
    ):
        st.session_state.pop(key, None)


def render_create_business(st: Any, token: str, *, first_business: bool = False) -> bool:
    step = int(st.session_state.get("business_create_step", 1))
    st.subheader("Set up your business" if first_business else "Create Business")
    st.caption("Step 1 of 2 — Business Details" if step == 1 else "Step 2 of 2 — Confirm Business")

    if step == 1:
        name = st.text_input("Business Name *", key="business_name_input")
        business_type = st.selectbox(
            "Business Type / Industry *",
            BUSINESS_TYPES,
            index=0,
            key="business_type_input",
        )
        custom_type = ""
        if business_type == "Other":
            custom_type = st.text_input(
                "Enter business type *",
                key="business_type_other",
            )
        legal_id = st.text_input(
            "Legal / Registration Identifier",
            key="business_legal_input",
        )
        email = st.text_input("Business Email", key="business_email_input")
        phone = st.text_input("Business Phone", key="business_phone_input")
        if st.button("Next", type="primary"):
            final_type = custom_type.strip() if business_type == "Other" else business_type
            if len((name or "").strip()) < 2:
                st.error("Enter a business name.")
                return False
            if final_type in {"", "Select business type"}:
                st.error("Select a business type.")
                return False
            st.session_state["business_draft"] = {
                "business_name": name.strip(),
                "business_type": final_type,
                "legal_identifier": (legal_id or "").strip(),
                "contact_email": (email or "").strip(),
                "contact_phone": (phone or "").strip(),
            }
            st.session_state["business_create_step"] = 2
            st.rerun()
        return False

    draft = st.session_state.get("business_draft")
    if not isinstance(draft, dict):
        st.session_state["business_create_step"] = 1
        st.rerun()

    with st.container(border=True):
        st.markdown(f"### {draft['business_name']}")
        st.write("Business Type:", draft["business_type"])
        if draft.get("legal_identifier"):
            st.write("Registration Identifier:", draft["legal_identifier"])
        if draft.get("contact_email"):
            st.write("Email:", draft["contact_email"])
        if draft.get("contact_phone"):
            st.write("Phone:", draft["contact_phone"])

    left, right = st.columns(2)
    if left.button("Back"):
        st.session_state["business_create_step"] = 1
        st.rerun()
    if right.button("Create Business & Continue", type="primary"):
        result = business_service.create_business(token, draft)
        if not result.get("success"):
            st.error(result.get("message", "Business creation failed."))
            return False
        business_id = result["business"]["business_id"]
        ready = business_service.ensure_business_ready(token, business_id)
        if not ready.get("success"):
            st.error(
                "The business was created, but its transaction workspace could "
                "not be prepared. Please try again."
            )
            return False
        st.session_state["selected_business_id"] = business_id
        st.session_state["pending_page"] = "Upload Transactions"
        _clear_business_draft(st)
        st.success("Business created successfully.")
        st.rerun()
    return False


def _clear_deleted_business_state(st: Any, business_id: str) -> None:
    """Clear only this business's existing scoped state and selection."""
    for key in list(st.session_state):
        if (key.startswith((f"upload_{business_id}_", f"{business_id}_",
                            f"report_section_{business_id}_", f"delete_business_{business_id}_"))
                or (key.startswith(("report_", "scheme_")) and key.endswith(f"_{business_id}"))
                or key in {f"prepare_csv_{business_id}", f"use_business_{business_id}"}):
            st.session_state.pop(key, None)
    for key in ("selected_business_id", "business_selector"):
        if st.session_state.get(key) == business_id:
            st.session_state.pop(key, None)


def _render_delete_business(st: Any, token: str, business: dict) -> None:
    if business.get("membership", {}).get("membership_role") != "owner":
        return
    business_id = business["business_id"]
    name = business["business_name"]
    prefix = f"delete_business_{business_id}_"
    with st.expander("Danger Zone — Delete Business"):
        st.write("This business will be removed from your active FinSight workspace. "
                 "Existing financial records will be retained for data integrity.")
        if not st.session_state.get(prefix + "pending"):
            if st.button("Delete Business", key=prefix + "open"):
                st.session_state[prefix + "pending"] = True
                st.rerun()
            return
        st.write(f'Delete "{name}"?')
        confirmation = st.text_input(f'Type "{name}" to confirm.', key=prefix + "name")
        cancel, confirm = st.columns(2)
        if cancel.button("Cancel", key=prefix + "cancel"):
            st.session_state.pop(prefix + "pending", None)
            st.session_state.pop(prefix + "name", None)
            st.rerun()
        if confirm.button("Confirm Delete", key=prefix + "confirm"):
            if confirmation.strip() != name:
                st.error("Enter the business name exactly to confirm deletion.")
                return
            result = business_service.delete_business(token, business_id, confirmation)
            if not result.get("success"):
                st.error(result.get("message", "Business could not be deleted."))
                return
            _clear_deleted_business_state(st, business_id)
            st.session_state["pending_page"] = "Overview"
            st.success("Business deleted successfully.")
            st.rerun()


def render_manage_businesses(
    st: Any,
    token: str,
    businesses: list[dict[str, Any]],
    selected_business_id: str | None,
) -> bool:
    st.subheader("Manage Businesses")
    st.caption("Switch between businesses or create another independent workspace.")
    if st.button("+ Create Business", type="primary"):
        st.session_state["pending_page"] = "Create Business"
        _clear_business_draft(st)
        st.rerun()

    for business in businesses:
        with st.container(border=True):
            left, right = st.columns([3, 1])
            left.markdown(f"**{business['business_name']}**")
            left.caption(
                f"{business.get('business_type') or 'Business type not set'} · "
                f"Role: {business.get('membership', {}).get('membership_role', 'member').title()}"
            )
            if business["business_id"] == selected_business_id:
                right.success("Current")
            elif right.button(
                "Use Business",
                key=f"use_business_{business['business_id']}",
            ):
                st.session_state["selected_business_id"] = business["business_id"]
                st.session_state["pending_page"] = "Overview"
                st.rerun()
            _render_delete_business(st, token, business)
    return True
