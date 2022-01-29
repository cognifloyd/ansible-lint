"""Transformer implementation."""
import logging
import re
from typing import Dict, List, Set, Union

from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.emitter import Emitter

# Module 'ruamel.yaml' does not explicitly export attribute 'YAML'; implicit reexport disabled
# To make the type checkers happy, we import from ruamel.yaml.main instead.
from ruamel.yaml.main import YAML

from .errors import MatchError
from .file_utils import Lintable
from .runner import LintResult
from .skip_utils import load_data  # TODO: move load_data out of skip_utils

__all__ = ["Transformer"]

_logger = logging.getLogger(__name__)

_comment_line_re = re.compile(r"^ *#")


class FormattedEmitter(Emitter):
    """Emitter that applies custom formatting rules when dumping YAML.

    Root-level sequences are never indented.
    All subsequent levels are indented as configured (normal ruamel.yaml behavior).

    Earlier implementations used dedent on ruamel.yaml's dumped output,
    but string magic like that had a ton of problematic edge cases.
    """

    _sequence_indent = 2
    _sequence_dash_offset = 0  # Should be _sequence_indent - 2

    # NB: mypy does not support overriding attributes with properties yet:
    #     https://github.com/python/mypy/issues/4125
    #     To silence we have to ignore[override] both the @property and the method.

    @property  # type: ignore[override]
    def best_sequence_indent(self) -> int:  # type: ignore[override]
        """Return the configured sequence_indent or 2 for root level."""
        return 2 if self.column < 2 else self._sequence_indent

    @best_sequence_indent.setter
    def best_sequence_indent(self, value: int) -> None:
        """Configure how many columns to indent each sequence item (including the '-')."""
        self._sequence_indent = value

    @property  # type: ignore[override]
    def sequence_dash_offset(self) -> int:  # type: ignore[override]
        """Return the configured sequence_dash_offset or 2 for root level."""
        return 0 if self.column < 2 else self._sequence_dash_offset

    @sequence_dash_offset.setter
    def sequence_dash_offset(self, value: int) -> None:
        """Configure how many spaces to put before each sequence item's '-'."""
        self._sequence_dash_offset = value


# Transformer is for transforms like runner is for rules
class Transformer:
    """Transformer class performs the fmt transformations."""

    def __init__(self, result: LintResult):
        """Initialize a Transformer instance."""
        # TODO: options for explict_start, indent_sequences
        self.explicit_start = True
        self.indent_sequences = True

        self.matches: List[MatchError] = result.matches
        self.files: Set[Lintable] = result.files

        file: Lintable
        lintables: Dict[str, Lintable] = {file.filename: file for file in result.files}
        self.matches_per_file: Dict[Lintable, List[MatchError]] = {
            file: [] for file in result.files
        }

        for match in self.matches:
            try:
                lintable = lintables[match.filename]
            except KeyError:
                # we shouldn't get here, but this is easy to recover from so do that.
                lintable = Lintable(match.filename)
                self.matches_per_file[lintable] = []
            self.matches_per_file[lintable].append(match)

    def run(self) -> None:
        """Execute the fmt transforms."""
        # ruamel.yaml rt=round trip (preserves comments while allowing for modification)
        yaml = YAML(typ="rt")

        # NB: ruamel.yaml does not have typehints, so mypy complains about everything here.

        # configure yaml dump formatting
        yaml.explicit_start = True  # type: ignore[assignment]
        yaml.explicit_end = False  # type: ignore[assignment]

        # TODO: make the width configurable
        # yaml.width defaults to 80 which wraps longer lines in tests
        yaml.width = 120  # type: ignore[assignment]

        yaml.default_flow_style = False
        yaml.compact_seq_seq = (  # dash after dash
            True  # type: ignore[assignment]
        )
        yaml.compact_seq_map = (  # key after dash
            True  # type: ignore[assignment]
        )
        # yaml.indent() obscures the purpose of these vars:
        yaml.map_indent = 2  # type: ignore[assignment]
        yaml.sequence_indent = 4 if self.indent_sequences else 2  # type: ignore[assignment]
        yaml.sequence_dash_offset = yaml.sequence_indent - 2  # type: ignore[operator]

        if self.indent_sequences:  # in the future: or other formatting options
            # For root-level sequences, FormattedEmitter overrides sequence_indent
            # and sequence_dash_offset to prevent root-level indents.
            yaml.Emitter = FormattedEmitter

        # explicit_start=True + map_indent=2 + sequence_indent=2 + sequence_dash_offset=0
        # ---
        # - name: playbook
        #   loop:
        #   - item1
        #
        # explicit_start=True + map_indent=2 + sequence_indent=4 + sequence_dash_offset=2
        # With the normal Emitter
        # ---
        #   - name: playbook
        #     loop:
        #       - item1
        #
        # explicit_start=True + map_indent=2 + sequence_indent=4 + sequence_dash_offset=2
        # With the FormattedEmitter
        # ---
        # - name: playbook
        #   loop:
        #     - item1

        for file, matches in self.matches_per_file.items():
            # str() convinces mypy that "text/yaml" is a valid Literal.
            # Otherwise, it thinks base_kind is one of playbook, meta, tasks, ...
            file_is_yaml = str(file.base_kind) == "text/yaml"

            if file_is_yaml:
                # load_data has an lru_cache, so using it should be cached vs using YAML().load() to reload
                data: Union[CommentedMap, CommentedSeq] = load_data(file.content)
                yaml.dump(data, file.path)
