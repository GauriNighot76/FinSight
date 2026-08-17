# Module 2 business and membership UI contract

Module 2 keeps global `users.role` separate from a user's role inside one
business. Never send a frontend user ID as the authenticated identity; every
operation derives the actor from the validated session token.

## Create a business

```python
from services.business_service import create_business

result = create_business(st.session_state["auth_token"], {
    "business_name": "Example Store",
    "legal_identifier": "optional GST or registration value",
    "contact_email": "office@example.com",
    "contact_phone": "9876543210",
})
```

The backend always makes the creator `owner`. A role included by the frontend
is ignored.

## List and select businesses

```python
from services.business_service import list_user_businesses, get_business

available = list_user_businesses(token)
selected = get_business(token, business_id)
```

Only active businesses reached through an active membership are listed.
`get_business` repeats authorization, so changing `business_id` in the UI does
not bypass isolation.

## Membership management

```python
from services.business_service import add_member, list_members, remove_member

add_member(token, business_id, "person@example.com", "member")
list_members(token, business_id)
remove_member(token, business_id, membership_id)
```

Owners can add managers, members, and viewers and remove non-owners. Managers
can add/remove ordinary members and viewers but cannot manage owners/managers.
Members and viewers cannot manage memberships. Module 2 does not implement
ownership transfer, so the owner cannot be removed.

## Access check for future modules

Future business-scoped backend operations must call:

```python
from services.business_service import require_business_access
access = require_business_access(token, business_id)
```

For privileged actions pass the allowed membership roles. Do not authorize
using a role or user ID supplied by the browser.

## Error codes

- `SESSION_INVALID`: missing, expired, revoked, or invalid session
- `INVALID_INPUT`: invalid business or membership input
- `BUSINESS_NOT_FOUND`: unknown business ID
- `FORBIDDEN`: no membership or insufficient membership role
- `BUSINESS_DISABLED`: business is disabled
- `MEMBERSHIP_DISABLED`: membership is disabled
- `DUPLICATE_MEMBERSHIP`: user already has a membership record
- `OWNER_REQUIRED`: operation would remove the protected owner
- `USER_NOT_FOUND`: target email is not a FinSight account
