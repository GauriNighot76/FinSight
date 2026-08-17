# Authentication UI contract

The Streamlit UI imports Python services directly. It must not execute SQL or
hash passwords.

## Application startup

Call `database.db.initialize_database()` once before rendering authentication
pages.

## Signup

```python
from services.auth_service import signup
result = signup(username, email, contact_number, password)
```

Success returns `success`, safe `user`, and `message`. Failure returns
`success=False`, `error`, and `message`. The frontend cannot choose the role;
the backend assigns `standard_business`.

## Login

```python
from services.auth_service import login
result = login(email, password)
```

On success, store `result["session"]["token"]` only in `st.session_state` and
use `expires_at` for display/refresh logic. Never store the password. Do not
write the token into URLs or logs.

## Protect a page

```python
from services.auth_service import validate_session
auth = validate_session(st.session_state.get("auth_token", ""))
if not auth["success"]:
    # show login page and stop rendering protected data
    ...
```

For role-protected actions call `require_role(token, {"administrator"})` (or
the required set) immediately before the backend action. UI button visibility
is not authorization.

## Logout

Call `logout(token)`, then remove `auth_token` and cached user data from
`st.session_state`. The same token will subsequently fail validation.

## Google button

The frontend completes Google's supported sign-in flow and receives a Google
ID token. Send that token directly to:

```python
from services.auth_service import google_sign_in
result = google_sign_in(google_id_token)
```

Do not send an unverified profile dictionary as identity. The production
service verifies the ID token using `GOOGLE_CLIENT_ID` and maps its stable
Google `sub` to one local FinSight user.

Live Google sign-in requires Google console configuration and cannot be proven
by the mocked automated test alone.
