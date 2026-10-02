"""
Abstract Base Class for Code Smell Detectors
Defines the contract that all detector implementations must follow,
plus the global detector registry used by the analyzer engine.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Type
import javalang


# Global detector registry. Keyed logically by ``detector_id``; the first
# class registered for a given id wins, later collisions are skipped and
# recorded in ``_REGISTRY_CONFLICTS`` so the pipeline page can show them.
_DETECTOR_REGISTRY: List[Type["CodeSmell"]] = []
_REGISTRY_CONFLICTS: List[Dict[str, str]] = []


def register_detector(detector_cls: Type["CodeSmell"]) -> bool:
    """
    Register a detector class. On ``detector_id`` collision the class that
    was registered first stays active and the newcomer is skipped (and
    recorded), keeping resolution deterministic.
    """
    for existing in _DETECTOR_REGISTRY:
        if existing.detector_id == detector_cls.detector_id:
            _REGISTRY_CONFLICTS.append({
                "detector_id": detector_cls.detector_id,
                "kept": existing.__name__,
                "skipped": detector_cls.__name__,
            })
            return False
    _DETECTOR_REGISTRY.append(detector_cls)
    return True


def registered_detectors() -> List[Type["CodeSmell"]]:
    """
    Return registered detector classes in deterministic execution order,
    sorted by explicit ``(priority, detector_id)`` rather than import order.
    """
    return sorted(_DETECTOR_REGISTRY, key=lambda c: (c.priority, c.detector_id))


def registry_conflicts() -> List[Dict[str, str]]:
    """Return the list of skipped duplicate detector registrations."""
    return list(_REGISTRY_CONFLICTS)


class CodeSmell(ABC):
    """
    Abstract base class for all code smell detectors.
    Implements the Strategy Pattern for different detection algorithms.

    Class attributes:
        detector_id: Unique registry key. Reusing an existing id (e.g. a
            subclass that forgets to override it) loses to the first
            registration and is recorded as a conflict.
        priority: Execution order key; lower runs earlier.
        config_key: Engine config toggle that enables this detector.
            Empty string means "never auto-enabled" (registry only).
    """

    detector_id: str = ""
    priority: int = 100
    config_key: str = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        register_detector(cls)

    @abstractmethod
    def detect(self, tree: javalang.tree.CompilationUnit, lines: List[str]) -> List[Dict[str, Any]]:
        """
        Detect code smells in the given AST tree.
        
        Args:
            tree: Parsed Java AST (Abstract Syntax Tree)
            lines: Source code split into lines
            
        Returns:
            List of dictionaries containing detected issues with keys:
            - Type: The smell type name
            - Target: The affected element (class/method name)
            - Severity: Critical/High/Medium/Low
            - Reason: Detailed explanation
            - Category: Design/Implementation/Naming/Documentation
        """
        pass
    
    def _create_issue(self, smell_type: str, target: str, severity: str, 
                      reason: str, category: str) -> Dict[str, Any]:
        """
        Helper method to create a standardized issue dictionary.
        
        Args:
            smell_type: Name of the code smell
            target: Affected code element
            severity: Severity level
            reason: Detailed explanation
            category: Issue category
            
        Returns:
            Standardized issue dictionary
        """
        return {
            "Type": smell_type,
            "Target": target,
            "Severity": severity,
            "Reason": reason,
            "Category": category
        }
