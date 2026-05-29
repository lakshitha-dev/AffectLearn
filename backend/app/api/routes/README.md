# API Routes

REST and WebSocket endpoints exposed by the AffectLearn backend. All routes are
mounted under the `/api/v1` prefix in `app.main`.

## WebSocket: `/api/v1/ws`

Single persistent connection per learner — the transport substrate for the affect
detection loop (Epic 4) and adaptation delivery (Epic 5). Multiplexed by `type`
discriminator.

### Handshake

```
ws://<host>/api/v1/ws?token=<access_jwt>
```

- The JWT is sent as a query parameter and is validated once on `accept`.
- Only users with role `learner` may connect; designers and admins are rejected.

### Message protocol

Every message — both directions — is JSON of the form:

```json
{
  "type": "<snake_case_discriminator>",
  "ts": 1735776123456,
  "data": { ... }
}
```

WebSocket fields are **snake_case in both directions** — a deliberate exception to
the REST API's camelCase-on-the-wire rule (see `architecture.md` line 489).

For `type: "system"` messages, an `action` sub-discriminator selects the variant:

| `type`     | `action`           | Direction       | Notes                                          |
| ---------- | ------------------ | --------------- | ---------------------------------------------- |
| `system`   | `connected`        | server → client | First message on a fresh session               |
| `system`   | `session_restored` | server → client | Sent when prior session state exists in cache  |
| `system`   | `error`            | server → client | Soft errors — connection stays open            |
| `heartbeat`        | —          | client → server | Sent every 25s; carries `data.seq`             |
| `heartbeat_ack`    | —          | server → client | Echoes `seq`; adds `server_ts`                 |

### Close codes

Custom codes use the RFC 6455 application-defined range (4000–4999):

| Code  | Reason values                                                                    | Auto-reconnect? |
| ----- | -------------------------------------------------------------------------------- | --------------- |
| 4001  | `superseded_by_new_connection`                                                   | No              |
| 4401  | `missing_token`, `invalid_token`, `expired_token`, `role_not_authorized`         | No              |

Other close codes (1006 network blip, 1011 server error) are treated as transient
and the client transparently reconnects with exponential backoff (1s → 30s).

### Single-connection invariant

Opening a second connection for the same learner closes the first with code 4001.
This prevents duplicate research events and ensures the agent loop has exactly one
authoritative client per session.

## Adding a new route

1. Create the module under `app/api/routes/`.
2. Define schemas in `app/schemas/` using `CamelModel` for REST or `BaseModel` for
   WS payloads (snake_case-on-the-wire).
3. Register the router in `app/api/routes/__init__.py`.
4. Add tests under `backend/tests/api/`.
