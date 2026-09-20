"""Deterministic citation structure and local source-resolution checks."""

from urllib.parse import urlsplit

from ai_reliability.schemas.record import EvaluationRecord
from ai_reliability.schemas.result import EvaluatorResult, Finding


class CitationStructureEvaluator:
    evaluator_id = "citation_structure"
    evaluator_version = "1.0.0"
    dimension = "citation"
    method = "deterministic_structure_and_source_resolution"

    def __init__(self, *, require_citations: bool = False) -> None:
        self.require_citations = require_citations

    @staticmethod
    def _valid_http_url(value: str) -> bool:
        if any(character.isspace() for character in value):
            return False

        try:
            parsed = urlsplit(value)
            # Accessing port also validates malformed port values.
            port = parsed.port
            return (
                parsed.scheme.lower() in {"http", "https"}
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
                and (port is None or 1 <= port <= 65535)
            )
        except ValueError:
            return False

    def evaluate(self, record: EvaluationRecord) -> EvaluatorResult:
        findings = []
        sources = {source.id: source for source in record.context}

        if not record.citations:
            if self.require_citations:
                findings.append(
                    Finding(
                        code="missing_citations",
                        severity="medium",
                        message=(
                            "This evaluation requires citations, "
                            "but the record contains none."
                        ),
                    )
                )

            return self._result(
                status=(
                    "completed"
                    if self.require_citations
                    else "not_assessed"
                ),
                explanation=(
                    "Required citations are missing."
                    if self.require_citations
                    else "No structured citations were supplied; "
                    "citations are optional for this evaluation."
                ),
                findings=findings,
            )

        for citation in record.citations:
            prefix = f"Citation {citation.id!r}:"

            if citation.source_id is not None:
                if citation.source_id not in sources:
                    findings.append(
                        Finding(
                            code="unresolved_source",
                            severity="medium",
                            message=(
                                f"{prefix} source ID "
                                f"{citation.source_id!r} is absent "
                                "from the supplied context."
                            ),
                            response_excerpt=citation.raw_text,
                            source_ids=[citation.source_id],
                        )
                    )

            if citation.url is not None:
                if not self._valid_http_url(citation.url):
                    findings.append(
                        Finding(
                            code="invalid_citation_url",
                            severity="medium",
                            message=(
                                f"{prefix} URL failed the basic "
                                "HTTP/HTTPS structure check."
                            ),
                            response_excerpt=citation.raw_text,
                        )
                    )
                elif citation.source_id not in sources:
                    findings.append(
                        Finding(
                            code="external_support_unverified",
                            severity="info",
                            message=(
                                f"{prefix} URL was not fetched and "
                                "no source text was resolved."
                            ),
                            response_excerpt=citation.raw_text,
                        )
                    )

            if citation.source_id is None and citation.url is None:
                findings.append(
                    Finding(
                        code="missing_citation_target",
                        severity="medium",
                        message=(
                            f"{prefix} has neither a source ID nor a URL."
                        ),
                        response_excerpt=citation.raw_text,
                    )
                )

        return self._result(
            status="completed",
            explanation=(
                f"Checked {len(record.citations)} structured citation(s). "
                "Claim support and source authenticity were not assessed."
            ),
            findings=findings,
        )

    def _result(self, *, status, explanation, findings):
        return EvaluatorResult(
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            dimension=self.dimension,
            method=self.method,
            status=status,
            explanation=explanation,
            findings=findings,
            configuration = {"require_citations": self.require_citations},
            limitations=[
                "Only citations explicitly supplied in the record are checked.",
                "URLs are checked for basic structure, not fetched.",
                "Resolved source IDs do not establish claim support.",
                "Source authenticity and citation coverage are not assessed.",
            ],
        )