"""Utility helpers to simplify working with yaml-based data."""
import functools
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Union, cast

from ruamel.yaml.emitter import Emitter

import ansiblelint.skip_utils
from ansiblelint.errors import MatchError
from ansiblelint.file_utils import Lintable
from ansiblelint.utils import get_action_tasks, normalize_task, parse_yaml_linenumbers


def iter_tasks_in_file(
    lintable: Lintable, rule_id: str
) -> Iterator[Tuple[Dict[str, Any], Dict[str, Any], bool, Optional[MatchError]]]:
    """Iterate over tasks in file.

    This yields a 4-tuple of raw_task, normalized_task, skipped, and error.

    raw_task:
        When looping through the tasks in the file, each "raw_task" is minimally
        processed to include these special keys: __line__, __file__, skipped_rules.
    normalized_task:
        When each raw_task is "normalized", action shorthand (strings) get parsed
        by ansible into python objects and the action key gets normalized. If the task
        should be skipped (skipped is True) or normalizing it fails (error is not None)
        then this is just the raw_task instead of a normalized copy.
    skipped:
        Whether or not the task should be skipped according to tags or skipped_rules.
    error:
        This is normally None. It will be a MatchError when the raw_task cannot be
        normalized due to an AnsibleParserError.

    :param lintable: The playbook or tasks/handlers yaml file to get tasks from
    :param rule_id: The current rule id to allow calculating skipped.

    :return: raw_task, normalized_task, skipped, error
    """
    data = parse_yaml_linenumbers(lintable)
    if not data:
        return
    data = ansiblelint.skip_utils.append_skipped_rules(data, lintable)

    raw_tasks = get_action_tasks(data, lintable)

    for raw_task in raw_tasks:
        err: Optional[MatchError] = None

        # An empty `tags` block causes `None` to be returned if
        # the `or []` is not present - `task.get('tags', [])`
        # does not suffice.
        skipped_in_task_tag = "skip_ansible_lint" in (raw_task.get("tags") or [])
        skipped_in_yaml_comment = rule_id in raw_task.get("skipped_rules", ())
        skipped = skipped_in_task_tag or skipped_in_yaml_comment
        if skipped:
            yield raw_task, raw_task, skipped, err
            continue

        try:
            normalized_task = normalize_task(raw_task, str(lintable.path))
        except MatchError as err:
            # normalize_task converts AnsibleParserError to MatchError
            yield raw_task, raw_task, skipped, err
            return

        yield raw_task, normalized_task, skipped, err


def nested_items_path(
    data_collection: Union[Dict[Any, Any], List[Any]],
) -> Iterator[Tuple[Any, Any, List[Union[str, int]]]]:
    """Iterate a nested data structure, yielding key/index, value, and parent_path.

    This is a recursive function that calls itself for each nested layer of data.
    Each iteration yields:

    1. the current item's dictionary key or list index,
    2. the current item's value, and
    3. the path to the current item from the outermost data structure.

    For dicts, the yielded (1) key and (2) value are what ``dict.items()`` yields.
    For lists, the yielded (1) index and (2) value are what ``enumerate()`` yields.
    The final component, the parent path, is a list of dict keys and list indexes.
    The parent path can be helpful in providing error messages that indicate
    precisely which part of a yaml file (or other data structure) needs to be fixed.

    For example, given this playbook:

    .. code-block:: yaml

        - name: a play
          tasks:
          - name: a task
            debug:
              msg: foobar

    Here's the first and last yielded items:

    .. code-block:: python

        >>> playbook=[{"name": "a play", "tasks": [{"name": "a task", "debug": {"msg": "foobar"}}]}]
        >>> next( nested_items_path( playbook ) )
        (0, {'name': 'a play', 'tasks': [{'name': 'a task', 'debug': {'msg': 'foobar'}}]}, [])
        >>> list( nested_items_path( playbook ) )[-1]
        ('msg', 'foobar', [0, 'tasks', 0, 'debug'])

    Note that, for outermost data structure, the parent path is ``[]`` because
    you do not need to descend into any nested dicts or lists to find the indicated
    key and value.

    If a rule were designed to prohibit "foobar" debug messages, it could use the
    parent path to provide a path to the problematic ``msg``. It might use a jq-style
    path in its error message: "the error is at ``.[0].tasks[0].debug.msg``".
    Or if a utility could automatically fix issues, it could use the path to descend
    to the parent object using something like this:

    .. code-block:: python

        target = data
        for segment in parent_path:
            target = target[segment]

    :param data_collection: The nested data (dicts or lists).

    :returns: each iteration yields the key (of the parent dict) or the index (lists)
    """
    yield from _nested_items_path(data_collection=data_collection, parent_path=[])


def _nested_items_path(
    data_collection: Union[Dict[Any, Any], List[Any]],
    parent_path: List[Union[str, int]],
) -> Iterator[Tuple[Any, Any, List[Union[str, int]]]]:
    """Iterate through data_collection (internal implementation of nested_items_path).

    This is a separate function because callers of nested_items_path should
    not be using the parent_path param which is used in recursive _nested_items_path
    calls to build up the path to the parent object of the current key/index, value.
    """
    # we have to cast each convert_to_tuples assignment or mypy complains
    # that both assignments (for dict and list) do not have the same type
    convert_to_tuples_type = Callable[[], Iterator[Tuple[Union[str, int], Any]]]
    if isinstance(data_collection, dict):
        convert_data_collection_to_tuples = cast(
            convert_to_tuples_type, functools.partial(data_collection.items)
        )
    elif isinstance(data_collection, list):
        convert_data_collection_to_tuples = cast(
            convert_to_tuples_type, functools.partial(enumerate, data_collection)
        )
    else:
        raise TypeError(
            f"Expected a dict or a list but got {data_collection!r} "
            f"of type '{type(data_collection)}'"
        )
    for key, value in convert_data_collection_to_tuples():
        yield key, value, parent_path
        if isinstance(value, (dict, list)):
            yield from _nested_items_path(
                data_collection=value, parent_path=parent_path + [key]
            )


def final_yaml_dump_transform(text: str) -> str:
    """Transform YAML string before writing to file.

    Ansible uses PyYAML which only supports YAML 1.1, so we dump YAML 1.1.
    But we don't want "%YAML 1.1" at the start, so drop that.
    """
    prefix = "%YAML 1.1\n"
    prefix_len = len(prefix)
    if text.startswith(prefix):
        return text[prefix_len:]
    return text


class FormattedEmitter(Emitter):
    """Emitter that applies custom formatting rules when dumping YAML.

    Differences from ruamel.yaml defaults:

      - indentation of root-level sequences
      - prefer double-quoted scalars over single-quoted scalars

    This ensures that root-level sequences are never indented.
    All subsequent levels are indented as configured (normal ruamel.yaml behavior).

    Earlier implementations used dedent on ruamel.yaml's dumped output,
    but string magic like that had a ton of problematic edge cases.
    """

    preferred_quote = '"'  # either " or '

    _sequence_indent = 2
    _sequence_dash_offset = 0  # Should be _sequence_indent - 2

    @property
    def _is_root_level(self) -> bool:
        """Return True if this is the root level of the yaml document.

        Here, root level means the outermost sequence or map of the document.
        """
        return self.column < 2

    # NB: mypy does not support overriding attributes with properties yet:
    #     https://github.com/python/mypy/issues/4125
    #     To silence we have to ignore[override] both the @property and the method.

    @property  # type: ignore[override]
    def best_sequence_indent(self) -> int:  # type: ignore[override]
        """Return the configured sequence_indent or 2 for root level."""
        return 2 if self._is_root_level else self._sequence_indent

    @best_sequence_indent.setter
    def best_sequence_indent(self, value: int) -> None:
        """Configure how many columns to indent each sequence item (including the '-')."""
        self._sequence_indent = value

    @property  # type: ignore[override]
    def sequence_dash_offset(self) -> int:  # type: ignore[override]
        """Return the configured sequence_dash_offset or 2 for root level."""
        return 0 if self._is_root_level else self._sequence_dash_offset

    @sequence_dash_offset.setter
    def sequence_dash_offset(self, value: int) -> None:
        """Configure how many spaces to put before each sequence item's '-'."""
        self._sequence_dash_offset = value

    def choose_scalar_style(self) -> Any:
        """Select how to quote scalars if needed."""
        style = super().choose_scalar_style()
        if style != "'":
            # block scalar, double quoted, etc.
            return style
        if '"' in self.event.value:
            return "'"
        return self.preferred_quote
