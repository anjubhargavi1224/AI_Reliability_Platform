"""Deterministic agent tool-trace evaluation over structured tool calls and explicit expectations."""

from typing import Any
from pydantic import Field

from ai_reliability.schemas.record import EvaluationRecord, SchemaModel
from ai_reliability.schemas.result import EvaluatorResult, Finding


class AgentRequirements(SchemaModel):
    strict_argument_matching: bool = True


def compare_json_values(actual: Any, expected: Any) -> bool:
    """Recursively compare two JSON-compatible values deterministically.
    
    Ensures boolean and numeric types are not conflated (e.g. True is not treated as 1).
    """
    if isinstance(actual, bool) or isinstance(expected, bool):
        if not (isinstance(actual, bool) and isinstance(expected, bool)):
            return False
        return actual is expected
    if isinstance(actual, dict) and isinstance(expected, dict):
        if set(actual.keys()) != set(expected.keys()):
            return False
        return all(compare_json_values(actual[k], expected[k]) for k in expected)
    elif isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            return False
        return all(compare_json_values(a, e) for a, e in zip(actual, expected))
    elif isinstance(actual, str) and isinstance(expected, str):
        return actual.strip() == expected.strip()
    return actual == expected


def is_subsequence(expected_subsequence: list[str], observed_sequence: list[str]) -> bool:
    """Check if expected_subsequence appears in order within observed_sequence."""
    if not expected_subsequence:
        return True
    it = iter(observed_sequence)
    return all(any(target == item for item in it) for target in expected_subsequence)


class AgentToolTraceEvaluator:
    evaluator_id = "agent_tool_trace"
    evaluator_version = "1.0.0"
    dimension = "agent"
    method = "deterministic_tool_trace_metrics"

    def __init__(self, requirements: AgentRequirements | None = None) -> None:
        self.requirements = (
            AgentRequirements.model_validate(requirements.model_dump())
            if requirements is not None
            else AgentRequirements()
        )

    def evaluate(self, record: EvaluationRecord) -> EvaluatorResult:
        if record.tool_calls is None:
            return EvaluatorResult(
                evaluator_id=self.evaluator_id,
                evaluator_version=self.evaluator_version,
                dimension=self.dimension,
                method=self.method,
                configuration=self.requirements.model_dump(mode="json"),
                status="not_assessed",
                score=None,
                explanation="No tool_calls trace supplied for agent evaluation.",
                findings=[],
                limitations=self._limitations(),
            )

        if record.tool_trace_expectations is None:
            return EvaluatorResult(
                evaluator_id=self.evaluator_id,
                evaluator_version=self.evaluator_version,
                dimension=self.dimension,
                method=self.method,
                configuration=self.requirements.model_dump(mode="json"),
                status="not_assessed",
                score=None,
                explanation="No tool_trace_expectations supplied for agent evaluation.",
                findings=[],
                limitations=self._limitations(),
            )

        tool_calls = record.tool_calls
        exp = record.tool_trace_expectations

        observed_tool_names = [call.name.strip() for call in tool_calls]
        observed_tool_set = set(observed_tool_names)

        findings: list[Finding] = []

        # 1. Tool Selection Checks
        # Deduplicate expected tool names preserving order
        unique_expected_tools = list(dict.fromkeys(t.strip() for t in exp.expected_tools if t.strip()))
        expected_tools_called = 0
        missing_expected_tools = 0

        for name in unique_expected_tools:
            if name in observed_tool_set:
                expected_tools_called += 1
                findings.append(
                    Finding(
                        code="tool_expected_and_called",
                        severity="info",
                        message=f"Expected tool '{name}' was called in execution trace.",
                        source_ids=[name],
                    )
                )
            else:
                missing_expected_tools += 1
                findings.append(
                    Finding(
                        code="tool_expected_but_missing",
                        severity="medium",
                        message=f"Expected tool '{name}' was not called in execution trace.",
                        source_ids=[name],
                    )
                )

        # Disallowed and Unexpected Tools
        disallowed_set = {d.strip() for d in exp.disallowed_tools if d.strip()}
        expected_set = set(unique_expected_tools)
        disallowed_calls = 0
        unexpected_tools = 0

        for name in observed_tool_names:
            if name in disallowed_set:
                disallowed_calls += 1
                findings.append(
                    Finding(
                        code="unnecessary_tool_call",
                        severity="medium",
                        message=f"Disallowed tool '{name}' was called in execution trace.",
                        source_ids=[name],
                    )
                )
            elif not exp.allow_extra_tools and name not in expected_set:
                unexpected_tools += 1
                findings.append(
                    Finding(
                        code="tool_unexpectedly_called",
                        severity="low",
                        message=f"Tool '{name}' was called but was not in the expected tool list and extra tools are disallowed.",
                        source_ids=[name],
                    )
                )

        # 2. Tool Arguments Correctness
        argument_matches = 0
        argument_mismatches = 0
        total_arg_checks = len(exp.expected_arguments)

        for tool_name, expected_args in exp.expected_arguments.items():
            matching_calls = [c for c in tool_calls if c.name.strip() == tool_name.strip()]
            if not matching_calls:
                argument_mismatches += 1
                findings.append(
                    Finding(
                        code="tool_argument_mismatch",
                        severity="medium",
                        message=f"Expected arguments for tool '{tool_name}' could not be verified because the tool was not called.",
                        source_ids=[tool_name],
                    )
                )
            else:
                matched = any(
                    compare_json_values(call.arguments, expected_args)
                    for call in matching_calls
                )
                if matched:
                    argument_matches += 1
                    findings.append(
                        Finding(
                            code="tool_argument_match",
                            severity="info",
                            message=f"Arguments for tool '{tool_name}' matched expected arguments.",
                            source_ids=[tool_name],
                        )
                    )
                else:
                    argument_mismatches += 1
                    findings.append(
                        Finding(
                            code="tool_argument_mismatch",
                            severity="medium",
                            message=f"Arguments for tool '{tool_name}' did not match expected arguments.",
                            source_ids=[tool_name],
                        )
                    )

        # 3. Tool Ordering Checks
        order_match: int | None = None
        if exp.expected_tool_order:
            clean_expected_order = [t.strip() for t in exp.expected_tool_order if t.strip()]
            if is_subsequence(clean_expected_order, observed_tool_names):
                order_match = 1
                findings.append(
                    Finding(
                        code="tool_order_match",
                        severity="info",
                        message=f"Tool call sequence matched expected order: {' -> '.join(clean_expected_order)}.",
                    )
                )
            else:
                order_match = 0
                findings.append(
                    Finding(
                        code="tool_order_mismatch",
                        severity="medium",
                        message=f"Tool call sequence did not match expected order. Expected: {' -> '.join(clean_expected_order)}, Observed: {' -> '.join(observed_tool_names)}.",
                    )
                )

        # 4. Failed Tool Calls Checks
        failed_calls = 0
        for idx, call in enumerate(tool_calls, start=1):
            if call.status == "error":
                failed_calls += 1
                order_str = f"order {call.order}" if call.order is not None else f"call #{idx}"
                err_info = f": {call.error_message}" if call.error_message else ""
                findings.append(
                    Finding(
                        code="tool_call_failed",
                        severity="medium",
                        message=f"Tool call '{call.name}' ({order_str}) reported status 'error'{err_info}.",
                        source_ids=[call.name],
                    )
                )

        # 5. Maximum Allowed Calls Checks
        if exp.max_allowed_calls is not None and len(tool_calls) > exp.max_allowed_calls:
            findings.append(
                Finding(
                    code="tool_call_limit_exceeded",
                    severity="medium",
                    message=f"Total tool calls ({len(tool_calls)}) exceeded maximum allowed limit ({exp.max_allowed_calls}).",
                )
            )

        # 6. Final-Answer / Tool Reference Consistency
        if exp.expected_final_answer_tools:
            response_lower = record.response.lower()
            for ref_tool in exp.expected_final_answer_tools:
                clean_ref = ref_tool.strip().lower()
                if clean_ref in response_lower:
                    findings.append(
                        Finding(
                            code="final_answer_tool_reference_match",
                            severity="info",
                            message=f"Final answer contains reference to expected tool '{ref_tool}'.",
                            source_ids=[ref_tool],
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            code="final_answer_tool_reference_mismatch",
                            severity="medium",
                            message=f"Final answer does not reference expected tool '{ref_tool}'.",
                            source_ids=[ref_tool],
                        )
                    )

        # Measurements
        selection_rate = (
            round(expected_tools_called / len(unique_expected_tools), 4)
            if unique_expected_tools
            else None
        )
        arg_match_rate = (
            round(argument_matches / total_arg_checks, 4)
            if total_arg_checks > 0
            else None
        )

        measurements: dict[str, Any] = {
            "expected_tools_count": len(unique_expected_tools),
            "observed_tools_count": len(tool_calls),
            "expected_tools_called": expected_tools_called,
            "missing_expected_tools": missing_expected_tools,
            "unexpected_tools": unexpected_tools,
            "argument_matches": argument_matches,
            "argument_mismatches": argument_mismatches,
            "order_match": order_match,
            "failed_tool_calls": failed_calls,
            "disallowed_tool_calls": disallowed_calls,
            "tool_selection_rate": selection_rate,
            "argument_match_rate": arg_match_rate,
        }

        # Score reflects selection rate when expected tools configured; does not synthesize an aggregate score
        score: float | None = selection_rate

        explanation = (
            f"Evaluated {len(tool_calls)} observed tool calls against expectations. "
            f"Expected tools called: {expected_tools_called}/{len(unique_expected_tools)}, "
            f"Argument matches: {argument_matches}/{total_arg_checks}, "
            f"Failed calls: {failed_calls}, Disallowed calls: {disallowed_calls}."
        )

        return EvaluatorResult(
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            dimension=self.dimension,
            method=self.method,
            configuration=self.requirements.model_dump(mode="json"),
            status="completed",
            score=score,
            explanation=explanation,
            measurements=measurements,
            findings=findings,
            limitations=self._limitations(),
        )

    def _limitations(self) -> list[str]:
        return [
            "Evaluates observable tool execution traces against explicit deterministic expectations only.",
            "Does not infer agent reasoning quality, intelligence, planning optimality, or semantic truth.",
            "Does not evaluate tool outputs unless explicit expected arguments or final-answer references are configured.",
            "Final-answer tool reference check verifies only explicit string/identifier presence of configured expected tool names in the response text; it does NOT infer semantic reasoning, semantic truth, or whether tool output was factually utilized.",
            "Requires explicit tool_calls and tool_trace_expectations; abstains as not_assessed when absent.",
        ]
