"""
Static Analyzer Engine
Core logic for AST parsing and metric calculation
"""

import javalang
from typing import List, Dict, Any, Tuple
from detectors.base import CodeSmell, registered_detectors
from detectors.design import DesignSmells  # noqa: F401  (registry import)
from detectors.implementation import ImplementationSmells  # noqa: F401
from detectors.naming_docs import NamingSmells, DocumentationSmells  # noqa: F401
from utils.helpers import (
    count_blank_lines,
    count_comment_lines,
    deduplicate_issues,
    calculate_normalized_score,
    clamp_score,
    SEVERITY_WEIGHTS,
    PENALTY_PER_WEIGHT,
)


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
        self.pipeline_report: List[Dict[str, Any]] = []
        self.quality_score: Any = None
    
    def _initialize_detectors(self) -> List[CodeSmell]:
        """
        Initialize detector instances from the global registry, in
        deterministic (priority, detector_id) order, filtered by config.
        Detectors without a ``config_key`` are registry-only and are
        never auto-enabled.
        
        Returns:
            List of code smell detector instances
        """
        detectors = []
        for detector_cls in registered_detectors():
            if detector_cls.config_key and self.config.get(detector_cls.config_key, True):
                detectors.append(detector_cls())
        return detectors
    
    def run(self) -> Tuple[List[Dict[str, Any]], javalang.tree.CompilationUnit]:
        """
        Run the complete analysis pipeline.

        Each detector runs in isolation: if one raises, it is marked
        "degraded" in ``self.pipeline_report``, contributes zero issues
        and is excluded from scoring, while the remaining detectors and
        the overall score are unaffected. A syntax/parse failure, by
        contrast, degrades the whole run and raises ValueError.
        
        Returns:
            Tuple of (deduplicated issues, parsed AST tree)
            
        Raises:
            ValueError: If syntax error or parsing fails
        """
        try:
            tree = javalang.parse.parse(self.code)
        except javalang.parser.JavaSyntaxError as e:
            raise ValueError(f"Syntax Error at {e.at}: {e.description}")
        except Exception as e:
            raise ValueError(f"AST Analysis Failed: {str(e)}")

        raw_pairs: List[Tuple[int, Dict[str, Any]]] = []
        self.pipeline_report = []

        for position, detector in enumerate(self.detectors):
            entry = {
                "order": position + 1,
                "detector_id": detector.detector_id,
                "detector": type(detector).__name__,
                "status": "ok",
                "error": None,
                "raw_hits": 0,
                "hits": 0,
                "weighted_penalty": 0,
                "normalized_score": None,
            }
            try:
                issues = detector.detect(tree, self.lines)
            except Exception as exc:
                issues = []
                entry["status"] = "degraded"
                entry["error"] = f"{type(exc).__name__}: {exc}"
            entry["raw_hits"] = len(issues)
            raw_pairs.extend((position, issue) for issue in issues)
            self.pipeline_report.append(entry)

        deduped = deduplicate_issues([issue for _, issue in raw_pairs])

        # Attribute each kept issue to the earliest detector (registration
        # order) that reported it, so per-detector hits sum to the total.
        owner: Dict[Any, int] = {}
        for position, issue in raw_pairs:
            key = (issue.get("Type"), issue.get("Target"))
            if key not in owner:
                owner[key] = position

        for issue in deduped:
            position = owner[(issue.get("Type"), issue.get("Target"))]
            entry = self.pipeline_report[position]
            entry["hits"] += 1
            entry["weighted_penalty"] += (
                SEVERITY_WEIGHTS.get(issue.get("Severity"), 0) * PENALTY_PER_WEIGHT
            )

        for entry in self.pipeline_report:
            if entry["status"] == "ok":
                entry["normalized_score"] = clamp_score(100 - entry["weighted_penalty"])

        self.quality_score = calculate_normalized_score(deduped)
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
