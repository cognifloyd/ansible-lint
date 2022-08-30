"""Tests for Jinja AST Annotator."""
from __future__ import annotations

from typing import Any, cast

import pytest
from jinja2 import nodes
from jinja2.environment import Environment
from jinja2.ext import Extension
from jinja2.visitor import NodeVisitor

from ansiblelint.jinja_utils.annotator import _AnnotatedNode, annotate

from .jinja_fixtures import (
    CoreTagsFixtures,
    ExtendedAPIFixtures,
    ExtensionsFixtures,
    FilterFixtures,
    ImportsFixtures,
    IncludesFixtures,
    InheritanceFixtures,
    JinjaTestsFixtures,
    LexerFixtures,
    SyntaxFixtures,
    TrimBlocksFixtures,
)


@pytest.mark.parametrize(
    ("template_source", "extensions"),
    (
        # spell-checker: disable
        ("{{ [{'nested': ({'dict': [('tuple',), ()]}, {})}, {}] }}", ()),
        ("{{ ['slice', 'test', 1, 2, 3][1:3:-1] }}", ()),
        ("{{ ['slice', 'test', 1, 2, 3][2:] }}", ()),
        # these use fixtures from Jinja's test suite:
        (ExtendedAPIFixtures.item_and_attribute_1, ()),
        (ExtendedAPIFixtures.item_and_attribute_2, ()),
        (ExtendedAPIFixtures.item_and_attribute_3, ()),
        (CoreTagsFixtures.awaitable_property_slicing, ()),
        (CoreTagsFixtures.simple_for, ()),
        (CoreTagsFixtures.for_else, ()),
        (CoreTagsFixtures.for_else_scoping_item, ()),
        (CoreTagsFixtures.for_empty_blocks, ()),
        (CoreTagsFixtures.for_context_vars, ()),
        (CoreTagsFixtures.for_cycling, ()),
        (CoreTagsFixtures.for_lookaround, ()),
        (CoreTagsFixtures.for_changed, ()),
        (CoreTagsFixtures.for_scope, ()),
        (CoreTagsFixtures.for_varlen, ()),
        (CoreTagsFixtures.for_recursive, ()),
        (CoreTagsFixtures.for_recursive_lookaround, ()),
        (CoreTagsFixtures.for_recursive_depth0, ()),
        (CoreTagsFixtures.for_recursive_depth, ()),
        (CoreTagsFixtures.for_looploop, ()),
        (CoreTagsFixtures.for_reversed_bug, ()),
        (CoreTagsFixtures.for_loop_errors, ()),
        (CoreTagsFixtures.for_loop_filter_1, ()),
        (CoreTagsFixtures.for_loop_filter_2, ()),
        (CoreTagsFixtures.for_scoped_special_var, ()),
        (CoreTagsFixtures.for_scoped_loop_var_1, ()),
        (CoreTagsFixtures.for_scoped_loop_var_2, ()),
        (CoreTagsFixtures.for_recursive_empty_loop_iter, ()),
        (CoreTagsFixtures.for_call_in_loop, ()),
        (CoreTagsFixtures.for_scoping_bug, ()),
        (CoreTagsFixtures.for_unpacking, ()),
        (CoreTagsFixtures.for_intended_scoping_with_set_1, ()),
        (CoreTagsFixtures.for_intended_scoping_with_set_2, ()),
        (CoreTagsFixtures.simple_if, ()),
        (CoreTagsFixtures.if_elif, ()),
        (CoreTagsFixtures.if_elif_deep, ()),
        (CoreTagsFixtures.if_else, ()),
        (CoreTagsFixtures.if_empty, ()),
        (CoreTagsFixtures.if_complete, ()),
        (CoreTagsFixtures.if_no_scope_1, ()),
        (CoreTagsFixtures.if_no_scope_2, ()),
        (CoreTagsFixtures.simple_macros, ()),
        (CoreTagsFixtures.macros_scoping, ()),
        (CoreTagsFixtures.macros_arguments, ()),
        (CoreTagsFixtures.macros_varargs, ()),
        (CoreTagsFixtures.macros_simple_call, ()),
        (CoreTagsFixtures.macros_complex_call, ()),
        (CoreTagsFixtures.macros_caller_undefined, ()),
        (CoreTagsFixtures.macros_include, ()),
        (CoreTagsFixtures.macros_macro_api, ()),
        (CoreTagsFixtures.macros_callself, ()),
        (CoreTagsFixtures.macros_macro_defaults_self_ref, ()),
        (CoreTagsFixtures.set_normal, ()),
        (CoreTagsFixtures.set_block, ()),
        (CoreTagsFixtures.set_block_escaping, ()),
        (CoreTagsFixtures.set_namespace, ()),
        (CoreTagsFixtures.set_namespace_block, ()),
        (CoreTagsFixtures.set_init_namespace, ()),
        (CoreTagsFixtures.set_namespace_loop, ()),
        (CoreTagsFixtures.set_namespace_macro, ()),
        (CoreTagsFixtures.set_block_escaping_filtered, ()),
        (CoreTagsFixtures.set_block_filtered, ()),
        (CoreTagsFixtures.with_with, ()),
        (CoreTagsFixtures.with_with_argument_scoping, ()),
        (FilterFixtures.capitalize, ()),
        (FilterFixtures.center, ()),
        (FilterFixtures.default, ()),
        (FilterFixtures.dictsort_1, ()),
        (FilterFixtures.dictsort_2, ()),
        (FilterFixtures.dictsort_3, ()),
        (FilterFixtures.dictsort_4, ()),
        (FilterFixtures.batch, ()),
        (FilterFixtures.slice_, ()),
        (FilterFixtures.escape, ()),
        (FilterFixtures.trim, ()),
        (FilterFixtures.striptags, ()),
        (FilterFixtures.filesizeformat, ()),
        (FilterFixtures.filesizeformat_issue59, ()),
        (FilterFixtures.first, ()),
        (FilterFixtures.float_, ()),
        (FilterFixtures.float_default, ()),
        (FilterFixtures.format_, ()),
        (FilterFixtures.indent_1, ()),
        (FilterFixtures.indent_2, ()),
        (FilterFixtures.indent_3, ()),
        (FilterFixtures.indent_4, ()),
        (FilterFixtures.indent_5, ()),
        (FilterFixtures.indent_6, ()),
        (FilterFixtures.indent_7, ()),
        (FilterFixtures.indent_width_string, ()),
        (FilterFixtures.int_, ()),
        (FilterFixtures.int_base, ()),
        (FilterFixtures.int_default, ()),
        (FilterFixtures.join_1, ()),
        (FilterFixtures.join_2, ()),
        (FilterFixtures.join_attribute, ()),
        (FilterFixtures.last, ()),
        (FilterFixtures.length, ()),
        (FilterFixtures.lower, ()),
        (FilterFixtures.items, ()),
        (FilterFixtures.items_undefined, ()),
        (FilterFixtures.pprint, ()),
        (FilterFixtures.random, ()),
        (FilterFixtures.reverse, ()),
        (FilterFixtures.string, ()),
        (FilterFixtures.title_1, ()),
        (FilterFixtures.title_2, ()),
        (FilterFixtures.title_3, ()),
        (FilterFixtures.title_4, ()),
        (FilterFixtures.title_5, ()),
        (FilterFixtures.title_6, ()),
        (FilterFixtures.title_7, ()),
        (FilterFixtures.title_8, ()),
        (FilterFixtures.title_9, ()),
        (FilterFixtures.title_10, ()),
        (FilterFixtures.title_11, ()),
        (FilterFixtures.title_12, ()),
        (FilterFixtures.truncate, ()),
        (FilterFixtures.truncate_very_short, ()),
        (FilterFixtures.truncate_end_length, ()),
        (FilterFixtures.upper, ()),
        (FilterFixtures.urlize_1, ()),
        (FilterFixtures.urlize_2, ()),
        (FilterFixtures.urlize_3, ()),
        (FilterFixtures.urlize_4, ()),
        (FilterFixtures.urlize_rel_policy, ()),
        (FilterFixtures.urlize_target_parameters, ()),
        (FilterFixtures.urlize_extra_schemes_parameters, ()),
        (FilterFixtures.wordcount_1, ()),
        (FilterFixtures.wordcount_2, ()),
        (FilterFixtures.block, ()),
        (FilterFixtures.chaining, ()),
        (FilterFixtures.sum_, ()),
        (FilterFixtures.sum_attributes, ()),
        (FilterFixtures.sum_attributes_nested, ()),
        (FilterFixtures.sum_attributes_tuple, ()),
        (FilterFixtures.abs_, ()),
        (FilterFixtures.round_positive, ()),
        (FilterFixtures.round_negative, ()),
        (FilterFixtures.xmlattr, ()),
        (FilterFixtures.sort1, ()),
        (FilterFixtures.sort2, ()),
        (FilterFixtures.sort3, ()),
        (FilterFixtures.sort4, ()),
        (FilterFixtures.sort5, ()),
        (FilterFixtures.sort6, ()),
        (FilterFixtures.sort7, ()),
        (FilterFixtures.sort8, ()),
        (FilterFixtures.unique, ()),
        (FilterFixtures.unique_case_sensitive, ()),
        (FilterFixtures.unique_attribute, ()),
        (FilterFixtures.min_1, ()),
        (FilterFixtures.min_2, ()),
        (FilterFixtures.min_3, ()),
        (FilterFixtures.max_1, ()),
        (FilterFixtures.max_2, ()),
        (FilterFixtures.max_3, ()),
        (FilterFixtures.min_attribute, ()),
        (FilterFixtures.max_attribute, ()),
        (FilterFixtures.groupby, ()),
        (FilterFixtures.groupby_tuple_index, ()),
        (FilterFixtures.groupby_multi_dot, ()),
        (FilterFixtures.groupby_default, ()),
        (FilterFixtures.groupby_case, ()),
        (FilterFixtures.filter_tag, ()),
        (FilterFixtures.replace_1, ()),
        (FilterFixtures.replace_2, ()),
        (FilterFixtures.replace_3, ()),
        (FilterFixtures.forceescape, ()),
        (FilterFixtures.safe_1, ()),
        (FilterFixtures.safe_2, ()),
        (FilterFixtures.urlencode, ()),
        (FilterFixtures.simple_map, ()),
        (FilterFixtures.map_sum, ()),
        (FilterFixtures.attribute_map, ()),
        (FilterFixtures.empty_map, ()),
        (FilterFixtures.map_default, ()),
        (FilterFixtures.map_default_list, ()),
        (FilterFixtures.map_default_str, ()),
        (FilterFixtures.simple_select, ()),
        (FilterFixtures.bool_select, ()),
        (FilterFixtures.simple_reject, ()),
        (FilterFixtures.bool_reject, ()),
        (FilterFixtures.simple_select_attr, ()),
        (FilterFixtures.simple_reject_attr, ()),
        (FilterFixtures.func_select_attr, ()),
        (FilterFixtures.func_reject_attr, ()),
        (FilterFixtures.json_dump, ()),
        (FilterFixtures.wordwrap, ()),
        (FilterFixtures.filter_undefined, ()),
        (FilterFixtures.filter_undefined_in_if, ()),
        (FilterFixtures.filter_undefined_in_elif, ()),
        (FilterFixtures.filter_undefined_in_else, ()),
        (FilterFixtures.filter_undefined_in_nested_if, ()),
        (FilterFixtures.filter_undefined_in_condexpr_1, ()),
        (FilterFixtures.filter_undefined_in_condexpr_2, ()),
        (TrimBlocksFixtures.trim, ()),
        (TrimBlocksFixtures.no_trim, ()),
        (TrimBlocksFixtures.no_trim_outer, ()),
        (TrimBlocksFixtures.lstrip_no_trim, ()),
        (TrimBlocksFixtures.trim_blocks_false_with_no_trim_block1, ()),
        (TrimBlocksFixtures.trim_blocks_false_with_no_trim_block2, ()),
        (TrimBlocksFixtures.trim_blocks_false_with_no_trim_comment1, ()),
        (TrimBlocksFixtures.trim_blocks_false_with_no_trim_comment2, ()),
        (TrimBlocksFixtures.trim_blocks_false_with_no_trim_raw1, ()),
        (TrimBlocksFixtures.trim_blocks_false_with_no_trim_raw2, ()),
        (TrimBlocksFixtures.trim_nested, ()),
        (TrimBlocksFixtures.no_trim_nested, ()),
        (TrimBlocksFixtures.comment_trim, ()),
        (TrimBlocksFixtures.comment_no_trim, ()),
        (TrimBlocksFixtures.multiple_comment_trim_lstrip, ()),
        (TrimBlocksFixtures.multiple_comment_no_trim_lstrip, ()),
        (TrimBlocksFixtures.raw_trim_lstrip, ()),
        (TrimBlocksFixtures.raw_no_trim_lstrip, ()),
        (ImportsFixtures.context_imports_1, ()),
        (ImportsFixtures.context_imports_2, ()),
        (ImportsFixtures.context_imports_3, ()),
        (ImportsFixtures.context_imports_4, ()),
        (ImportsFixtures.context_imports_5, ()),
        (ImportsFixtures.context_imports_6, ()),
        (ImportsFixtures.import_needs_name_1, ()),
        (ImportsFixtures.import_needs_name_2, ()),
        (ImportsFixtures.trailing_comma_with_context_1, ()),
        (ImportsFixtures.trailing_comma_with_context_2, ()),
        (ImportsFixtures.trailing_comma_with_context_3, ()),
        (ImportsFixtures.trailing_comma_with_context_4, ()),
        (ImportsFixtures.trailing_comma_with_context_5, ()),
        (ImportsFixtures.exports, ()),
        (ImportsFixtures.import_with_globals, ()),
        (ImportsFixtures.import_with_globals_override, ()),
        (ImportsFixtures.from_import_with_globals, ()),
        (IncludesFixtures.context_include_1, ()),
        (IncludesFixtures.context_include_2, ()),
        (IncludesFixtures.context_include_3, ()),
        (IncludesFixtures.choice_includes_1, ()),
        (IncludesFixtures.choice_includes_2, ()),
        (IncludesFixtures.choice_includes_4, ()),
        (IncludesFixtures.choice_includes_5, ()),
        (IncludesFixtures.choice_includes_6, ()),
        (IncludesFixtures.choice_includes_7, ()),
        (IncludesFixtures.choice_includes_8, ()),
        (IncludesFixtures.include_ignoring_missing_2, ()),
        (IncludesFixtures.include_ignoring_missing_3, ()),
        (IncludesFixtures.include_ignoring_missing_4, ()),
        (IncludesFixtures.context_include_with_overrides_main, ()),
        (IncludesFixtures.context_include_with_overrides_item, ()),
        (IncludesFixtures.unoptimized_scopes, ()),
        (IncludesFixtures.import_from_with_context_a, ()),
        (IncludesFixtures.import_from_with_context, ()),
        (InheritanceFixtures.layout, ()),
        (InheritanceFixtures.level1, ()),
        (InheritanceFixtures.level2, ()),
        (InheritanceFixtures.level3, ()),
        (InheritanceFixtures.level4, ()),
        (InheritanceFixtures.working, ()),
        (InheritanceFixtures.double_e, ()),
        (InheritanceFixtures.super_a, ()),
        (InheritanceFixtures.super_b, ()),
        (InheritanceFixtures.super_c, ()),
        (InheritanceFixtures.reuse_blocks, ()),
        (InheritanceFixtures.preserve_blocks_a, ()),
        (InheritanceFixtures.preserve_blocks_b, ()),
        (InheritanceFixtures.dynamic_inheritance_default1, ()),
        (InheritanceFixtures.dynamic_inheritance_default2, ()),
        (InheritanceFixtures.dynamic_inheritance_child, ()),
        (InheritanceFixtures.multi_inheritance_default1, ()),
        (InheritanceFixtures.multi_inheritance_default2, ()),
        (InheritanceFixtures.multi_inheritance_child, ()),
        (InheritanceFixtures.scoped_block_default_html, ()),
        (InheritanceFixtures.scoped_block, ()),
        (InheritanceFixtures.super_in_scoped_block_default_html, ()),
        (InheritanceFixtures.super_in_scoped_block, ()),
        (InheritanceFixtures.scoped_block_after_inheritance_layout_html, ()),
        (InheritanceFixtures.scoped_block_after_inheritance_index_html, ()),
        (InheritanceFixtures.scoped_block_after_inheritance_helpers_html, ()),
        (InheritanceFixtures.level1_required_default, ()),
        (InheritanceFixtures.level1_required_level1, ()),
        (InheritanceFixtures.level2_required_default, ()),
        (InheritanceFixtures.level2_required_level1, ()),
        (InheritanceFixtures.level2_required_level2, ()),
        (InheritanceFixtures.level3_required_default, ()),
        (InheritanceFixtures.level3_required_level1, ()),
        (InheritanceFixtures.level3_required_level2, ()),
        (InheritanceFixtures.level3_required_level3, ()),
        (InheritanceFixtures.required_with_scope_default1, ()),
        (InheritanceFixtures.required_with_scope_child1, ()),
        # The annotator only supports 'autoescape', 'loopcontrols', and 'do' extensions
        (ExtensionsFixtures.extend_late, ()),
        (ExtensionsFixtures.loop_controls_1, ("jinja2.ext.loopcontrols",)),
        (ExtensionsFixtures.loop_controls_2, ("jinja2.ext.loopcontrols",)),
        (ExtensionsFixtures.do, ("jinja2.ext.do",)),
        (ExtensionsFixtures.auto_escape_scoped_setting_1, ()),
        (ExtensionsFixtures.auto_escape_scoped_setting_2, ()),
        (ExtensionsFixtures.auto_escape_nonvolatile_1, ()),
        (ExtensionsFixtures.auto_escape_nonvolatile_2, ()),
        (ExtensionsFixtures.auto_escape_volatile, ()),
        (ExtensionsFixtures.auto_escape_scoping, ()),
        (ExtensionsFixtures.auto_escape_volatile_scoping, ()),
        # The annotator does not support jinja extensions that do custom parsing
        # (ExtensionsFixtures.extension_nodes, (ExampleExtension,)),
        # (ExtensionsFixtures.contextreference_node_passes_context, (ExampleExtension,)),
        # (ExtensionsFixtures.contextreference_node_can_pass_locals, (DerivedExampleExtension,)),
        # (ExtensionsFixtures.preprocessor_extension, (PreprocessorExtension,)),
        # (ExtensionsFixtures.streamfilter_extension, (StreamFilterExtension)),
        # (ExtensionsFixtures.debug, ("jinja2.ext.debug",)),
        # (ExtensionsFixtures.scope, (ScopeExt)),
        # (ExtensionsFixtures.auto_escape_overlay_scopes, (MagicScopesExtension)),
        (LexerFixtures.raw1, ()),
        (LexerFixtures.raw2, ()),
        (LexerFixtures.raw3, ()),
        (LexerFixtures.raw4, ()),
        (LexerFixtures.bytefallback, ()),
        (LexerFixtures.lineno_with_strip, ()),
        (LexerFixtures.start_comment, ()),
        (SyntaxFixtures.slicing, ()),
        (SyntaxFixtures.attr, ()),
        (SyntaxFixtures.subscript, ()),
        (SyntaxFixtures.tuple_, ()),
        (SyntaxFixtures.math, ()),
        (SyntaxFixtures.div, ()),
        (SyntaxFixtures.unary, ()),
        (SyntaxFixtures.concat, ()),
        (SyntaxFixtures.compare_1, ()),
        (SyntaxFixtures.compare_2, ()),
        (SyntaxFixtures.compare_3, ()),
        (SyntaxFixtures.compare_4, ()),
        (SyntaxFixtures.compare_5, ()),
        (SyntaxFixtures.compare_6, ()),
        (SyntaxFixtures.compare_parens, ()),
        (SyntaxFixtures.compare_compound_1, ()),
        (SyntaxFixtures.compare_compound_2, ()),
        (SyntaxFixtures.compare_compound_3, ()),
        (SyntaxFixtures.compare_compound_4, ()),
        (SyntaxFixtures.compare_compound_5, ()),
        (SyntaxFixtures.compare_compound_6, ()),
        (SyntaxFixtures.inop, ()),
        (SyntaxFixtures.collection_literal_1, ()),
        (SyntaxFixtures.collection_literal_2, ()),
        (SyntaxFixtures.collection_literal_3, ()),
        (SyntaxFixtures.numeric_literal_1, ()),
        (SyntaxFixtures.numeric_literal_2, ()),
        (SyntaxFixtures.numeric_literal_3, ()),
        (SyntaxFixtures.numeric_literal_4, ()),
        (SyntaxFixtures.numeric_literal_5, ()),
        (SyntaxFixtures.numeric_literal_6, ()),
        (SyntaxFixtures.numeric_literal_7, ()),
        (SyntaxFixtures.numeric_literal_8, ()),
        (SyntaxFixtures.numeric_literal_9, ()),
        (SyntaxFixtures.numeric_literal_10, ()),
        (SyntaxFixtures.numeric_literal_11, ()),
        (SyntaxFixtures.numeric_literal_12, ()),
        (SyntaxFixtures.numeric_literal_13, ()),
        (SyntaxFixtures.numeric_literal_14, ()),
        (SyntaxFixtures.numeric_literal_15, ()),
        (SyntaxFixtures.numeric_literal_16, ()),
        (SyntaxFixtures.numeric_literal_17, ()),
        (SyntaxFixtures.numeric_literal_18, ()),
        (SyntaxFixtures.numeric_literal_19, ()),
        (SyntaxFixtures.boolean, ()),
        (SyntaxFixtures.grouping, ()),
        (SyntaxFixtures.django_attr, ()),
        (SyntaxFixtures.conditional_expression, ()),
        (SyntaxFixtures.short_conditional_expression, ()),
        (SyntaxFixtures.filter_priority, ()),
        (SyntaxFixtures.function_calls_1, ()),
        (SyntaxFixtures.function_calls_2, ()),
        (SyntaxFixtures.function_calls_3, ()),
        (SyntaxFixtures.function_calls_4, ()),
        (SyntaxFixtures.function_calls_5, ()),
        (SyntaxFixtures.function_calls_6, ()),
        (SyntaxFixtures.function_calls_7, ()),
        (SyntaxFixtures.function_calls_8, ()),
        (SyntaxFixtures.function_calls_9, ()),
        (SyntaxFixtures.tuple_expr_1, ()),
        (SyntaxFixtures.tuple_expr_2, ()),
        (SyntaxFixtures.tuple_expr_3, ()),
        (SyntaxFixtures.tuple_expr_4, ()),
        (SyntaxFixtures.tuple_expr_5, ()),
        (SyntaxFixtures.tuple_expr_6, ()),
        (SyntaxFixtures.tuple_expr_7, ()),
        (SyntaxFixtures.tuple_expr_8, ()),
        (SyntaxFixtures.trailing_comma, ()),
        (SyntaxFixtures.block_end_name, ()),
        (SyntaxFixtures.constant_casing_true, ()),
        (SyntaxFixtures.constant_casing_false, ()),
        (SyntaxFixtures.constant_casing_none, ()),
        (SyntaxFixtures.chaining_tests, ()),
        (SyntaxFixtures.string_concatenation, ()),
        (SyntaxFixtures.not_in, ()),
        (SyntaxFixtures.operator_precedence, ()),
        (SyntaxFixtures.raw2, ()),
        (SyntaxFixtures.const, ()),
        (SyntaxFixtures.neg_filter_priority, ()),
        (SyntaxFixtures.localset, ()),
        (SyntaxFixtures.parse_unary_1, ()),
        (SyntaxFixtures.parse_unary_2, ()),
        (JinjaTestsFixtures.defined, ()),
        (JinjaTestsFixtures.even, ()),
        (JinjaTestsFixtures.odd, ()),
        (JinjaTestsFixtures.lower, ()),
        (JinjaTestsFixtures.upper, ()),
        (JinjaTestsFixtures.equalto, ()),
        (JinjaTestsFixtures.sameas, ()),
        (JinjaTestsFixtures.no_paren_for_arg1, ()),
        (JinjaTestsFixtures.escaped, ()),
        (JinjaTestsFixtures.greaterthan, ()),
        (JinjaTestsFixtures.lessthan, ()),
        (JinjaTestsFixtures.multiple_tests, ()),
        (JinjaTestsFixtures.in_, ()),
        (JinjaTestsFixtures.name_undefined, ()),
        (JinjaTestsFixtures.name_undefined_in_if, ()),
    )
    + tuple(
        ("{{ " + type_test[0] + " }}", ()) for type_test in JinjaTestsFixtures.types
    )
    + tuple(
        ("{{ " + alias_test[0] + " }}", ())
        for alias_test in JinjaTestsFixtures.compare_aliases
    ),
    # spell-checker: enable
)
def test_annotate(
    jinja_env: Environment,
    template_source: str,
    extensions: tuple[str | type[Extension]],
) -> None:
    """Validate sanity of annotated token details on Jinja2 AST."""
    for extension in extensions:
        jinja_env.add_extension(extension)

    ast = jinja_env.parse(template_source)
    annotate(ast, jinja_env, raw_template=template_source)

    class TestVisitor(NodeVisitor):
        """Recursive iterator to visit and test each node in a Jinja2 AST tree."""

        def generic_visit(self, node: _AnnotatedNode, *args: Any, **kwargs: Any) -> Any:
            """Visit all nodes while tracking parent node."""
            for child_node in cast(nodes.Node, node).iter_child_nodes():
                kwargs["parent"] = node
                self.visit(child_node, *args, **kwargs)

        def visit(self, node: _AnnotatedNode, *args: Any, **kwargs: Any) -> None:
            """Test AST node to ensure it is sane and fits within the parent node."""
            # Make it easier to identify which node had failures in the future
            assert hasattr(node, "tokens_slice")
            assert isinstance(node.tokens_slice, tuple)
            assert len(node.tokens_slice) == 2
            assert all(isinstance(index, int) for index in node.tokens_slice)
            assert node.tokens_slice[0] < node.tokens_slice[1]
            assert hasattr(node, "tokens")
            assert node.tokens_slice[0] == node.tokens[0].index
            assert node.tokens_slice[1] == node.tokens[-1].index + 1
            assert node.tokens_slice[1] - node.tokens_slice[0] == len(node.tokens)
            if "parent" in kwargs:
                # only the root node will not have a parent arg.
                parent: _AnnotatedNode = kwargs["parent"]
                assert hasattr(node, "parent")
                assert node.parent == parent

                assert hasattr(parent, "tokens_slice")
                assert isinstance(parent.tokens_slice, tuple)
                assert parent.tokens_slice[0] <= node.tokens_slice[0]
                assert node.tokens_slice[1] <= parent.tokens_slice[1]
                assert hasattr(parent, "tokens")
                assert parent.tokens_slice[0] == parent.tokens[0].index
                assert parent.tokens_slice[1] == parent.tokens[-1].index + 1
                assert parent.tokens_slice[1] - parent.tokens_slice[0] == len(
                    parent.tokens
                )
            super().visit(cast(nodes.Node, node), *args, **kwargs)

    TestVisitor().visit(cast(_AnnotatedNode, ast))
