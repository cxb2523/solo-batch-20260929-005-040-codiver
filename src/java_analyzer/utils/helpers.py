"""
Helper Functions
Utility functions for naming validation, line counting, issue
deduplication and normalized quality scoring.
"""

import re
from typing import Any, Dict, List, Optional


# Severity weights shared by the pipeline report and the normalized score.
SEVERITY_WEIGHTS = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}

# Score points deducted per unit of severity weight.
PENALTY_PER_WEIGHT = 5


def validate_class_name(name: str) -> bool:
    """
    Validate that a class name follows PascalCase convention.
    
    Args:
        name: The class name to validate
        
    Returns:
        True if valid, False otherwise
    """
    return bool(re.match(r'^[A-Z][a-zA-Z0-9]*$', name))


def validate_method_name(name: str) -> bool:
    """
    Validate that a method name follows camelCase convention.
    
    Args:
        name: The method name to validate
        
    Returns:
        True if valid, False otherwise
    """
    return bool(re.match(r'^[a-z][a-zA-Z0-9]*$', name))


def count_blank_lines(lines: List[str]) -> int:
    """
    Count the number of blank lines in source code.
    
    Args:
        lines: Source code split into lines
        
    Returns:
        Number of blank lines
    """
    return sum(1 for line in lines if line.strip() == '')


def count_comment_lines(lines: List[str]) -> int:
    """
    Count the number of comment lines (single-line and multi-line).
    
    Args:
        lines: Source code split into lines
        
    Returns:
        Number of comment lines
    """
    count = 0
    in_block_comment = False
    
    for line in lines:
        stripped = line.strip()
        
        # Check for block comment start
        if '/*' in stripped:
            in_block_comment = True
        
        # Count line if in block comment or single-line comment
        if in_block_comment or stripped.startswith('//'):
            count += 1
        
        # Check for block comment end
        if '*/' in stripped:
            in_block_comment = False
    
    return count


def calculate_comment_ratio(total_lines: int, comment_lines: int) -> float:
    """
    Calculate the ratio of comment lines to total lines.
    
    Args:
        total_lines: Total number of lines
        comment_lines: Number of comment lines
        
    Returns:
        Comment ratio as a percentage (0-100)
    """
    if total_lines == 0:
        return 0.0
    return (comment_lines / total_lines) * 100


def calculate_quality_score(total_issues: int, critical_count: int) -> int:
    """
    Calculate an overall quality score based on issues found.
    
    Args:
        total_issues: Total number of issues detected
        critical_count: Number of critical issues
        
    Returns:
        Quality score (0-100)
    """
    score = 100 - (total_issues * 2) - (critical_count * 10)
    return max(0, score)


def deduplicate_issues(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge duplicate issues reported by multiple detectors.

    Two issues are duplicates when they share the same (Type, Target).
    The earliest occurrence (pipeline registration order) is kept as the
    canonical entry, but its Severity/Reason are upgraded to the highest
    severity seen across all duplicates, so the total weighted penalty is
    independent of detector order.

    Args:
        issues: Raw issues in pipeline order

    Returns:
        Deduplicated issues, preserving first-occurrence order
    """
    merged: Dict[Any, Dict[str, Any]] = {}
    order: List[Any] = []

    for issue in issues:
        key = (issue.get("Type"), issue.get("Target"))
        if key not in merged:
            merged[key] = dict(issue)
            order.append(key)
        else:
            current = merged[key]
            if SEVERITY_WEIGHTS.get(issue.get("Severity"), 0) > \
                    SEVERITY_WEIGHTS.get(current.get("Severity"), 0):
                current["Severity"] = issue["Severity"]
                current["Reason"] = issue["Reason"]

    return [merged[key] for key in order]


def calculate_weighted_penalty(issues: List[Dict[str, Any]]) -> int:
    """
    Calculate the total weighted penalty of a list of issues.

    penalty = PENALTY_PER_WEIGHT * sum(SEVERITY_WEIGHTS[severity])

    Args:
        issues: Issues (already deduplicated) to weigh

    Returns:
        Total penalty points
    """
    return sum(SEVERITY_WEIGHTS.get(i.get("Severity"), 0) for i in issues) * PENALTY_PER_WEIGHT


def clamp_score(score: int) -> int:
    """Clamp a score into the inclusive 0-100 range."""
    return min(100, max(0, score))


def calculate_normalized_score(issues: Optional[List[Dict[str, Any]]]) -> Optional[int]:
    """
    Calculate the normalized quality score: 100 minus the weighted
    penalty, clamped to 0-100.

    Args:
        issues: Deduplicated issues, or None when the analysis data is
            missing (e.g. AST parsing failed)

    Returns:
        Score in [0, 100], or None when the input data is missing so the
        UI can render "N/A" instead of a misleading 0 or 100.
    """
    if issues is None:
        return None
    return clamp_score(100 - calculate_weighted_penalty(issues))


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted string (e.g., "1.5 KB", "2.3 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"
