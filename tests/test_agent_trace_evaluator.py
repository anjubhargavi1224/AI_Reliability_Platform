"""Comprehensive unit tests for AgentToolTraceEvaluator covering selection, arguments, order, failures, and abstentions."""

import pytest
from ai_reliability.evaluators.agent.tool_trace import (
    AgentRequirements,
    AgentToolTraceEvaluator,
    compare_json_values,
)
from ai_reliability.schemas.record import (
    EvaluationRecord,
    ToolCall,
    ToolTraceExpectations,
)


def test_compare_json_values():
    """Verify recursive deterministic equality across scalar, dict, list, and boolean separation."""
    assert compare_json_values("  query  ", "query") is True
    assert compare_json_values({"a": 1, "b": [2, 3]}, {"b": [2, 3], "a": 1}) is True
    assert compare_json_values({"a": 1}, {"a": 2}) is False
    assert compare_json_values([1, 2], [1, 2, 3]) is False
    assert compare_json_values("test", 123) is False
    # Strict boolean vs numeric isolation:
    assert compare_json_values(True, 1) is False
    assert compare_json_values(False, 0) is False
    assert compare_json_values("1", 1) is False
    assert compare_json_values(True, True) is True
    assert compare_json_values({"flag": True}, {"flag": 1}) is False
    assert compare_json_values({"flag": True}, {"flag": True}) is True


def test_agent_expected_tool_called():
    """Case 1: Expected tool called successfully."""
    evaluator = AgentToolTraceEvaluator()
    record = EvaluationRecord(
        application_type="agent",
        question="Find universities.",
        response="Found top universities.",
        tool_calls=[
            ToolCall(name="search", arguments={"query": "universities"}, order=1, status="success")
        ],
        tool_trace_expectations=ToolTraceExpectations(
            expected_tools=["search"],
            expected_arguments={"search": {"query": "universities"}},
        ),
    )
    result = evaluator.evaluate(record)
    assert result.status == "completed"
    assert result.score == 1.0
    assert result.measurements["expected_tools_called"] == 1
    assert result.measurements["missing_expected_tools"] == 0
    assert result.measurements["argument_matches"] == 1
    assert result.measurements["argument_mismatches"] == 0

    codes = [f.code for f in result.findings]
    assert "tool_expected_and_called" in codes
    assert "tool_argument_match" in codes


def test_agent_expected_tool_missing():
    """Case 2: Expected tool missing from trace."""
    evaluator = AgentToolTraceEvaluator()
    record = EvaluationRecord(
        application_type="agent",
        question="Find universities.",
        response="No tool was executed.",
        tool_calls=[],
        tool_trace_expectations=ToolTraceExpectations(
            expected_tools=["search"]
        ),
    )
    result = evaluator.evaluate(record)
    assert result.status == "completed"
    assert result.score == 0.0
    assert result.measurements["expected_tools_called"] == 0
    assert result.measurements["missing_expected_tools"] == 1

    codes = [f.code for f in result.findings]
    assert "tool_expected_but_missing" in codes


def test_agent_disallowed_and_unexpected_tools():
    """Case 3: Disallowed and unexpected tools called with allow_extra_tools=False."""
    evaluator = AgentToolTraceEvaluator()
    record = EvaluationRecord(
        application_type="agent",
        question="Check weather.",
        response="Checked weather and sent email.",
        tool_calls=[
            ToolCall(name="weather", arguments={"city": "London"}, order=1),
            ToolCall(name="send_email", arguments={"to": "user@example.com"}, order=2),
            ToolCall(name="random_tool", arguments={}, order=3),
        ],
        tool_trace_expectations=ToolTraceExpectations(
            expected_tools=["weather"],
            disallowed_tools=["send_email"],
            allow_extra_tools=False,
        ),
    )
    result = evaluator.evaluate(record)
    assert result.status == "completed"
    assert result.measurements["disallowed_tool_calls"] == 1
    assert result.measurements["unexpected_tools"] == 1

    codes = [f.code for f in result.findings]
    assert "unnecessary_tool_call" in codes
    assert "tool_unexpectedly_called" in codes


def test_agent_allowed_extra_tools():
    """Case 3b: Extra tools allowed by default (allow_extra_tools=True)."""
    evaluator = AgentToolTraceEvaluator()
    record = EvaluationRecord(
        application_type="agent",
        question="Check weather.",
        response="Checked weather and logged.",
        tool_calls=[
            ToolCall(name="weather", arguments={"city": "London"}, order=1),
            ToolCall(name="logger", arguments={"msg": "done"}, order=2),
        ],
        tool_trace_expectations=ToolTraceExpectations(
            expected_tools=["weather"],
            allow_extra_tools=True,
        ),
    )
    result = evaluator.evaluate(record)
    assert result.status == "completed"
    assert result.measurements["unexpected_tools"] == 0
    codes = [f.code for f in result.findings]
    assert "tool_unexpectedly_called" not in codes


def test_agent_argument_mismatch():
    """Case 4: Argument mismatch between expectation and observation."""
    evaluator = AgentToolTraceEvaluator()
    record = EvaluationRecord(
        application_type="agent",
        question="Query",
        response="Answer",
        tool_calls=[
            ToolCall(name="search", arguments={"query": "cybersecurity"}, order=1)
        ],
        tool_trace_expectations=ToolTraceExpectations(
            expected_tools=["search"],
            expected_arguments={"search": {"query": "artificial intelligence"}},
        ),
    )
    result = evaluator.evaluate(record)
    assert result.status == "completed"
    assert result.measurements["argument_matches"] == 0
    assert result.measurements["argument_mismatches"] == 1

    codes = [f.code for f in result.findings]
    assert "tool_argument_mismatch" in codes


def test_agent_nested_arguments_comparison():
    """Case 5: Nested dictionary and list argument comparison."""
    evaluator = AgentToolTraceEvaluator()
    record = EvaluationRecord(
        application_type="agent",
        question="Query",
        response="Answer",
        tool_calls=[
            ToolCall(
                name="complex_tool",
                arguments={"filters": {"tag": "ai", "limit": 10}, "ids": [1, 2, 3]},
                order=1,
            )
        ],
        tool_trace_expectations=ToolTraceExpectations(
            expected_tools=["complex_tool"],
            expected_arguments={
                "complex_tool": {"filters": {"tag": "ai", "limit": 10}, "ids": [1, 2, 3]}
            },
        ),
    )
    result = evaluator.evaluate(record)
    assert result.status == "completed"
    assert result.measurements["argument_matches"] == 1
    assert "tool_argument_match" in [f.code for f in result.findings]


def test_agent_tool_order_subsequence_matching():
    """Case 6: Tool ordering match vs mismatch with subsequence."""
    evaluator = AgentToolTraceEvaluator()

    # Match with interleaved calls: search -> logger -> calc
    record_interleaved = EvaluationRecord(
        application_type="agent",
        question="Query",
        response="Answer",
        tool_calls=[
            ToolCall(name="search", order=1),
            ToolCall(name="logger", order=2),
            ToolCall(name="calculator", order=3),
        ],
        tool_trace_expectations=ToolTraceExpectations(
            expected_tool_order=["search", "calculator"]
        ),
    )
    res_interleaved = evaluator.evaluate(record_interleaved)
    assert res_interleaved.status == "completed"
    assert res_interleaved.measurements["order_match"] == 1
    assert "tool_order_match" in [f.code for f in res_interleaved.findings]

    # Match with repeated tool before next: search -> search -> calc
    record_repeated = EvaluationRecord(
        application_type="agent",
        question="Query",
        response="Answer",
        tool_calls=[
            ToolCall(name="search", order=1),
            ToolCall(name="search", order=2),
            ToolCall(name="calculator", order=3),
        ],
        tool_trace_expectations=ToolTraceExpectations(
            expected_tool_order=["search", "calculator"]
        ),
    )
    res_repeated = evaluator.evaluate(record_repeated)
    assert res_repeated.status == "completed"
    assert res_repeated.measurements["order_match"] == 1

    # Mismatch: calc -> search
    record_mismatch = EvaluationRecord(
        application_type="agent",
        question="Query",
        response="Answer",
        tool_calls=[
            ToolCall(name="calculator", order=1),
            ToolCall(name="search", order=2),
        ],
        tool_trace_expectations=ToolTraceExpectations(
            expected_tool_order=["search", "calculator"]
        ),
    )
    res_mismatch = evaluator.evaluate(record_mismatch)
    assert res_mismatch.status == "completed"
    assert res_mismatch.measurements["order_match"] == 0
    assert "tool_order_mismatch" in [f.code for f in res_mismatch.findings]


def test_agent_failed_tool_call():
    """Case 7: Tool call reporting error status."""
    evaluator = AgentToolTraceEvaluator()
    record = EvaluationRecord(
        application_type="agent",
        question="Query",
        response="Answer",
        tool_calls=[
            ToolCall(name="api_fetch", order=1, status="error", error_message="HTTP 500")
        ],
        tool_trace_expectations=ToolTraceExpectations(
            expected_tools=["api_fetch"]
        ),
    )
    result = evaluator.evaluate(record)
    assert result.status == "completed"
    assert result.measurements["failed_tool_calls"] == 1
    assert "tool_call_failed" in [f.code for f in result.findings]


def test_agent_max_allowed_calls_limit():
    """Case 8: Maximum allowed calls limit exceeded."""
    evaluator = AgentToolTraceEvaluator()
    record = EvaluationRecord(
        application_type="agent",
        question="Query",
        response="Answer",
        tool_calls=[
            ToolCall(name="search", order=1),
            ToolCall(name="search", order=2),
            ToolCall(name="search", order=3),
        ],
        tool_trace_expectations=ToolTraceExpectations(
            expected_tools=["search"],
            max_allowed_calls=2,
        ),
    )
    result = evaluator.evaluate(record)
    assert result.status == "completed"
    assert "tool_call_limit_exceeded" in [f.code for f in result.findings]


def test_agent_final_answer_tool_reference():
    """Case 9: Final-answer reference match and mismatch."""
    evaluator = AgentToolTraceEvaluator()

    record_match = EvaluationRecord(
        application_type="agent",
        question="Query",
        response="According to the database_lookup tool, the record exists.",
        tool_calls=[ToolCall(name="database_lookup", order=1)],
        tool_trace_expectations=ToolTraceExpectations(
            expected_tools=["database_lookup"],
            expected_final_answer_tools=["database_lookup"],
        ),
    )
    res_match = evaluator.evaluate(record_match)
    assert "final_answer_tool_reference_match" in [f.code for f in res_match.findings]

    record_mismatch = EvaluationRecord(
        application_type="agent",
        question="Query",
        response="The record exists.",
        tool_calls=[ToolCall(name="database_lookup", order=1)],
        tool_trace_expectations=ToolTraceExpectations(
            expected_tools=["database_lookup"],
            expected_final_answer_tools=["database_lookup"],
        ),
    )
    res_mismatch = evaluator.evaluate(record_mismatch)
    assert "final_answer_tool_reference_mismatch" in [f.code for f in res_mismatch.findings]


def test_agent_missing_trace_or_expectations_abstains():
    """Case 10: Missing trace or expectations must abstain as not_assessed."""
    evaluator = AgentToolTraceEvaluator()

    # 1. Missing tool_calls
    rec1 = EvaluationRecord(
        application_type="agent",
        question="Query",
        response="Answer",
        tool_calls=None,
        tool_trace_expectations=ToolTraceExpectations(expected_tools=["search"]),
    )
    assert evaluator.evaluate(rec1).status == "not_assessed"

    # 2. Missing expectations
    rec2 = EvaluationRecord(
        application_type="agent",
        question="Query",
        response="Answer",
        tool_calls=[ToolCall(name="search")],
        tool_trace_expectations=None,
    )
    assert evaluator.evaluate(rec2).status == "not_assessed"

    # 3. Both missing
    rec3 = EvaluationRecord(
        application_type="agent",
        question="Query",
        response="Answer",
    )
    assert evaluator.evaluate(rec3).status == "not_assessed"


def test_agent_duplicate_expected_tools_deduplication():
    """Case 11: Duplicate expected tool entries do not inflate denominator."""
    evaluator = AgentToolTraceEvaluator()
    record = EvaluationRecord(
        application_type="agent",
        question="Query",
        response="Answer",
        tool_calls=[ToolCall(name="search")],
        tool_trace_expectations=ToolTraceExpectations(
            expected_tools=["search", "search"]
        ),
    )
    res = evaluator.evaluate(record)
    assert res.measurements["expected_tools_count"] == 1
    assert res.measurements["expected_tools_called"] == 1
    assert res.measurements["missing_expected_tools"] == 0
    assert res.score == 1.0


def test_agent_no_expected_tools_score_is_none():
    """Case 12: When no expected tools are configured, score is None (no synthetic 1.0)."""
    evaluator = AgentToolTraceEvaluator()
    record = EvaluationRecord(
        application_type="agent",
        question="Query",
        response="Answer",
        tool_calls=[ToolCall(name="search", arguments={"q": "1"})],
        tool_trace_expectations=ToolTraceExpectations(
            expected_arguments={"search": {"q": "1"}}
        ),
    )
    res = evaluator.evaluate(record)
    assert res.status == "completed"
    assert res.score is None
    assert res.measurements["expected_tools_count"] == 0
    assert res.measurements["argument_matches"] == 1


def test_agent_deterministic_reproducibility():
    """Case 13: Bitwise identical results upon repeated execution."""
    evaluator = AgentToolTraceEvaluator()
    record = EvaluationRecord(
        application_type="agent",
        question="Query",
        response="Answer",
        tool_calls=[
            ToolCall(name="search", arguments={"q": 1}, order=1, status="success"),
            ToolCall(name="calc", arguments={"v": 2}, order=2, status="error"),
        ],
        tool_trace_expectations=ToolTraceExpectations(
            expected_tools=["search", "calc"],
            expected_tool_order=["search", "calc"],
            expected_arguments={"search": {"q": 1}},
        ),
    )
    res1 = evaluator.evaluate(record)
    res2 = evaluator.evaluate(record)
    assert res1.model_dump(mode="json", exclude={"evaluation_latency_ms"}) == (
        res2.model_dump(mode="json", exclude={"evaluation_latency_ms"})
    )

