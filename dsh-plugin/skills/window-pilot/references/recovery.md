# Stop, uncertain input and recovery

Unknown or partial input means STOP. Never replay, auto-rebind, reconnect or restart to bypass a fault. A disconnect grants no retry. Fresh screenshots or returned state do not themselves establish the requested effect. Review what actually happened against the human's task before deciding a new action.

## Windows uncertain-input faults

1. Inspect the error's `recovery_diagnostic` and `window_control(operation="status")`. `attempt_input=not_sent` describes this attempt only; it cannot clear an older unknown fault. Unknown/unreviewed faults survive ownership release, lease expiry and reconnects.
2. With the existing write binding, call `window_control(operation="prepare_recovery", target_id=...)`. It obtains ownership and collects a fresh client frame by default; `evidence_kind="controls"` requires a successful nonempty UIA tree. A supplied fresh frame/observation ID may reuse valid evidence. Preparation never sends input or clears a fault.
3. Inspect the returned evidence. `not_required` needs no recovery but preparation may still own a lease. Failed/empty observations supply no valid recovery plan. If the effect cannot be assessed, keep input stopped and report the uncertainty.
4. After assessment, submit the exact returned `next_call_after_review` recover arguments with purpose and `confirmation="reviewed_effect_no_replay"`. This is an explicit host review under the original task, not an automatic resubmission and not a new access grant. There is no mandatory human prompt for every recover; ask only when the task needs a human decision.
5. Recover requires current owner/epoch and successful evidence from this exact connection/target within 30 seconds. Screenshot dimensions or UIA geometry/identity must still match. Recover consumes/invalidates the review evidence: observe AGAIN before choosing ONE new action. Never repeat the uncertain action merely because recovery succeeded.

Direct recover remains available when these evidence requirements are already met. Read-only bindings cannot clear faults or gain write access. Failed UIA reads do not confirm prior input effects.

## Executor-wide stop

`input_control(operation="stop")` is idempotent, invalidates observations and cooperatively cancels input. Already dispatched effects cannot be undone. Read-only Windows observation and cleanup remain available. Stop also terminates owned browser sessions, including idle ones.

Resume only after a NEW explicit human request, using the current stop_id, purpose and `confirmation="user_requested_resume"`. Confirmation/purpose are caller statements, not authorization proof. Resume waits for pending input/cleanup as required, retains uncertain-input faults and invalidates observations again. It never restarts old browser sessions, replays actions or clears origin faults. Physical Esc and other executors are outside this tool.

Browser unknown outcomes lock the exact origin and have NO recovery endpoint. Do not apply Windows recover, start another same-origin session, reconnect or resume to bypass that fault. Human review of page/server effects does not by itself clear the origin lock. Unknown launches also cannot be retried with a new request_id.
