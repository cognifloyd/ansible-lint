"""Transformer implementation."""
import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Set, Union, cast

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from ansiblelint.errors import MatchError
from ansiblelint.file_utils import Lintable
from ansiblelint.rules import TransformMixin
from ansiblelint.runner import LintResult
from ansiblelint.yaml_utils import FormattedYAML

__all__ = ["Transformer"]

if TYPE_CHECKING:
    # noinspection PyProtectedMember
    from ruamel.yaml.comments import LineCol

_logger = logging.getLogger(__name__)


PLAYBOOK_TASK_KEYWORDS = [
    'tasks',
    'pre_tasks',
    'post_tasks',
    'handlers',
]
NESTED_TASK_KEYS = [
    'block',
    'always',
    'rescue',
]


class Transformer:
    """Transformer class marshals transformations.

    The Transformer is similar to the ``ansiblelint.runner.Runner`` which manages
    running each of the rules. We only expect there to be one ``Transformer`` instance
    which should be instantiated from the main entrypoint function.

    In the future, the transformer will be responsible for running transforms for each
    of the rule matches. For now, it just reads/writes YAML files which is a
    pre-requisite for the planned rule-specific transforms.
    """

    def __init__(self, result: LintResult):
        """Initialize a Transformer instance."""
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
        """For each file, read it, execute transforms on it, then write it."""
        yaml = FormattedYAML()
        for file, matches in self.matches_per_file.items():
            # str() convinces mypy that "text/yaml" is a valid Literal.
            # Otherwise, it thinks base_kind is one of playbook, meta, tasks, ...
            file_is_yaml = str(file.base_kind) == "text/yaml"

            try:
                data: str = file.content
            except (UnicodeDecodeError, IsADirectoryError):
                # we hit a binary file (eg a jar or tar.gz) or a directory
                data = ""
                file_is_yaml = False

            if file_is_yaml:
                ruamel_data: Optional[Union[CommentedMap, CommentedSeq]] = yaml.loads(data)
                if not isinstance(ruamel_data, (CommentedMap, CommentedSeq)):
                    # This is an empty vars file or similar which loads as None.
                    # It is not safe to write this file or data-loss is likely.
                    # Only maps and sequences can preserve comments. Skip it.
                    continue
            else:
                ruamel_data = None

            self._do_transforms(file, ruamel_data or data, file_is_yaml, matches)

            if file_is_yaml:
                # YAML transforms modify data in-place. Now write it to file.
                file.content = yaml.dumps(ruamel_data)
                file.write()

            # transforms for other filetypes must handle writing it to file.

    def _do_transforms(
        self,
        file: Lintable,
        data: Union[CommentedMap, CommentedSeq, str],
        file_is_yaml: bool,
        matches: List[MatchError],
    ) -> None:
        for match in sorted(matches):
            if not isinstance(match.rule, TransformMixin):
                continue
            if file_is_yaml and not match.yaml_path:
                data = cast(Union[CommentedMap, CommentedSeq], data)
                if match.match_type == "play":
                    match.yaml_path = self._get_play_path(file, match.linenumber, data)
                elif match.task or file.kind in (
                    "tasks",
                    "handlers",
                    "playbook",
                ):
                    match.yaml_path = self._get_task_path(file, match.linenumber, data)
            match.rule.transform(match, file, data)

    @staticmethod
    def _get_play_path(
        lintable: Lintable,
        linenumber: int,  # 1-based
        ruamel_data: Union[CommentedMap, CommentedSeq],
    ) -> Sequence[Union[str, int]]:
        if lintable.kind != "playbook":
            return []
        ruamel_data = cast(CommentedSeq, ruamel_data)
        lc: "LineCol"  # lc uses 0-based counts
        # linenumber and last_line are 1-based. Convert to 0-based.
        linenumber_0 = linenumber - 1

        prev_play_line = ruamel_data.lc.line
        play_count = len(ruamel_data)
        for i_play, play in enumerate(ruamel_data):
            i_next_play = i_play + 1
            if play_count > i_next_play:
                next_play_line = ruamel_data[i_next_play].lc.line
            else:
                next_play_line = None

            lc = play.lc
            assert isinstance(lc.line, int)
            if lc.line == linenumber_0:
                return [i_play]
            if i_play > 0 and prev_play_line < linenumber_0 < lc.line:
                return [i_play - 1]
            # The previous play check (above) can't catch the last play,
            # so, handle the last play separately.
            if (
                i_play + 1 == play_count
                and linenumber_0 > lc.line
                and (next_play_line is None or linenumber_0 < next_play_line)
            ):
                # part of this (last) play
                return [i_play]
            prev_play_line = play.lc.line
        return []

    def _get_task_path(
        self,
        lintable: Lintable,
        linenumber: int,  # 1-based
        ruamel_data: Union[CommentedMap, CommentedSeq],
    ) -> Sequence[Union[str, int]]:
        if lintable.kind in ("tasks", "handlers"):
            assert isinstance(ruamel_data, CommentedSeq)
            return self._get_task_path_in_tasks_block(linenumber, ruamel_data)
        if lintable.kind == "playbook":
            assert isinstance(ruamel_data, CommentedSeq)
            return self._get_task_path_in_playbook(linenumber, ruamel_data)
        # if lintable.kind in ['yaml', 'requirements', 'vars', 'meta', 'reno']:

        return []

    def _get_task_path_in_playbook(
        self,
        linenumber: int,  # 1-based
        ruamel_data: CommentedSeq,
    ) -> Sequence[Union[str, int]]:
        play_count = len(ruamel_data)
        for i_play, play in enumerate(ruamel_data):
            i_next_play = i_play + 1
            if play_count > i_next_play:
                next_play_line = ruamel_data[i_next_play].lc.line
            else:
                next_play_line = None

            play_keys = list(play.keys())
            for tasks_keyword in PLAYBOOK_TASK_KEYWORDS:
                if not play.get(tasks_keyword):
                    continue

                try:
                    next_keyword = play_keys[play_keys.index(tasks_keyword) + 1]
                except IndexError:
                    next_block_line = None
                else:
                    next_block_line = play.lc.data[next_keyword][0]
                # last_line_in_block is 1-based; next_*_line is 0-based
                if next_block_line is not None:
                    last_line_in_block = next_block_line
                elif next_play_line is not None:
                    last_line_in_block = next_play_line
                else:
                    last_line_in_block = None

                task_path = self._get_task_path_in_tasks_block(
                    linenumber, play[tasks_keyword], last_line_in_block
                )
                if task_path:
                    # mypy gets confused without this typehint
                    tasks_keyword_path: List[Union[int, str]] = [
                        i_play,
                        tasks_keyword,
                    ]
                    return tasks_keyword_path + list(task_path)
        # probably no tasks keywords in any of the plays
        return []

    def _get_task_path_in_tasks_block(
        self,
        linenumber: int,  # 1-based
        tasks_block: CommentedSeq,
        last_line: Optional[int] = None,  # 1-based
    ) -> Sequence[Union[str, int]]:
        task: CommentedMap
        # lc (LineCol) uses 0-based counts
        # linenumber and last_line are 1-based. Convert to 0-based.
        linenumber_0 = linenumber - 1
        last_line_0 = None if last_line is None else last_line - 1

        prev_task_line = tasks_block.lc.line
        tasks_count = len(tasks_block)
        for i_task, task in enumerate(tasks_block):
            i_next_task = i_task + 1
            if tasks_count > i_next_task:
                next_task_line_0 = tasks_block[i_next_task].lc.line
            else:
                next_task_line_0 = None

            nested_task_keys = set(task.keys()).intersection(set(NESTED_TASK_KEYS))
            if nested_task_keys:
                subtask_path = self._get_task_path_in_nested_tasks_block(
                    linenumber, task, nested_task_keys, next_task_line_0
                )
                if subtask_path:
                    # mypy gets confused without this typehint
                    task_path: List[Union[str, int]] = [i_task]
                    return task_path + list(subtask_path)

            assert isinstance(task.lc.line, int)
            if task.lc.line == linenumber_0:
                return [i_task]
            if i_task > 0 and prev_task_line < linenumber_0 < task.lc.line:
                return [i_task - 1]
            # The previous task check can't catch the last task,
            # so, handle the last task separately (also after subtask checks).
            # pylint: disable=too-many-boolean-expressions
            if (
                i_task + 1 == tasks_count
                and linenumber_0 > task.lc.line
                and (next_task_line_0 is None or linenumber_0 < next_task_line_0)
                and (last_line_0 is None or linenumber_0 <= last_line_0)
            ):
                # part of this (last) task
                return [i_task]
            prev_task_line = task.lc.line
        return []

    def _get_task_path_in_nested_tasks_block(
        self,
        linenumber: int,  # 1-based
        task: CommentedMap,
        nested_task_keys: Set[str],
        next_task_line_0: Optional[int] = None,  # 0-based
    ) -> Sequence[Union[str, int]]:
        subtask: CommentedMap
        # loop through the keys in line order
        task_keys = list(task.keys())
        task_keys_by_index = dict(enumerate(task_keys))
        for task_index, task_key in enumerate(task_keys):
            nested_task_block = task[task_key]
            if task_key not in nested_task_keys or not nested_task_block:
                continue
            next_task_key = task_keys_by_index.get(task_index + 1, None)
            if next_task_key is not None:
                next_task_key_line_0 = task.lc.data[next_task_key][0]
            else:
                next_task_key_line_0 = None
            # 0-based next_line - 1 to get line before next_line.
            # Then + 1 to make it a 1-based number.
            # So, next_task*_0 - 1 + 1 = last_block_line
            last_block_line = (
                next_task_key_line_0
                if next_task_key_line_0 is not None
                else next_task_line_0
            )
            subtask_path = self._get_task_path_in_tasks_block(
                linenumber,
                nested_task_block,
                last_block_line,  # 1-based
            )
            if subtask_path:
                return [task_key] + list(subtask_path)
        return []
