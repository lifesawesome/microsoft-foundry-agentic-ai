"""Unit tests for the tool registry, policy, and delegated identity."""

from __future__ import annotations

import pytest

from agent_platform.contracts.errors import ErrorCode, PlatformException
from agent_platform.contracts.tools import ToolCall, ToolKind, ToolResult
from agent_platform.interfaces.tools import ToolDefinition
from agent_platform.tools.identity import SimulatedDelegatedIdentityProvider
from agent_platform.tools.policy import DefaultToolPolicy
from agent_platform.tools.registry import InMemoryToolProvider, RegisteredTool


def _provider() -> InMemoryToolProvider:
    policy = DefaultToolPolicy()
    return InMemoryToolProvider(
        lambda definition, call, principal, token: policy.evaluate(
            definition, call, principal_id=principal, delegated_token=token
        )
    )


async def _echo(call: ToolCall) -> ToolResult:
    return ToolResult(tool_name=call.tool_name, succeeded=True, output=call.arguments)


async def test_read_only_tool_runs_without_delegation() -> None:
    provider = _provider()
    provider.register(
        RegisteredTool(
            ToolDefinition(
                name="lookup", description="read", kind=ToolKind.READ_ONLY
            ),
            _echo,
        )
    )

    result = await provider.invoke(
        ToolCall(tool_name="lookup"), principal_id="user-1", delegated_token=None
    )
    assert result.succeeded


async def test_side_effecting_tool_requires_delegated_token() -> None:
    provider = _provider()
    provider.register(
        RegisteredTool(
            ToolDefinition(
                name="post", description="acts", kind=ToolKind.SIDE_EFFECTING
            ),
            _echo,
        )
    )

    with pytest.raises(PlatformException) as exc:
        await provider.invoke(
            ToolCall(tool_name="post"), principal_id="user-1", delegated_token=None
        )
    assert exc.value.error.code is ErrorCode.DELEGATION_REQUIRED


async def test_side_effecting_tool_runs_with_matching_delegated_token() -> None:
    identity = SimulatedDelegatedIdentityProvider(frozenset({"Mail.Send"}))
    token = await identity.acquire_token("user-1", ("Mail.Send",))
    provider = _provider()
    provider.register(
        RegisteredTool(
            ToolDefinition(
                name="post", description="acts", kind=ToolKind.SIDE_EFFECTING
            ),
            _echo,
        )
    )

    result = await provider.invoke(
        ToolCall(tool_name="post"), principal_id="user-1", delegated_token=token
    )
    assert result.succeeded


async def test_token_principal_mismatch_is_denied() -> None:
    identity = SimulatedDelegatedIdentityProvider(frozenset({"Mail.Send"}))
    token = await identity.acquire_token("attacker", ("Mail.Send",))
    provider = _provider()
    provider.register(
        RegisteredTool(
            ToolDefinition(
                name="post", description="acts", kind=ToolKind.SIDE_EFFECTING
            ),
            _echo,
        )
    )

    with pytest.raises(PlatformException) as exc:
        await provider.invoke(
            ToolCall(tool_name="post"), principal_id="user-1", delegated_token=token
        )
    assert exc.value.error.code is ErrorCode.TOOL_POLICY_DENIED


async def test_unknown_tool_raises_not_found() -> None:
    with pytest.raises(PlatformException) as exc:
        await _provider().invoke(
            ToolCall(tool_name="missing"), principal_id="user-1", delegated_token=None
        )
    assert exc.value.error.code is ErrorCode.NOT_FOUND


async def test_consent_is_required_before_token_issue() -> None:
    identity = SimulatedDelegatedIdentityProvider(frozenset())
    with pytest.raises(PermissionError):
        await identity.acquire_token("user-1", ("Mail.Send",))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
