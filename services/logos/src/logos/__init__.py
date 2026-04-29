"""LogicBrain - Deterministic Logic Verifier.

A Z3-backed verifier for propositional and predicate logic.
Can be used directly by AI agents via Python execution.

Quick usage:
    >>> from logos import verify
    >>> result = verify("P -> Q, P |- Q")
    >>> result.valid
    True
    >>> result.rule
    'Modus Ponens'
"""

from .models import Proposition, LogicalExpression, Connective, Argument, VerificationResult
from .verifier import PropositionalVerifier
from .predicate_models import (
    Variable,
    Constant,
    Predicate,
    PredicateConnective,
    PredicateExpression,
    QuantifiedExpression,
    Quantifier,
    FOLArgument,
)
from .predicate import PredicateVerifier
from .exceptions import (
    CertificateError,
    ConstraintError,
    LogicBrainError,
    PolicyViolationError,
    SessionError,
    VerificationError,
)
from .parser import (
    verify,
    parse_argument,
    parse_expression,
    is_tautology,
    is_contradiction,
    are_equivalent,
    ParseError,
)
from .explain import TruthTable, TruthTableRow, render_truth_table, truth_table
from .lean_session import LeanSession, TacticResult, is_lean_available
from .z3_session import Z3Session, CheckResult
from .diagnostics import (
    Diagnostic,
    ErrorType,
    LeanDiagnosticParser,
    Z3DiagnosticParser,
)
from .generator import ProblemGenerator, GeneratorConfig
from .certificate import ProofCertificate, certify, certify_z3_session, verify_certificate
from .certificate_store import (
    CertificateStore,
    CompactionResult,
    ConsistencyFilterResult,
    RankedCertificate,
    RelevanceResult,
    StoredCertificate,
    StoreStats,
)
from .assumptions import (
    AssumptionConsistency,
    AssumptionEntry,
    AssumptionKind,
    AssumptionSet,
    AssumptionStatus,
)
from .counterfactual import (
    CounterfactualPlanner,
    PlanBranch,
    PlanResult,
    PlanState,
    RankedBranch,
    SafetyBound,
    UtilityModel,
    VariableDecl,
)
from .action_policy import (
    ActionPolicyEngine,
    ActionPolicyResult,
    ActionPolicyRule,
    PolicyDecision,
    PolicyViolationEvidence,
)
from .uncertainty import (
    ConfidenceLevel,
    ConfidenceRecord,
    EscalationDecision,
    EscalationResult,
    RiskLevel,
    UncertaintyCalibrator,
    UncertaintyPolicy,
    certificate_reference,
    resolve_certificate_reference,
)
from .proof_exchange import (
    ProofBundle,
    ProofExchangeNode,
    ProofExchangeResult,
    create_proof_bundle,
    verify_proof_bundle,
)
from .belief_graph import (
    BeliefEdge,
    BeliefEdgeType,
    BeliefGraph,
    BeliefNode,
    ContradictionExplanation,
)
from .goal_contract import (
    GoalContract,
    GoalContractDiagnostic,
    GoalContractResult,
    GoalContractStatus,
    build_branch_context,
    evaluate_goal_contract,
    verify_contract_preconditions_z3,
)
from .execution_bus import ActionBusResult, ActionEnvelope, PostconditionCheck, execute_action_envelope
from .orchestrator import Claim, ClaimStatus, OrchestrationStatus, ProofOrchestrator
from .recovery import (
    FailureCategory,
    FailureContext,
    RecoveryCertificate,
    RecoveryDecision,
    RecoveryProtocol,
    choose_recovery,
    classify_action_bus_failure,
    classify_claim_failure,
    classify_goal_contract_failure,
    classify_plan_failure,
    failure_context_from_dict,
    verify_recovery_certificate,
)
from .trust_ledger import FederatedProofLedger, LedgerQueryResult, LedgerRecord, TrustPolicy
from .verified_runtime import (
    RuntimeEvent,
    RuntimeOutcome,
    RuntimePhase,
    RuntimeRequest,
    RuntimeTrace,
    VerifiedAgentRuntime,
)
from .adversarial_harness import (
    AdversarialSelfPlayHarness,
    AttackTemplate,
    DefensiveScore,
    SelfPlayEpisode,
    SelfPlayReport,
)

__all__ = [
    # Exception hierarchy (Tier 2 / Provisional)
    "LogicBrainError",
    "VerificationError",
    "ConstraintError",
    "SessionError",
    "CertificateError",
    "PolicyViolationError",
    # Quick API (string-based)
    "verify",
    "parse_argument",
    "parse_expression",
    "is_tautology",
    "is_contradiction",
    "are_equivalent",
    "ParseError",
    "truth_table",
    "render_truth_table",
    "TruthTable",
    "TruthTableRow",
    # Core classes
    "Proposition",
    "LogicalExpression",
    "Connective",
    "Argument",
    "VerificationResult",
    "PropositionalVerifier",
    # FOL classes
    "Variable",
    "Constant",
    "Predicate",
    "PredicateConnective",
    "PredicateExpression",
    "QuantifiedExpression",
    "Quantifier",
    "FOLArgument",
    "PredicateVerifier",
    # Z3 interactive session (Tier 1 / Stable)
    "Z3Session",
    "CheckResult",
    # Diagnostics (Tier 1 / Stable)
    "Diagnostic",
    "ErrorType",
    # Proof certificates (Tier 1 / Stable)
    "ProofCertificate",
    "certify",
    "certify_z3_session",
    "verify_certificate",
    # Lean 4 interactive session (Tier 2 / Provisional)
    "LeanSession",
    "TacticResult",
    "is_lean_available",
    # Diagnostics — parsers (Tier 2 / Provisional)
    "LeanDiagnosticParser",
    "Z3DiagnosticParser",
    # Problem generation (Tier 2 / Provisional)
    "ProblemGenerator",
    "GeneratorConfig",
    "CertificateStore",
    "CompactionResult",
    "ConsistencyFilterResult",
    "RankedCertificate",
    "RelevanceResult",
    "StoredCertificate",
    "StoreStats",
    # Assumption state kernel (Tier 2 / Provisional)
    "AssumptionKind",
    "AssumptionStatus",
    "AssumptionEntry",
    "AssumptionConsistency",
    "AssumptionSet",
    # Counterfactual planning (Tier 2 / Provisional)
    "VariableDecl",
    "PlanState",
    "PlanBranch",
    "PlanResult",
    "CounterfactualPlanner",
    "UtilityModel",
    "SafetyBound",
    "RankedBranch",
    # Action policy enforcement (Tier 2 / Provisional)
    "PolicyDecision",
    "ActionPolicyRule",
    "PolicyViolationEvidence",
    "ActionPolicyResult",
    "ActionPolicyEngine",
    # Uncertainty calibration (Tier 2 / Provisional)
    "ConfidenceLevel",
    "RiskLevel",
    "EscalationDecision",
    "ConfidenceRecord",
    "EscalationResult",
    "UncertaintyPolicy",
    "UncertaintyCalibrator",
    "certificate_reference",
    "resolve_certificate_reference",
    # Proof exchange protocol (Tier 2 / Provisional)
    "ProofExchangeNode",
    "ProofBundle",
    "ProofExchangeResult",
    "create_proof_bundle",
    "verify_proof_bundle",
    # Causal belief graph (Tier 2 / Provisional)
    "BeliefEdgeType",
    "BeliefNode",
    "BeliefEdge",
    "ContradictionExplanation",
    "BeliefGraph",
    # Goal contracts (Tier 2 / Provisional)
    "GoalContractStatus",
    "GoalContractDiagnostic",
    "GoalContract",
    "GoalContractResult",
    "build_branch_context",
    "evaluate_goal_contract",
    "verify_contract_preconditions_z3",
    # Proof-carrying execution bus (Tier 2 / Provisional)
    "ActionEnvelope",
    "PostconditionCheck",
    "ActionBusResult",
    "execute_action_envelope",
    # Proof orchestration (Tier 2 / Provisional)
    "ClaimStatus",
    "Claim",
    "OrchestrationStatus",
    "ProofOrchestrator",
    # Recovery protocols (Tier 2 / Provisional)
    "FailureCategory",
    "RecoveryProtocol",
    "FailureContext",
    "RecoveryCertificate",
    "RecoveryDecision",
    "failure_context_from_dict",
    "choose_recovery",
    "verify_recovery_certificate",
    "classify_action_bus_failure",
    "classify_claim_failure",
    "classify_plan_failure",
    "classify_goal_contract_failure",
    # Federated trust ledger (Tier 2 / Provisional)
    "TrustPolicy",
    "LedgerRecord",
    "LedgerQueryResult",
    "FederatedProofLedger",
    # Verified runtime loop (Tier 2 / Provisional)
    "RuntimePhase",
    "RuntimeEvent",
    "RuntimeTrace",
    "RuntimeRequest",
    "RuntimeOutcome",
    "VerifiedAgentRuntime",
    # Adversarial harness (Tier 2 / Provisional)
    "AttackTemplate",
    "DefensiveScore",
    "SelfPlayEpisode",
    "SelfPlayReport",
    "AdversarialSelfPlayHarness",
]
