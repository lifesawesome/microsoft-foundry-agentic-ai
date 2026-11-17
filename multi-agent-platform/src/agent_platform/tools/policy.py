"""Default tool policy.

Enforces the core rule: side-effecting tools require both an allow decision and a
delegated identity token scoped to the acting user. Read-only tools are permitted by
default. Deny-by-default applies to unknown tool kinds.
"""

from __future__ import annotations

from agent_platform.contracts.tools import ToolCall, ToolKind
from agent_platform.interfaces.identity import DelegatedToken
from agent_platform.interfaces.tools import PolicyDecision, ToolDefinition


class DefaultToolPolicy:
    """A conservative `ToolPolicy` suitable for the MVP."""

    def evaluate(
        self,
        definition: ToolDefinition,
        call: ToolCall,
        *,
        principal_id: str,
        delegated_token: DelegatedToken | None,
    ) -> PolicyDecision:
        if definition.kind is ToolKind.READ_ONLY:
            return PolicyDecision(allowed=True)

        if definition.kind is ToolKind.SIDE_EFFECTING:
            if delegated_token is None:
                return PolicyDecision(
                    allowed=False,
                    reason="Side-effecting tool requires a delegated user token.",
                )
            if delegated_token.principal_id != principal_id:
                return PolicyDecision(
                    allowed=False,
                    reason="Delegated token principal does not match the caller.",
                )
            return PolicyDecision(allowed=True)

        return PolicyDecision(allowed=False, reason="Unknown tool kind.")
