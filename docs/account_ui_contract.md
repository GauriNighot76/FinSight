# Module 3 financial-account UI contract

Financial accounts belong to Module 2 `businesses`, not legacy Module 0
`business_registry`. The backend always derives the user from the session and
checks the user's active business membership.

## Create an account

```python
from services.account_service import create_account

result = create_account(token, business_id, {
    "account_name": "HDFC Current Account",
    "account_type": "bank",
    "institution_name": "HDFC Bank",       # optional
    "account_identifier": "internal-ref",  # optional; never a PIN/password/CVV
    "currency": "INR",
    "opening_balance": "10500.75",
})
```

Only owners and managers can create accounts. The backend rejects frontend
identity, role, status, or business reassignment fields.

Supported account types: `bank`, `cash`, `credit_card`, `loan`, `other`.
Currency must be an uppercase three-letter code. Send balances as strings with
at most two decimal places. SQLite stores integer minor units, avoiding binary
floating-point errors.

## Read and list

```python
from services.account_service import get_account, list_business_accounts

one = get_account(token, account_id)
listed = list_business_accounts(token, business_id)
```

All active membership roles may read active accounts. Normal lists exclude
disabled accounts. Account identifiers are masked in responses.

## Update

```python
from services.account_service import update_account

result = update_account(token, account_id, {
    "account_name": "Updated name",
    "currency": "USD",
})
```

Updates are partial. Owners and managers may update editable account fields.
The UI cannot change `account_id`, `business_id`, `created_at`, status, actor
identity, or membership role through this operation.

## Disable

```python
from services.account_service import disable_account
result = disable_account(token, account_id)
```

Owners and managers may disable an account. Accounts are not hard-deleted.

## Reusable access check

Future transaction services should call:

```python
from services.account_service import require_account_access
access = require_account_access(token, account_id)
```

This performs session → account → business → membership authorization and
rejects disabled users, businesses, memberships, and accounts.

## Safe errors

- `SESSION_INVALID`
- `INVALID_INPUT`
- `BUSINESS_NOT_FOUND`
- `BUSINESS_DISABLED`
- `MEMBERSHIP_DISABLED`
- `ACCOUNT_NOT_FOUND`
- `ACCOUNT_DISABLED`
- `FORBIDDEN`
- `DUPLICATE_ACCOUNT`
- `ACCOUNT_CREATE_FAILED`
- `ACCOUNT_UPDATE_FAILED`
