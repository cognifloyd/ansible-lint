"""Rule that flags Jinja2 tests used as filters."""

import os
import re
import sys
from pathlib import Path
from typing import List, MutableMapping, Optional, Pattern, Union, cast

import ansible.plugins.test.core
import ansible.plugins.test.files
import ansible.plugins.test.mathstuff
from ansible.template import Templar
from jinja2 import nodes
from jinja2.environment import Environment
from jinja2.visitor import NodeTransformer
from ruamel.yaml.comments import CommentedMap, CommentedSeq

import ansiblelint.skip_utils
import ansiblelint.utils
from ansiblelint.errors import MatchError
from ansiblelint.file_utils import Lintable
from ansiblelint.rules import AnsibleLintRule, TransformMixin
from ansiblelint.transform_utils import dump
from ansiblelint.utils import LINE_NUMBER_KEY, ansible_templar

# inspired by https://github.com/ansible/ansible/blob/devel/hacking/fix_test_syntax.py
_ansible_tests: List[str] = (
    list(ansible.plugins.test.core.TestModule().tests().keys())
    + list(ansible.plugins.test.files.TestModule().tests().keys())
    + list(ansible.plugins.test.mathstuff.TestModule().tests().keys())
)
_tests_as_filters_re: Pattern[str] = re.compile(
    r"\s*\|\s*" + f"({'|'.join(_ansible_tests)})" + r"\b"
)


class FilterNodeTransformer(NodeTransformer):

    # from https://github.com/ansible/ansible/blob/devel/hacking/fix_test_syntax.py
    ansible_test_map = {
        'version_compare': 'version',
        'is_dir': 'directory',
        'is_file': 'file',
        'is_link': 'link',
        'is_abs': 'abs',
        'is_same_file': 'same_file',
        'is_mount': 'mount',
        'issubset': 'subset',
        'issuperset': 'superset',
        'isnan': 'nan',
        'succeeded': 'successful',
        'success': 'successful',
        'change': 'changed',
        'skip': 'skipped',
    }

    def visit_Filter(self, node: nodes.Filter) -> Optional[nodes.Node]:
        if node.name not in _ansible_tests:
            return self.generic_visit(node)

        test_name = self.ansible_test_map.get(node.name, node.name)
        # fields = ("node", "name", "args", "kwargs", "dyn_args", "dyn_kwargs")
        test_node = nodes.Test(
            node.node,
            test_name,
            node.args,
            node.kwargs,
            node.dyn_args,
            node.dyn_kwargs,
        )
        return self.generic_visit(test_node)


class JinjaTestsAsFilters(AnsibleLintRule, TransformMixin):

    id = "jinja-tests-as-filters"
    shortdesc = "Using tests as filters is deprecated."
    description = """
Using tests as filters is deprecated.

Instead of using ``result|failed`` use ``result is failed``.

Deprecated in Ansible 2.5; Removed in Ansible 2.9.
see: https://github.com/ansible/proposals/issues/83
"""
    severity = "VERY_HIGH"
    tags = ["deprecations", "experimental"]
    version_added = "5.3"

    # for raw jinja templates (not yaml) we only need to reformat for one match.
    # keep a list of files so we can skip them.
    _files_fixed: List[Path] = []

    def _uses_test_as_filter(self, value: str) -> bool:
        matches = _tests_as_filters_re.search(value)
        return bool(matches)

    def matchyaml(self, file: Lintable) -> List[MatchError]:
        matches: List[MatchError] = []
        if str(file.base_kind) != 'text/yaml':
            return matches

        yaml = ansiblelint.utils.parse_yaml_linenumbers(file)
        if not yaml or (isinstance(yaml, str) and yaml.startswith('$ANSIBLE_VAULT')):
            return matches

        # If we need to let people disable this rule, then we'll need to enable this.
        # yaml = ansiblelint.skip_utils.append_skipped_rules(yaml, file)

        templar = ansiblelint.utils.ansible_templar(str(file.path.parent), {})

        linenumber = 1
        # skip_path = []
        for key, value, parent_path in ansiblelint.utils.nested_items_path(yaml):
            # if key == "skipped_rules":
            #     skip_path = parent_path + [key]
            #     continue
            # elif skip_path and parent_path == skip_path:
            #     continue

            # we can only get the linenumber from the most recent dictionary.
            if isinstance(value, MutableMapping):
                linenumber = value.get(LINE_NUMBER_KEY, linenumber)

            # We handle looping through lists/dicts to get parent_path.
            # So, only strings can be Jinja2 templates.
            if not isinstance(value, str) or (
                isinstance(key, str) and key.startswith("__") and key.endswith("__")
            ):
                continue
            yaml_path = parent_path + [key]
            do_wrap_template = "when" in yaml_path or (
                isinstance(key, str) and key.endswith("_when")
            )
            if not do_wrap_template and not templar.is_template(value):
                continue
            # We have a Jinja2 template string
            template = "{{" + value + "}}" if do_wrap_template else value
            if self._uses_test_as_filter(template):
                err = self.create_matcherror(
                    linenumber=linenumber,
                    details=value,
                    filename=file,
                )
                err.yaml_path = yaml_path
                matches.append(err)
        return matches

    def matchlines(self, file: "Lintable") -> List[MatchError]:
        """Match template lines."""
        matches: List[MatchError] = []
        # we handle yaml separately to handle things like when templates.
        if str(file.base_kind) != 'text/jinja2':
            return matches

        templar = ansiblelint.utils.ansible_templar(str(file.path.parent), {})

        if not templar.is_template(file.content):
            return matches

        matches = super().matchlines(file)
        return matches

    def match(self, line: str) -> Union[bool, str]:
        """Match template lines."""
        return self._uses_test_as_filter(line)

    def transform(
        self,
        match: MatchError,
        lintable: Lintable,
        data: Union[CommentedMap, CommentedSeq, str],
    ) -> None:
        """Transform data to fix the MatchError."""
        if lintable.path in self._files_fixed:
            # text/jinja2 template file was already reformatted. Nothing left to do.
            self._fixed(match)
            return

        basedir: str = os.path.abspath(os.path.dirname(str(lintable.path)))
        templar: Templar = ansible_templar(basedir, templatevars={})
        jinja_env: Environment = templar.environment

        target_key: Optional[Union[int, str]]
        target_parent: Optional[Union[CommentedMap, CommentedSeq]]
        target_template: str
        do_wrap_template = False

        if str(lintable.base_kind) == 'text/yaml':
            # the full yaml_path is to the string template.
            # we need the parent so we can modify it.
            target_key = match.yaml_path[-1]
            target_parent = cast(
                Union[CommentedMap, CommentedSeq],
                self._seek(match.yaml_path[:-1], data),
            )
            target_template = target_parent[target_key]
            do_wrap_template = "when" in match.yaml_path or (
                isinstance(match.yaml_path[-1], str)
                and match.yaml_path[-1].endswith("_when")
            )
            if do_wrap_template:
                target_template = "{{" + target_template + "}}"
        elif str(lintable.base_kind) == 'text/jinja2':
            target_parent = target_key = None
            target_template = cast(str, data)  # the whole file
        else:  # unknown file type
            return

        ast = jinja_env.parse(target_template)
        ast = FilterNodeTransformer().visit(ast)
        new_template = cast(str, dump(node=ast, environment=jinja_env))

        if target_parent is not None:
            if do_wrap_template:
                # remove "{{ " and " }}" (dump always adds space w/ braces)
                new_template = new_template[3:-3]
            target_parent[target_key] = new_template
        else:
            with open(lintable.path.resolve(), mode='w', encoding='utf-8') as f:
                f.write(new_template)
            self._files_fixed.append(lintable.path)

        self._fixed(match)


# testing code to be loaded only with pytest or when executed the rule file
if "pytest" in sys.modules:

    import pytest

    from ansiblelint.rules import RulesCollection  # pylint: disable=ungrouped-imports
    from ansiblelint.runner import Runner  # pylint: disable=ungrouped-imports

    @pytest.mark.parametrize(
        ("test_file", "failures"),
        (
            pytest.param(
                'examples/roles/role_for_jinja_tests_as_filters/tasks/fail.yml',
                19,
                id='tasks',
            ),
            pytest.param(
                'examples/roles/role_for_jinja_tests_as_filters/templates/sample.ini.j2',
                2,
                id='template',
            ),
        ),
    )
    def test_jinja_tests_as_filters_rule(
        default_rules_collection: RulesCollection, test_file: str, failures: int
    ) -> None:
        """Test rule matches."""
        results = Runner(test_file, rules=default_rules_collection).run()
        assert len(results) == failures
        for result in results:
            assert result.message == JinjaTestsAsFilters.shortdesc
