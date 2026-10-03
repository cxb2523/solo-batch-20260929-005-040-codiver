"""
Static Analyzer Engine
Core logic for AST parsing and metric calculation
"""

import javalang
from typing import List, Dict, Any, Optional, Tuple
from detectors.base import CodeSmell, SEVERITY_WEIGHTS
from detectors.design import DesignSmells
from detectors.implementation import ImplementationSmells
from detectors.naming_docs import NamingSmells, DocumentationSmells
from utils.helpers import count_blank_lines, count_comment_lines


# ---------------------------------------------------------------------------
# Detector registry
# ---------------------------------------------------------------------------
# Registration order is fixed and meaningful:
#   design -> implementation -> naming -> documentation
# i.e. architectural smells first, then implementation, then cosmetic rules.
# The order decides (a) the row order on the pipeline page and (b) which
# issue survives when two detectors emit the same rule key with the same
# severity (the earlier registration wins the tie).
DETECTOR_REGISTRY: Dict[str, type] = {}
REGISTRY_WARNINGS: List[str] = []


def register_detector(detector_cls: type) -> type:
    """
    Register a detector class under its ``detector_id``.

    Rule-id collisions are first-wins: if the id is already taken (by
    another detector or by a subclass trying to override it), the existing
    registration stays in effect and a warning is recorded. This keeps the
    pipeline deterministic regardless of import order.
    """
    detector_id = getattr(detector_cls, "detector_id", detector_cls.__name__)
    if detector_id in DETECTOR_REGISTRY:
        REGISTRY_WARNINGS.append(
            f"Duplicate detector id '{detector_id}' from "
            f"{detector_cls.__name__} ignored; "
            f"{DETECTOR_REGISTRY[detector_id].__name__} stays in effect."
        )
        return detector_cls
    DETECTOR_REGISTRY[detector_id] = detector_cls
    return detector_cls


register_detector(DesignSmells)
register_detector(ImplementationSmells)
register_detector(NamingSmells)
register_detector(DocumentationSmells)

# Penalty applied per weighted hit when normalizing a detector score.
ISSUE_PENALTY = 5


def deduplicate_issues(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate issues coming from multiple detectors.

    Two issues collide when they share the same rule key ``(Type, Target)``.
    The issue with the higher severity weight survives; on a tie the issue
    emitted by the earlier-registered detector wins (stable input order).
    """
    merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for issue in issues:
        key = (issue["Type"], issue["Target"])
        existing = merged.get(key)
        if existing is None:
            merged[key] = issue
        elif SEVERITY_WEIGHTS[issue["Severity"]] > SEVERITY_WEIGHTS[existing["Severity"]]:
            merged[key] = issue
    return list(merged.values())


def normalize_score(weighted_hits: int) -> int:
    """
    Normalize weighted hits into a 0-100 score.

    Formula: ``clamp(100 - ISSUE_PENALTY * weighted_hits, 0, 100)``.
    """
    return max(0, min(100, 100 - ISSUE_PENALTY * weighted_hits))


class StaticAnalyzerEngine:
    """
    Main analyzer engine that orchestrates all code smell detectors
    and calculates comprehensive code metrics.
    """
    
    def __init__(self, code: str, config: Dict[str, bool] = None):
        """
        Initialize the analyzer engine.
        
        Args:
            code: Java source code as a string
            config: Dictionary specifying which detectors to enable
        """
        self.code = code
        self.lines = code.split('\n')
        self.config = config or {
            'design': True,
            'implementation': True,
            'naming': True,
            'documentation': True
        }
        self.detectors: List[CodeSmell] = self._initialize_detectors()
        # Populated by run(); drives the pipeline page in the dashboard.
        self.pipeline_report: Dict[str, Any] = self._empty_report()
    
    def _initialize_detectors(self) -> List[CodeSmell]:
        """
        Instantiate enabled detectors in registry order.
        
        Returns:
            List of code smell detector instances
        """
        return [
            detector_cls()
            for detector_id, detector_cls in DETECTOR_REGISTRY.items()
            if self.config.get(detector_id, True)
        ]

    def _empty_report(self) -> Dict[str, Any]:
        """Build the degraded (no-data) pipeline report."""
        return {
            "detectors": [
                {
                    "order": order,
                    "id": detector_id,
                    "class": detector_cls.__name__,
                    "status": "disabled" if not self.config.get(detector_id, True) else "pending",
                    "raw_hits": 0,
                    "hits": 0,
                    "weighted_hits": 0,
                    "score": None,
                    "error": None,
                }
                for order, (detector_id, detector_cls) in enumerate(
                    DETECTOR_REGISTRY.items(), start=1
                )
            ],
            "overall_score": None,
            "total_issues": 0,
            "raw_issues": 0,
            "duplicates_removed": 0,
            "registry_warnings": list(REGISTRY_WARNINGS),
        }
    
    def run(self) -> Tuple[List[Dict[str, Any]], javalang.tree.CompilationUnit]:
        """
        Run the complete analysis pipeline.
        
        Returns:
            Tuple of (list of deduplicated detected issues, parsed AST tree)
            
        Raises:
            ValueError: If syntax error or parsing fails
        """
        try:
            # Parse the Java source code into an AST
            tree = javalang.parse.parse(self.code)
        except javalang.parser.JavaSyntaxError as e:
            # Degraded path: no AST -> every detector is skipped and the
            # overall score stays None (rendered as N/A on the pipeline page).
            for row in self.pipeline_report["detectors"]:
                if row["status"] == "pending":
                    row["status"] = "skipped"
            raise ValueError(f"Syntax Error at {e.at}: {e.description}")
        except Exception as e:
            for row in self.pipeline_report["detectors"]:
                if row["status"] == "pending":
                    row["status"] = "skipped"
            raise ValueError(f"AST Analysis Failed: {str(e)}")

        # Run detectors one by one. A crashing detector is isolated in
        # place: it contributes zero issues, is marked "error", and is
        # excluded from the overall score, so it cannot pollute the other
        # detectors or the total.
        all_issues: List[Dict[str, Any]] = []
        rows = self.pipeline_report["detectors"]
        for detector in self.detectors:
            row = next(r for r in rows if r["id"] == detector.detector_id)
            try:
                issues = detector.detect(tree, self.lines)
            except Exception as exc:
                row["status"] = "error"
                row["error"] = f"{type(exc).__name__}: {exc}"
                continue
            for issue in issues:
                issue["_detector"] = detector.detector_id
            row["status"] = "ok"
            row["raw_hits"] = len(issues)
            all_issues.extend(issues)

        deduped = deduplicate_issues(all_issues)

        # Attribute surviving issues back to their detector and score each
        # detector on its own deduplicated, severity-weighted hits.
        ok_scores = []
        for row in rows:
            if row["status"] != "ok":
                continue
            own = [i for i in deduped if i["_detector"] == row["id"]]
            row["hits"] = len(own)
            row["weighted_hits"] = sum(SEVERITY_WEIGHTS[i["Severity"]] for i in own)
            row["score"] = normalize_score(row["weighted_hits"])
            ok_scores.append(row["score"])

        self.pipeline_report["raw_issues"] = len(all_issues)
        self.pipeline_report["total_issues"] = len(deduped)
        self.pipeline_report["duplicates_removed"] = len(all_issues) - len(deduped)
        # Degraded path: if no detector produced a usable score, the overall
        # score stays None instead of silently defaulting to 100.
        self.pipeline_report["overall_score"] = (
            max(0, min(100, round(sum(ok_scores) / len(ok_scores))))
            if ok_scores else None
        )

        for issue in deduped:
            issue.pop("_detector", None)
        return deduped, tree
    
    def calculate_metrics(self, tree: javalang.tree.CompilationUnit) -> Dict[str, Any]:
        """
        Calculate comprehensive code metrics from the AST.
        
        Args:
            tree: Parsed Java AST
            
        Returns:
            Dictionary containing various code metrics
        """
        metrics = {
            'total_classes': 0,
            'total_methods': 0,
            'total_fields': 0,
            'total_lines': len(self.lines),
            'blank_lines': count_blank_lines(self.lines),
            'comment_lines': count_comment_lines(self.lines),
            'avg_method_length': 0,
            'max_method_length': 0,
            'avg_complexity': 0,
            'max_complexity': 0,
            'code_lines': 0
        }
        
        method_lengths = []
        complexities = []
        
        # Analyze classes
        for _, node in tree.filter(javalang.tree.ClassDeclaration):
            metrics['total_classes'] += 1
            
            # Count methods
            if node.methods:
                metrics['total_methods'] += len(node.methods)
                
                for method in node.methods:
                    # Calculate method length
                    if method.body:
                        length = len(method.body)
                        method_lengths.append(length)
                        
                        # Calculate cyclomatic complexity
                        complexity = self._calculate_complexity(method)
                        complexities.append(complexity)
            
            # Count fields
            if node.fields:
                metrics['total_fields'] += len(node.fields)
        
        # Calculate averages
        if method_lengths:
            metrics['avg_method_length'] = sum(method_lengths) / len(method_lengths)
            metrics['max_method_length'] = max(method_lengths)
        
        if complexities:
            metrics['avg_complexity'] = sum(complexities) / len(complexities)
            metrics['max_complexity'] = max(complexities)
        
        # Calculate code lines (excluding blanks and comments)
        metrics['code_lines'] = (metrics['total_lines'] - 
                                 metrics['blank_lines'] - 
                                 metrics['comment_lines'])
        
        return metrics
    
    def _calculate_complexity(self, method_node: javalang.tree.MethodDeclaration) -> int:
        """
        Calculate cyclomatic complexity for a method.
        
        Args:
            method_node: AST node representing a method
            
        Returns:
            Cyclomatic complexity value
        """
        count = 1
        branch_types = (
            javalang.tree.IfStatement,
            javalang.tree.WhileStatement,
            javalang.tree.DoStatement,
            javalang.tree.ForStatement,
            javalang.tree.CatchClause,
            javalang.tree.SwitchStatementCase,
            javalang.tree.TernaryExpression
        )
        
        for _, node in method_node.filter(branch_types):
            count += 1
        
        return count
