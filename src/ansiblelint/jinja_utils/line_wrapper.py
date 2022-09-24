"""Jinja template/expression line wrapper utils for dumping."""
from __future__ import annotations

from .token import TokenStream


class LineWrapper:
    def __init__(
        self,
        # max_line_length: int,
        # max_first_line_length: int | None = None,
    ):
        pass
        # self._block_stmt_start_position = -1
        # self._block_stmt_start_line = -1

    def process(self, tokens: TokenStream) -> None:
        pass

    # old logic from dumper
    # contextmanager()
    # def token_pair_block():
    #     self._block_stmt_start_position = self.tokens.line_position
    #     self._block_stmt_start_line = self.tokens.line_number
    #     yield
    #     if (
    #         # if the block starts in the middle of a line, keep it inline.
    #         self._block_stmt_start_position == 0
    #         # if the block statement uses multiple lines, don't inline the body.
    #         or self._block_stmt_start_line != self.tokens.line_number
    #     ):
    #         if "\n" not in end_string:  # TODO: does this make sense?
    #             self.tokens.append(j2tokens.TOKEN_WHITESPACE, "\n")
    #         self._block_stmt_start_position = -1
    #         self._block_stmt_start_line = -1
