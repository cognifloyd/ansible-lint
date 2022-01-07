"""Transformer implementation."""
import logging
import re
from textwrap import dedent
from typing import Dict, List, Optional, Set, Union, TYPE_CHECKING

if TYPE_CHECKING:
    # noinspection PyProtectedMember
    from ruamel.yaml.comments import LineCol

# Module 'ruamel.yaml' does not explicitly export attribute 'YAML'; implicit reexport disabled
from ruamel.yaml import YAML  # type: ignore
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from .errors import MatchError
from .file_utils import Lintable
from .runner import LintResult
from .skip_utils import load_data  # TODO: move load_data out of skip_utils
from .transforms import Transform, TransformsCollection

_logger = logging.getLogger(__name__)

_comment_line_re = re.compile(r"^ *#")

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


# Transformer is for transforms like runner is for rules
class Transformer:
    """Transformer class performs the fmt transformations."""

    def __init__(
        self,
        result: LintResult,
        transforms: TransformsCollection,
    ):
        """Initialize a Transformer instance."""
        # TODO: options for explict_start, indent_sequences
        self.explicit_start = True
        self.indent_sequences = True

        self.matches: List[MatchError] = result.matches
        self.files: Set[Lintable] = result.files
        self.transforms = transforms

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

    def run(self, fmt_all_files=True) -> None:
        """Execute the fmt transforms."""
        # ruamel.yaml rt=round trip (preserves comments while allowing for modification)
        yaml = YAML(typ="rt")

        # configure yaml dump formatting
        yaml.explicit_start = (
            False  # explicit_start is handled in self._final_yaml_transform()
        )
        yaml.explicit_end = False
        yaml.default_flow_style = False
        yaml.compact_seq_seq = True  # dash after dash
        yaml.compact_seq_map = True  # key after dash
        # yaml.indent() obscures the purpose of these vars:
        yaml.map_indent = 2
        yaml.sequence_indent = 4 if self.indent_sequences else 2
        yaml.sequence_dash_offset = yaml.sequence_indent - 2

        # explicit_start=True + map_indent=2 + sequence_indent=2 + sequence_dash_offset=0
        # ---
        # - name: playbook
        #   loop:
        #   - item1
        #
        # explicit_start=True + map_indent=2 + sequence_indent=4 + sequence_dash_offset=2
        # ---
        #   - name: playbook
        #     loop:
        #       - item1

        for file, matches in self.matches_per_file.items():
            # matches can be empty if no LintErrors were found.
            # However, we can still fmt the yaml file
            if not fmt_all_files and not matches:
                continue
            # load_data has an lru_cache, so using it should be cached vs using YAML().load() to reload
            ruamel_data: Union[CommentedMap, CommentedSeq] = load_data(file.content)
            for match in sorted(matches):
                transforms: List[Transform] = self.transforms.get_transforms_for(match)
                if not transforms:
                    continue
                if match.task or file.kind in ("tasks", "handlers", "playbook"):
                    match.yaml_path = self._get_task_path(
                        file, match.linenumber, ruamel_data
                    )
                for transform in transforms:
                    transform(match, file, ruamel_data)
            yaml.dump(ruamel_data, file.path, transform=self._final_yaml_transform)

    def _get_task_path(
        self,
        lintable: Lintable,
        linenumber: int,  # 1-based
        ruamel_data: Union[CommentedMap, CommentedSeq],
    ) -> List[Union[str, int]]:
        if lintable.kind in ("tasks", "handlers"):
            return self._get_task_path_in_tasks_block(linenumber, ruamel_data)
        elif lintable.kind == "playbook":
            ruamel_data: CommentedSeq
            play_count = len(ruamel_data)
            for i_play, play in enumerate(ruamel_data):
                i_next_play = i_play + 1
                if play_count > i_next_play:
                    next_play_line = ruamel_data[i_next_play].lc.line
                else:
                    next_play_line = None

                play_keys = list(play.keys())
                play_keys_by_index = dict(enumerate(play_keys))
                for tasks_keyword in PLAYBOOK_TASK_KEYWORDS:
                    tasks_block = play.get(tasks_keyword, [])
                    if not tasks_block:
                        continue

                    play_index = play_keys.index(tasks_keyword)
                    next_keyword = play_keys_by_index.get(play_index + 1, None)
                    if next_keyword is not None:
                        next_block_line = play.lc.data[next_keyword][0]
                    else:
                        next_block_line = None
                    # last_line_in_block is 1-based; next_*_line is 0-based
                    if next_block_line is not None:
                        last_line_in_block = next_block_line
                    elif next_play_line is not None:
                        last_line_in_block = next_play_line
                    else:
                        last_line_in_block = None

                    tasks_yaml_path = self._get_task_path_in_tasks_block(
                        linenumber, tasks_block, last_line_in_block
                    )
                    if tasks_yaml_path:
                        return [i_play, tasks_keyword] + tasks_yaml_path
        # elif lintable.kind in ['yaml', 'requirements', 'vars', 'meta', 'reno']:

        return []

    def _get_task_path_in_tasks_block(
        self,
        linenumber: int,  # 1-based
        tasks_block: CommentedSeq,
        last_line: Optional[int] = None,  # 1-based
    ) -> List[Union[str, int]]:
        task: CommentedMap
        subtask: CommentedMap
        lc: LineCol  # lc uses 0-based counts
        # linenumber and last_line are 1-based. Convert to 0-based.
        linenumber_0 = linenumber - 1
        last_line_0 = None if last_line is None else last_line - 1

        prev_task_line = prev_subtask_line = tasks_block.lc.line
        tasks_count = len(tasks_block)
        for i_task, task in enumerate(tasks_block):
            i_next_task = i_task + 1
            if tasks_count > i_next_task:
                next_task_line = tasks_block[i_next_task].lc.line
            else:
                next_task_line = None

            lc = task.lc
            if lc.line == linenumber_0:
                return [i_task]
            elif i_task > 0 and prev_task_line < linenumber_0 < lc.line:
                return [i_task - 1]

            task_keys = list(task.keys())
            task_keys_by_index = dict(enumerate(task_keys))
            for block_key in NESTED_TASK_KEYS:
                if block_key in task and task[block_key]:
                    task_index = task_keys.index(block_key)
                    next_play_keyword = task_keys_by_index.get(task_index + 1, None)
                    if next_play_keyword is not None:
                        next_play_keyword_line = task.lc.data[next_play_keyword][0]
                    else:
                        next_play_keyword_line = None
                    subtasks_count = len(task[block_key])
                    for i_subtask, subtask in enumerate(task[block_key]):
                        lc = subtask.lc
                        if lc.line == linenumber_0:
                            return [i_task, block_key, i_subtask]
                        elif (
                            i_subtask > 0 and prev_subtask_line < linenumber_0 < lc.line
                        ):
                            # part of previous subtask
                            return [i_task, block_key, i_subtask - 1]
                        # The previous subtask check can't catch the last task,
                        # so, handle the last task separately.
                        elif (
                            i_subtask + 1 == subtasks_count  # last subtask
                            and linenumber_0 > lc.line
                            and (
                                next_play_keyword_line is None
                                or linenumber_0 < next_play_keyword_line
                            )
                            and (
                                next_task_line is None or linenumber_0 < next_task_line
                            )
                            and (last_line_0 is None or linenumber_0 <= last_line_0)
                        ):
                            # part of this (last) subtask
                            return [i_task, block_key, i_subtask]
                        prev_subtask_line = lc.line

            # The previous task check (above) can't catch the last task,
            # so, handle the last task separately (also after subtask checks).
            if (
                i_task + 1 == tasks_count
                and linenumber_0 > lc.line
                and (next_task_line is None or linenumber_0 < next_task_line)
                and (last_line_0 is None or linenumber_0 <= last_line_0)
            ):
                # part of this (last) task
                return [i_task]
            prev_task_line = task.lc.line
        return []

    def _final_yaml_transform(self, text: str) -> str:
        """
        This ensures that top-level sequences are not over-indented.

        In order to make that work, we cannot delegate adding the yaml explict_start
        to ruamel.yaml or dedent() won't have anything to work with.
        Instead, we add the explicit_start here.
        """
        text_lines = text.splitlines(keepends=True)
        dedented_lines = dedent(text).splitlines(keepends=True)

        # preserve the indents for comment lines (do not dedent them)
        for i, line in enumerate(text_lines):
            if _comment_line_re.match(line):
                dedented_lines[i] = line

        text = "".join(dedented_lines)
        if self.explicit_start:
            text = "---\n" + text
        return text
