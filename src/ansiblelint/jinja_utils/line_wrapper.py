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

    def stringify(
        self,
        tokens: TokenStream,
        max_lines: int | None = None,
        max_length: int | None = None,
    ) -> str:
        """Convert tokens to string within limits."""
        string = ""
        length = 0
        lines = 1
        for token in tokens:
            new_lines = token.value_str.count("\n")
            lines += new_lines
            if max_lines is not None and lines > max_lines:
                raise ValueError("ExceededLines")
            if not new_lines:
                length += len(token.value_str)
                lengths = [length]
            else:
                index = token.value_str.find("\n")
                lengths = [length + index]
                while True:
                    start = index + 1
                    index = token.value_str.find("\n", start)
                    if index == -1:
                        if start < len(token.value_str):
                            lengths.append(len(token.value_str) - start)
                        break
                    lengths.append(index - start)
                length = lengths[-1]
            if max_length is not None and max(lengths) > max_length:
                raise ValueError("ExceededLength")
            string += token.value_str
        return string

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
