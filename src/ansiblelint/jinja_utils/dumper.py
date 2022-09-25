"""Jinja template/expression dumper utils for transforms."""
from __future__ import annotations

from contextlib import contextmanager
from io import StringIO
from typing import Iterator, List, TextIO, cast

from jinja2 import lexer as j2tokens
from jinja2 import nodes
from jinja2.compiler import operators
from jinja2.environment import Environment
from jinja2.visitor import NodeVisitor

from .annotator import _AnnotatedNode
from .line_wrapper import LineWrapper
from .token import (
    BLOCK_PAIR_PRIORITY,
    COMMA_PRIORITY,
    COMPARATOR_PRIORITY,
    DOT_PRIORITY,
    EXPR_PAIR_PRIORITY,
    FILTER_PRIORITY,
    LOGIC_PRIORITY,
    MATH_PRIORITIES,
    SPACE,
    STRING_PRIORITY,
    TERNARY_PRIORITY,
    TEST_PRIORITY,
    Token,
    TokenStream,
)


def dump(
    node: nodes.Template,
    environment: Environment,
    max_line_length: int,
    # in YAML, first line can be shorter than subsequent lines.
    max_first_line_length: int | None = None,
    stream: TextIO | None = None,
) -> str | None:
    """Dump a jinja2 ast back into a jinja2 template.

    This is based on jinja2.compiler.generate
    """
    if not isinstance(node, nodes.Template):
        raise TypeError("Can't dump non template nodes")

    tokens = TokenStream(
        max_line_length=max_line_length,
        max_first_line_length=max_first_line_length,
    )

    dumper = TemplateDumper(
        environment=environment,
        token_stream=tokens,
    )
    dumper.visit(node)

    line_wrapper = LineWrapper()
    try:
        # see if it can fit on one line
        line_wrapper.stringify(
            tokens.tokens, max_lines=1, max_length=max_first_line_length
        )
    except ValueError:
        # needs multiple lines
        line_wrapper.process(tokens)

    as_string = False
    if stream is None:
        stream = StringIO()
        as_string = True

    stream.write(str(tokens))

    if as_string:
        stream = cast(StringIO, stream)
        return stream.getvalue()

    return None


# Ignore these because they're required by Jinja2's NodeVisitor interface
# pylint: disable=too-many-public-methods,invalid-name
class TemplateDumper(NodeVisitor):
    """Dump a jinja2 AST back into a jinja2 template tokens stream.

    This facilitates AST-based template modification.
    This is based on jinja2.compiler.CodeGenerator
    """

    def __init__(
        self,
        environment: Environment,
        token_stream: TokenStream,
    ):
        """Create a TemplateDumper."""
        self.environment = environment
        self.tokens = token_stream

    # -- Various compilation helpers

    @contextmanager
    def token_pair_block(
        self, node: nodes.Node, *names: str, tag_index: int = 0
    ) -> Iterator[None]:
        """Wrap context with block {% %} tokens."""
        start_string = self.environment.block_start_string
        end_string = self.environment.block_end_string
        start_chomp = end_chomp = ""

        # preserve chomped values
        if hasattr(node, "token_pairs"):
            _node = cast(_AnnotatedNode, node)
            if len(_node.token_pairs) > tag_index:
                # the outermost pair should be {{ }}
                pair_opener = _node.token_pairs[tag_index]
                pair_closer = cast(Token, pair_opener.pair)
                if pair_opener.chomp:
                    start_string = pair_opener.value_str
                    start_chomp = pair_opener.chomp
                if pair_closer.chomp or pair_closer.value_str.endswith("\n"):
                    end_string = pair_closer.value_str
                    end_chomp = pair_closer.chomp

        with self.tokens.pair(
            (j2tokens.TOKEN_BLOCK_BEGIN, start_string, start_chomp, 0),
            (j2tokens.TOKEN_BLOCK_END, end_string, end_chomp, 0),
        ):
            with self.tokens.pair(
                (j2tokens.TOKEN_WHITESPACE, SPACE, "", BLOCK_PAIR_PRIORITY),
                (j2tokens.TOKEN_WHITESPACE, SPACE, "", BLOCK_PAIR_PRIORITY),
            ):
                for name in names:
                    self.tokens.extend(
                        (j2tokens.TOKEN_WHITESPACE, SPACE),
                        (j2tokens.TOKEN_NAME, name),
                        (j2tokens.TOKEN_WHITESPACE, SPACE),
                    )
                yield

    @contextmanager
    def token_pair_variable(self, node: nodes.Node) -> Iterator[None]:
        """Wrap context with variable {{ }} tokens."""
        start_string = self.environment.variable_start_string
        end_string = self.environment.variable_end_string
        start_chomp = end_chomp = ""

        # preserve chomped values
        if hasattr(node, "token_pairs"):
            # the outermost pair should be {{ }}
            pair_opener = cast(_AnnotatedNode, node).token_pairs[0]
            pair_closer = cast(Token, pair_opener.pair)
            if pair_opener.chomp:
                start_string = pair_opener.value_str
                start_chomp = pair_opener.chomp
            if pair_closer.chomp or pair_closer.value_str.endswith("\n"):
                end_string = pair_closer.value_str
                end_chomp = pair_closer.chomp

        with self.tokens.pair(
            (j2tokens.TOKEN_VARIABLE_BEGIN, start_string, start_chomp, 0),
            (j2tokens.TOKEN_VARIABLE_END, end_string, end_chomp, 0),
        ):
            with self.tokens.pair(
                (j2tokens.TOKEN_WHITESPACE, SPACE, "", BLOCK_PAIR_PRIORITY),
                (j2tokens.TOKEN_WHITESPACE, SPACE, "", BLOCK_PAIR_PRIORITY),
            ):
                yield

    def token_pair_paren(self, explicit: bool = True) -> Iterator[None]:
        """Wrap context with a pair of () tokens."""
        with self.tokens.pair(
            (j2tokens.TOKEN_LPAREN, "(" if explicit else "", "", 0),
            (j2tokens.TOKEN_RPAREN, ")" if explicit else "", "", 0),
        ):
            with self.tokens.pair(
                # possible newline, but no space otherwise
                (j2tokens.TOKEN_WHITESPACE, "", "", EXPR_PAIR_PRIORITY),
                (j2tokens.TOKEN_WHITESPACE, "", "", EXPR_PAIR_PRIORITY),
            ):
                yield

    def token_pair_bracket(self) -> Iterator[None]:
        """Wrap context with a pair of [] tokens."""
        with self.tokens.pair(
            (j2tokens.TOKEN_LBRACKET, "[", "", 0),
            (j2tokens.TOKEN_RBRACKET, "]", "", 0),
        ):
            with self.tokens.pair(
                # possible newline, but no space otherwise
                (j2tokens.TOKEN_WHITESPACE, "", "", EXPR_PAIR_PRIORITY),
                (j2tokens.TOKEN_WHITESPACE, "", "", EXPR_PAIR_PRIORITY),
            ):
                yield

    def token_pair_brace(self) -> Iterator[None]:
        """Wrap context with a pair of {} tokens."""
        with self.tokens.pair(
            (j2tokens.TOKEN_LBRACE, "{", "", 0),
            (j2tokens.TOKEN_RBRACE, "}", "", 0),
        ):
            with self.tokens.pair(
                # possible newline, but no space otherwise
                (j2tokens.TOKEN_WHITESPACE, "", "", EXPR_PAIR_PRIORITY),
                (j2tokens.TOKEN_WHITESPACE, "", "", EXPR_PAIR_PRIORITY),
            ):
                yield

    def signature(
        self,
        node: nodes.Call | nodes.Filter | nodes.Test,
    ) -> None:
        """Write a function call to the stream for the current node."""
        first = True
        arg: nodes.Expr
        for arg in node.args:
            if first:
                first = False
            else:
                self.tokens.extend(
                    (j2tokens.TOKEN_COMMA, ","),
                    (j2tokens.TOKEN_WHITESPACE, SPACE, COMMA_PRIORITY),
                )
            self.visit(arg)
        # cast because typehint is incorrect on nodes._FilterTestCommon
        for kwarg in cast(List[nodes.Keyword], node.kwargs):
            if first:
                first = False
            else:
                self.tokens.extend(
                    (j2tokens.TOKEN_COMMA, ","),
                    (j2tokens.TOKEN_WHITESPACE, SPACE, COMMA_PRIORITY),
                )
            self.visit(kwarg)
        if node.dyn_args:
            if first:
                first = False
                self.tokens.append(j2tokens.TOKEN_MUL, "*")
                # must not append SPACE after this *
            else:
                self.tokens.extend(
                    (j2tokens.TOKEN_COMMA, ","),
                    (j2tokens.TOKEN_WHITESPACE, SPACE, COMMA_PRIORITY),
                    (j2tokens.TOKEN_MUL, "*"),
                )
                # must not append SPACE after this *
            self.visit(node.dyn_args)
        if node.dyn_kwargs is not None:
            if first:
                self.tokens.append(j2tokens.TOKEN_POW, "**")
                # must not append SPACE after this **
            else:
                self.tokens.extend(
                    (j2tokens.TOKEN_COMMA, ","),
                    (j2tokens.TOKEN_WHITESPACE, SPACE, COMMA_PRIORITY),
                    (j2tokens.TOKEN_POW, "**"),
                )
                # must not append SPACE after this **
            self.visit(node.dyn_kwargs)

    def macro_signature(
        self,
        node: nodes.Macro | nodes.CallBlock,
    ) -> None:
        """Write a Macro or CallBlock signature to the stream for the current node."""
        with self.token_pair_paren():
            for idx, arg in enumerate(node.args):
                if idx:
                    self.tokens.extend(
                        (j2tokens.TOKEN_COMMA, ","),
                        (j2tokens.TOKEN_WHITESPACE, SPACE, COMMA_PRIORITY),
                    )
                self.visit(arg)
                try:
                    default = node.defaults[idx - len(node.args)]
                except IndexError:
                    continue
                self.tokens.extend(
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                    (j2tokens.TOKEN_ASSIGN, "="),
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                )
                self.visit(default)

    # -- Statement Visitors

    def visit_Template(self, node: nodes.Template) -> None:
        """Template is the root node.

        Ensure that multiline templates end with a newline.
        Single line templates are probably simple expressions.
        """
        # TODO: write/preserve whitespace and comments at start
        self.generic_visit(node)
        # if not self.environment.keep_trailing_newline
        # if self.tokens.line_number > 1 and self.tokens.line_position != 0:
        #     self.tokens.append(j2tokens.TOKEN_WHITESPACE, "\n")
        # TODO: write/preserve whitespace and comments at end

    def visit_Output(self, node: nodes.Template) -> None:
        """Write an ``Output`` node to the stream.

        Output is a ``{{ }}`` statement (aka ``print`` or output statement).
        """
        for child_node in node.iter_child_nodes():
            # child_node might be TemplateData which is outside {{ }}
            if isinstance(child_node, nodes.TemplateData):
                self.visit(child_node)
                continue

            # child_node is one of the expression nodes surrounded by {{ }}
            with self.token_pair_variable(child_node):
                self.visit(child_node)

    def visit_Block(self, node: nodes.Block) -> None:
        """Write a ``Block`` to the stream.

        Examples::

            {% block name %}block{% endblock %}
            {% block name scoped %}block{% endblock %}
            {% block name scoped required %}block{% endblock %}
            {% block name required %}block{% endblock %}
        """
        block_name_tokens: list[str] = ["block", node.name]
        if node.scoped:
            block_name_tokens.append("scoped")
        if node.required:
            block_name_tokens.append("required")
        with self.token_pair_block(node, *block_name_tokens, tag_index=0):
            pass
        for child_node in node.body:
            self.visit(child_node)
        with self.token_pair_block(node, "endblock", tag_index=1):
            pass

    def visit_Extends(self, node: nodes.Extends) -> None:
        """Write an ``Extends`` block to the stream.

        Example::

            {% extends name %}
        """
        with self.token_pair_block(node, "extends"):
            self.visit(node.template)

    def visit_Include(self, node: nodes.Include) -> None:
        """Write an ``Include`` block to the stream.

        Examples::

            {% include name %}
            {% include name ignore missing %}
            {% include name ignore missing without context %}
            {% include name without context %}
        """
        with self.token_pair_block(node, "include"):
            self.visit(node.template)
            if node.ignore_missing:
                self.tokens.extend(
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                    # one token to prevent line breaks
                    (j2tokens.TOKEN_NAME, "ignore missing"),
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                )
            # include defaults to "with context" so leave it off
            if not node.with_context:
                self.tokens.extend(
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                    # one token to prevent line breaks
                    (j2tokens.TOKEN_NAME, "without context"),
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                )

    def visit_Import(self, node: nodes.Import) -> None:
        """Write an ``Import`` block to the stream.

        Examples::

            {% import expr as name %}
            {% import expr as name without context %}
        """
        with self.token_pair_block(node, "import"):
            self.visit(node.template)
            self.tokens.extend(
                (j2tokens.TOKEN_WHITESPACE, SPACE),
                (j2tokens.TOKEN_NAME, "as"),
                (j2tokens.TOKEN_WHITESPACE, SPACE),
                (j2tokens.TOKEN_NAME, node.target),
                (j2tokens.TOKEN_WHITESPACE, SPACE),
            )
            # import defaults to "without context" so leave it off
            if node.with_context:
                self.tokens.extend(
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                    # one token to prevent line breaks
                    (j2tokens.TOKEN_NAME, "with context"),
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                )

    def visit_FromImport(self, node: nodes.FromImport) -> None:
        """Write a ``FromImport`` block to the stream.

        Examples::

            {% import expr as name %}
            {% import expr as name without context %}
        """
        with self.token_pair_block(node, "from"):
            self.visit(node.template)
            self.tokens.extend(
                (j2tokens.TOKEN_WHITESPACE, SPACE),
                (j2tokens.TOKEN_NAME, "import"),
                (j2tokens.TOKEN_WHITESPACE, SPACE),
            )
            for idx, name in enumerate(node.names):
                if idx:
                    self.tokens.extend(
                        (j2tokens.TOKEN_COMMA, ","),
                        (j2tokens.TOKEN_WHITESPACE, SPACE, COMMA_PRIORITY),
                    )
                if isinstance(name, tuple):
                    self.tokens.extend(
                        (j2tokens.TOKEN_NAME, name[0]),
                        (j2tokens.TOKEN_WHITESPACE, SPACE),
                        (j2tokens.TOKEN_NAME, "as"),
                        (j2tokens.TOKEN_WHITESPACE, SPACE),
                        (j2tokens.TOKEN_NAME, name[1]),
                    )
                else:  # str
                    self.tokens.append(j2tokens.TOKEN_NAME, name)
            # import defaults to "without context" so leave it off
            if node.with_context:
                self.tokens.extend(
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                    # one token to prevent line breaks
                    (j2tokens.TOKEN_NAME, "with context"),
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                )

    def visit_For(self, node: nodes.For) -> None:
        """Write a ``For`` block to the stream.

        Examples::

            {% for target in iter %}block{% endfor %}
            {% for target in iter recursive %}block{% endfor %}
            {% for target in iter %}block{% else %}block{% endfor %}
        """
        tag_index = 0
        with self.token_pair_block(node, "for", tag_index=tag_index):
            tag_index += 1
            self.visit(node.target)
            self.tokens.extend(
                (j2tokens.TOKEN_WHITESPACE, SPACE),
                (j2tokens.TOKEN_NAME, "in"),
                (j2tokens.TOKEN_WHITESPACE, SPACE),
            )
            self.visit(node.iter)
            if node.test is not None:
                self.tokens.extend(
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                    (j2tokens.TOKEN_NAME, "if"),
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                )
                self.visit(node.test)
            if node.recursive:
                self.tokens.extend(
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                    (j2tokens.TOKEN_NAME, "recursive"),
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                )
        for child_node in node.body:
            self.visit(child_node)
        if node.else_:
            with self.token_pair_block(node, "else", tag_index=tag_index):
                tag_index += 1
            for child_node in node.else_:
                self.visit(child_node)
        with self.token_pair_block(node, "endfor", tag_index=tag_index):
            pass

    def visit_If(self, node: nodes.If) -> None:
        """Write an ``If`` block to the stream."""
        tag_index = 0
        with self.token_pair_block(node, "if", tag_index=tag_index):
            tag_index += 1
            self.visit(node.test)
        for child_node in node.body:
            self.visit(child_node)
        for elif_node in node.elif_:
            self.visit_Elif(elif_node)
        if node.else_:
            with self.token_pair_block(node, "else", tag_index=tag_index):
                tag_index += 1
            for child_node in node.else_:
                self.visit(child_node)
        with self.token_pair_block(node, "endif", tag_index=tag_index):
            pass

    def visit_Elif(self, node: nodes.If) -> None:
        """Visit an ``If`` block that serves as an elif node in another ``If`` block."""
        with self.token_pair_block(node, "elif"):
            self.visit(node.test)
        for child_node in node.body:
            self.visit(child_node)

    def visit_With(self, node: nodes.With) -> None:
        """Write a ``With`` statement (manual scopes) to the stream."""
        with self.token_pair_block(node, "with", tag_index=0):
            first = True
            for target, expr in zip(node.targets, node.values):
                if first:
                    first = False
                else:
                    self.tokens.extend(
                        (j2tokens.TOKEN_COMMA, ","),
                        (j2tokens.TOKEN_WHITESPACE, SPACE, COMMA_PRIORITY),
                    )
                self.visit(target)
                self.tokens.extend(
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                    (j2tokens.TOKEN_ASSIGN, "="),
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                )
                self.visit(expr)
        for child_node in node.body:
            self.visit(child_node)
        with self.token_pair_block(node, "endwith", tag_index=1):
            pass

    def visit_ExprStmt(self, node: nodes.ExprStmt) -> None:
        """Write a ``do`` block to the stream.

        ExprStmtExtension
            A ``do`` tag is like a ``print`` statement but doesn't print the return value.
        ExprStmt
            A statement that evaluates an expression and discards the result.
        """
        with self.token_pair_block(node, "do"):
            self.visit(node.node)

    def visit_Assign(self, node: nodes.Assign) -> None:
        """Write an ``Assign`` statement to the stream.

        Example::

            {% set var = value %}
        """
        with self.token_pair_block(node, "set"):
            self.visit(node.target)
            self.tokens.extend(
                (j2tokens.TOKEN_WHITESPACE, SPACE),
                (j2tokens.TOKEN_ASSIGN, "="),
                (j2tokens.TOKEN_WHITESPACE, SPACE),
            )
            self.visit(node.node)

    # noinspection DuplicatedCode
    def visit_AssignBlock(self, node: nodes.AssignBlock) -> None:
        """Write an ``Assign`` block to the stream.

        Example::

            {% set var %}value{% endset %}
        """
        with self.token_pair_block(node, "set", tag_index=0):
            self.visit(node.target)
            if node.filter is not None:
                self.visit(node.filter)
        for child_node in node.body:
            self.visit(child_node)
        with self.token_pair_block(node, "endset", tag_index=1):
            pass

    # noinspection DuplicatedCode
    def visit_FilterBlock(self, node: nodes.FilterBlock) -> None:
        """Write a ``Filter`` block to the stream.

        Example::

            {% filter <filter> %}block{% endfilter %}
        """
        with self.token_pair_block(node, "filter", tag_index=0):
            self.visit(node.filter)
        for child_node in node.body:
            self.visit(child_node)
        with self.token_pair_block(node, "endfilter", tag_index=1):
            pass

    def visit_Macro(self, node: nodes.Macro) -> None:
        """Write a ``Macro`` definition block to the stream.

        Example::

            {% macro name(args/defaults) %}block{% endmacro %}
        """
        with self.token_pair_block(node, "macro", node.name):
            self.macro_signature(node)
        for child_node in node.body:
            self.visit(child_node)
        with self.token_pair_block(node, "endmacro"):
            pass

    def visit_CallBlock(self, node: nodes.CallBlock) -> None:
        """Write a macro ``Call`` block to the stream.

        Examples::

            {% call macro() %}block{% endcall %}
            {% call(args/defaults) macro() %}block{% endcall %}
        """
        with self.token_pair_block(node, "call"):
            if node.args:
                self.macro_signature(node)
            self.tokens.append(j2tokens.TOKEN_WHITESPACE, SPACE)
            self.visit(node.call)
        for child_node in node.body:
            self.visit(child_node)
        with self.token_pair_block(node, "endcall"):
            pass

    # -- Expression Visitors

    def visit_Name(self, node: nodes.Name) -> None:
        """Write a ``Name`` expression to the stream."""
        # ctx is one of: load, store, param
        # load named var, store named var, or store named function parameter
        self.tokens.append(j2tokens.TOKEN_NAME, node.name)

    def visit_NSRef(self, node: nodes.NSRef) -> None:
        """Write a ref to namespace value assignment to the stream."""
        self.tokens.extend(
            (j2tokens.TOKEN_NAME, node.name),
            (j2tokens.TOKEN_WHITESPACE, "", DOT_PRIORITY),
            (j2tokens.TOKEN_DOT, "."),
            (j2tokens.TOKEN_NAME, node.attr),
        )

    def visit_Const(self, node: nodes.Const) -> None:
        """Write a constant value (``int``, ``str``, etc) to the stream."""
        if node.value is None or isinstance(node.value, bool):
            self.tokens.append(j2tokens.TOKEN_NAME, repr(node.value).lower())
            return
        # We are using repr() here to handle quoting strings.
        self.tokens.append(j2tokens.TOKEN_NAME, repr(node.value))

    def visit_TemplateData(self, node: nodes.TemplateData) -> None:
        """Write a constant string (between Jinja blocks) to the stream."""
        self.tokens.append(j2tokens.TOKEN_DATA, node.data)

    def visit_Tuple(self, node: nodes.Tuple) -> None:
        """Write a ``Tuple`` to the stream."""
        # this not distinguish between node.ctx = load or node.ctx = store

        _node = cast(_AnnotatedNode, node)
        if hasattr(_node, "extras") and "explicit_parentheses" in _node.extras:
            # parentheses are optional in many contexts like "for <tuple> in ..."
            # this gets set by the Annotator based on inspecting the stream of tokens.
            explicit_parentheses = _node.extras["explicit_parentheses"]
        else:
            # If a Tuple node was added by a transform (after annotation),
            # it might not have extras. Just assume it needs parentheses.
            explicit_parentheses = True

        with self.token_pair_paren(explicit=explicit_parentheses):
            idx = -1
            for idx, item in enumerate(node.items):
                if idx:
                    self.tokens.extend(
                        (j2tokens.TOKEN_COMMA, ","),
                        (j2tokens.TOKEN_WHITESPACE, SPACE, COMMA_PRIORITY),
                    )
                self.visit(item)
            if idx == 0:
                self.tokens.extend(
                    (j2tokens.TOKEN_COMMA, ","),
                    (j2tokens.TOKEN_WHITESPACE, "", COMMA_PRIORITY),
                )

    def visit_List(self, node: nodes.List) -> None:
        """Write a ``List`` to the stream."""
        with self.token_pair_bracket():
            for idx, item in enumerate(node.items):
                if idx:
                    self.tokens.extend(
                        (j2tokens.TOKEN_COMMA, ","),
                        (j2tokens.TOKEN_WHITESPACE, SPACE, COMMA_PRIORITY),
                    )
                self.visit(item)

    def visit_Dict(self, node: nodes.Dict) -> None:
        """Write a ``Dict`` to the stream."""
        with self.token_pair_brace():
            item: nodes.Pair
            for idx, item in enumerate(node.items):
                if idx:
                    self.tokens.extend(
                        (j2tokens.TOKEN_COMMA, ","),
                        (j2tokens.TOKEN_WHITESPACE, SPACE, COMMA_PRIORITY),
                    )
                self.visit(item.key)
                self.tokens.extend(
                    (j2tokens.TOKEN_COLON, ":"),
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                )
                self.visit(item.value)

    def _visit_possible_binary_op(self, node: nodes.Expr) -> None:
        """Wrap binary_ops in parentheses if needed.

        This is not in _binary_op so that the outermost
        binary_op does not get wrapped in parentheses.
        """
        if isinstance(node, nodes.BinExpr):
            with self.token_pair_paren():
                self.visit(node)
        else:
            self.visit(node)

    def _binary_op(self, node: nodes.BinExpr) -> None:
        """Write a ``BinExpr`` (left and right op) to the stream."""
        self._visit_possible_binary_op(node.left)
        try:
            op_token = j2tokens.operators[node.operator]
        except KeyError:
            # op_token is "and" or "or"
            op_token = j2tokens.TOKEN_NAME
            priority = LOGIC_PRIORITY
        else:
            priority = MATH_PRIORITIES[op_token]
        self.tokens.extend(
            # if line is too long, only add newline before operators
            (j2tokens.TOKEN_WHITESPACE, SPACE, priority),
            (op_token, node.operator),
            (j2tokens.TOKEN_WHITESPACE, SPACE),  # no priority => no newline
        )
        self._visit_possible_binary_op(node.right)

    visit_Add = _binary_op
    visit_Sub = _binary_op
    visit_Mul = _binary_op
    visit_Div = _binary_op
    visit_FloorDiv = _binary_op
    visit_Pow = _binary_op
    visit_Mod = _binary_op
    visit_And = _binary_op
    visit_Or = _binary_op

    def _unary_op(self, node: nodes.UnaryExpr) -> None:
        """Write an ``UnaryExpr`` (one node with one op) to the stream."""
        self.tokens.extend(
            (j2tokens.TOKEN_WHITESPACE, SPACE),  # before unary => low newline priority
            (j2tokens.operators[node.operator], node.operator),
            # must not end in SPACE
        )
        self._visit_possible_binary_op(node.node)

    visit_Pos = _unary_op
    visit_Neg = _unary_op

    def visit_Not(self, node: nodes.Not) -> None:
        """Write a negated expression to the stream."""
        if isinstance(node.node, nodes.Test):
            return self.visit_Test(node.node, negate=True)

        # this is a unary operator
        self.tokens.extend(
            (j2tokens.TOKEN_WHITESPACE, SPACE),  # newline here would be odd
            (j2tokens.TOKEN_NAME, node.operator),  # "not"
            (j2tokens.TOKEN_WHITESPACE, SPACE),
        )
        return self._visit_possible_binary_op(node.node)

    def visit_Concat(self, node: nodes.Concat) -> None:
        """Write a string concatenation expression to the stream.

        The Concat operator ``~`` concatenates expressions
        after converting them to strings.
        """
        for idx, expr in enumerate(node.nodes):
            if idx:
                self.tokens.extend(
                    (j2tokens.TOKEN_WHITESPACE, SPACE, STRING_PRIORITY),
                    (j2tokens.TOKEN_TILDE, "~"),
                    (j2tokens.TOKEN_WHITESPACE, SPACE),
                )
            self.visit(expr)

    def visit_Compare(self, node: nodes.Compare) -> None:
        """Write a ``Compare`` operator to the stream."""
        self._visit_possible_binary_op(node.expr)
        # spell-checker:disable
        for operand in node.ops:
            # node.ops: List[Operand]
            # op.op: eq, ne, gt, gteq, lt, lteq, in, notin
            self.visit(operand)
        # spell-checker:enable

    def visit_Operand(self, node: nodes.Operand) -> None:
        """Write an ``Operand`` to the stream."""
        symbolic_op = operators[node.op]
        if symbolic_op in ("in", "not in"):
            # keeping "not in" as one token prevents line breaks between them
            op_token = j2tokens.TOKEN_NAME
        else:
            op_token = j2tokens.operators[symbolic_op]
        self.tokens.extend(
            (j2tokens.TOKEN_WHITESPACE, SPACE, COMPARATOR_PRIORITY),
            (op_token, symbolic_op),
            (j2tokens.TOKEN_WHITESPACE, SPACE),
        )
        self._visit_possible_binary_op(node.expr)

    def visit_Getattr(self, node: nodes.Getattr) -> None:
        """Write a ``Getattr`` expression to the stream."""
        # node.ctx is only ever "load" (which does not change how we write it)
        self.visit(node.node)
        if node.attr in []:  # TODO: which protected names?
            # if this is a protected name (like "items") use [] syntax
            with self.token_pair_bracket():
                self.tokens.append(j2tokens.TOKEN_NAME, repr(node.attr))
            return
        self.tokens.extend(
            (j2tokens.TOKEN_WHITESPACE, "", DOT_PRIORITY),
            (j2tokens.TOKEN_DOT, "."),
            (j2tokens.TOKEN_NAME, node.attr),
        )

    def visit_Getitem(self, node: nodes.Getitem) -> None:
        """Write a ``Getitem`` expression to the stream."""
        # node.ctx is only ever "load" (which does not change how we write it)
        self.visit(node.node)
        # using . and [] are mostly interchangeable. Prefer . for the simple case
        if isinstance(node.arg, nodes.Const) and isinstance(node.arg.value, int):
            self.tokens.extend(
                (j2tokens.TOKEN_WHITESPACE, "", DOT_PRIORITY),
                (j2tokens.TOKEN_DOT, "."),
                (j2tokens.TOKEN_NAME, str(node.arg.value)),
            )
            return
        with self.token_pair_bracket():
            self.visit(node.arg)

    def visit_Slice(self, node: nodes.Slice) -> None:
        """Write a ``Slice`` expression to the stream."""
        if node.start is not None:
            self.visit(node.start)
        self.tokens.append(j2tokens.TOKEN_COLON, ":")
        if node.stop is not None:
            self.visit(node.stop)
        if node.step is not None:
            self.tokens.append(j2tokens.TOKEN_COLON, ":")
            self.visit(node.step)

    def visit_Filter(self, node: nodes.Filter) -> None:
        """Write a Jinja ``Filter`` to the stream."""
        if node.node is not None:
            self.visit(node.node)
            self.tokens.extend(
                (j2tokens.TOKEN_WHITESPACE, SPACE, FILTER_PRIORITY),
                (j2tokens.TOKEN_PIPE, "|"),
                (j2tokens.TOKEN_WHITESPACE, SPACE),
            )
        self.tokens.append(j2tokens.TOKEN_NAME, node.name)
        if any((node.args, node.kwargs, node.dyn_args, node.dyn_kwargs)):
            with self.token_pair_paren():
                self.signature(node)

    def visit_Test(self, node: nodes.Test, negate: bool = False) -> None:
        """Write a Jinja ``Test`` to the stream."""
        self.visit(node.node)
        if negate:
            # keeping "is not" as one token prevents line breaks between them
            op = "is not"
        else:
            op = "is"
        self.tokens.extend(
            (j2tokens.TOKEN_WHITESPACE, SPACE, TEST_PRIORITY),
            (j2tokens.TOKEN_NAME, op),
            (j2tokens.TOKEN_WHITESPACE, SPACE),
            (j2tokens.TOKEN_NAME, node.name),
        )
        if any((node.args, node.kwargs, node.dyn_args, node.dyn_kwargs)):
            with self.token_pair_paren():
                self.signature(node)
        else:
            self.tokens.append(j2tokens.TOKEN_WHITESPACE, SPACE)

    def visit_CondExpr(self, node: nodes.CondExpr) -> None:
        """Write a conditional expression to the stream.

        A conditional expression (inline ``if`` expression)::

            {{ foo if bar else baz }}
        """
        self.visit(node.expr1)
        self.tokens.extend(
            (j2tokens.TOKEN_WHITESPACE, SPACE, TERNARY_PRIORITY),
            (j2tokens.TOKEN_NAME, "if"),
            (j2tokens.TOKEN_WHITESPACE, SPACE),
        )
        self.visit(node.test)
        if node.expr2 is not None:
            self.tokens.extend(
                (j2tokens.TOKEN_WHITESPACE, SPACE, TERNARY_PRIORITY),
                (j2tokens.TOKEN_NAME, "else"),
                (j2tokens.TOKEN_WHITESPACE, SPACE),
            )
            self.visit(node.expr2)

    def visit_Call(self, node: nodes.Call) -> None:
        """Write a function ``Call`` expression to the stream."""
        self.visit(node.node)
        with self.token_pair_paren():
            self.signature(node)

    def visit_Keyword(self, node: nodes.Keyword) -> None:
        """Write a dict ``Keyword`` expression to the stream."""
        self.tokens.extend(
            (j2tokens.TOKEN_NAME, node.key),
            (j2tokens.TOKEN_ASSIGN, "="),
        )
        self.visit(node.value)

    # -- Unused nodes for extensions

    # def visit_MarkSafe(self, node: nodes.MarkSafe) -> None:
    #     """ast node added by extensions, could dump to template if syntax were known"""

    # def visit_MarkSafeIfAutoescape(self, node: nodes.MarkSafeIfAutoescape) -> None:
    #     """Used by InternationalizationExtension"""
    #     # i18n adds blocks: ``trans/pluralize/endtrans``, but they are not in ast

    # def visit_EnvironmentAttribute(self, node: nodes.EnvironmentAttribute) -> None:
    #     """ast node added by extensions, not present in orig template"""

    # def visit_ExtensionAttribute(self, node: nodes.ExtensionAttribute) -> None:
    #     """ast node added by extensions, not present in orig template"""

    # def visit_ImportedName(self, node: nodes.ImportedName) -> None:
    #     """ast node added by extensions, could dump to template if syntax were known"""

    # def visit_InternalName(self, node: nodes.InternalName) -> None:
    #     """ast node added by parser.free_identifier, not present in template"""

    # def visit_ContextReference(self, node: nodes.ContextReference) -> None:
    #     """Added by DebugExtension"""
    #     # triggered by debug block, but debug block is not present in ast

    # def visit_DerivedContextReference(self, node: nodes.DerivedContextReference) -> None:
    #     """could be added by extensions. like debug block but w/ locals"""

    # noinspection PyUnusedLocal
    def visit_Continue(
        self, node: nodes.Continue  # pylint: disable=unused-argument
    ) -> None:
        """Write a ``Continue`` block for the LoopControlExtension to the stream."""
        with self.token_pair_block(node, "continue"):
            pass

    # noinspection PyUnusedLocal
    def visit_Break(self, node: nodes.Break) -> None:  # pylint: disable=unused-argument
        """Write a ``Break`` block for the LoopControlExtension to the stream."""
        with self.token_pair_block(node, "break"):
            pass

    # def visit_Scope(self, node: nodes.Scope) -> None:
    #     """could be added by extensions.
    #     Wraps the ScopedEvalContextModifier node for autoescape blocks
    #     """

    # def visit_OverlayScope(self, node: nodes.OverlayScope) -> None:
    #     """could be added by extensions."""

    # def visit_EvalContextModifier(self, node: nodes.EvalContextModifier) -> None:
    #     """could be added by extensions."""

    def visit_ScopedEvalContextModifier(
        self, node: nodes.ScopedEvalContextModifier
    ) -> None:
        """Write an ``autoescape``/``endautoescape`` block to the stream."""
        autoescape = None
        for keyword_node in node.options:
            if keyword_node.key == "autoescape":
                autoescape = keyword_node.value
                break
        if autoescape is None:
            # unknown Modifier block
            self.generic_visit(node)
            return
        with self.token_pair_block(node, "autoescape"):
            self.visit(autoescape)
        for child_node in node.body:
            self.visit(child_node)
        with self.token_pair_block(node, "endautoescape"):
            self.visit(autoescape)
