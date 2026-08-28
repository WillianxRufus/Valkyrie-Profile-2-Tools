# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Deterministic tri-Ace SLZ mode 1/2 compressor."""

import struct


MIN_MATCH = 3
MAX_MATCH = 18
MAX_DISTANCE = 4095
MAX_CHAIN = 4096
MIN_RUN = 4
MAX_RUN = 0xFF + 0x13


def _run_length(source, position):
    end = min(len(source), position + MAX_RUN)
    value = source[position]
    length = 1
    while position + length < end and source[position + length] == value:
        length += 1
    return length


def compress_body(source, mode):
    """Encode bytes with the greedy parse used by the original local tool."""
    if mode not in (1, 2):
        raise ValueError("SLZ byte compressor supports only modes 1 and 2")
    source = bytes(source)
    size = len(source)
    heads = {}
    previous = [-1] * size

    def insert(position):
        if position + MIN_MATCH <= size:
            key = source[position:position + MIN_MATCH]
            previous[position] = heads.get(key, -1)
            heads[key] = position

    tokens = []
    position = 0
    while position < size:
        best_length = best_distance = 0
        maximum = min(17 if mode == 2 else MAX_MATCH, size - position)
        if maximum >= MIN_MATCH:
            candidate = heads.get(
                source[position:position + MIN_MATCH], -1
            )
            earliest = position - MAX_DISTANCE
            chain = 0
            while (candidate >= 0 and candidate >= earliest and
                   chain < MAX_CHAIN):
                if source[candidate + best_length] == source[position + best_length]:
                    matched = 0
                    while (matched < maximum and
                           source[candidate + matched] ==
                           source[position + matched]):
                        matched += 1
                    if matched > best_length:
                        best_length = matched
                        best_distance = position - candidate
                        if matched == maximum:
                            break
                candidate = previous[candidate]
                chain += 1

        run_length = _run_length(source, position) if mode == 2 else 0
        if run_length >= MIN_RUN and run_length >= best_length:
            tokens.append(("run", source[position], run_length))
            end = position + run_length
        elif best_length >= MIN_MATCH:
            tokens.append(("match", best_distance, best_length))
            end = position + best_length
        else:
            tokens.append(("literal", source[position]))
            end = position + 1
        while position < end:
            insert(position)
            position += 1

    output = bytearray()
    for group_start in range(0, len(tokens), 8):
        flags = 0
        body = bytearray()
        for bit, token in enumerate(tokens[group_start:group_start + 8]):
            if token[0] == "literal":
                flags |= 1 << bit
                body.append(token[1])
            elif token[0] == "match":
                _, distance, length = token
                body.extend((
                    distance & 0xFF,
                    ((distance >> 8) & 0x0F) | ((length - 3) << 4),
                ))
            else:
                _, fill, length = token
                if length <= 18:
                    body.extend((fill, 0xF0 | (length - 3)))
                else:
                    body.extend((length - 0x13, 0xF0, fill))
        output.append(flags)
        output.extend(body)
    return bytes(output)


def compress(source, mode, next_offset=0):
    """Return one complete mode-1 or mode-2 SLZ stream."""
    source = bytes(source)
    body = compress_body(source, mode)
    return b"SLZ" + bytes((mode,)) + struct.pack(
        "<III", len(body), len(source), next_offset
    ) + body
