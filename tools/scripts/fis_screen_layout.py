# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
"""On-screen positions of FIS-backed battle banners, as guarded overlay edits."""

from dataclasses import dataclass
import struct

from .overlay_edits import Edit, offset_of, word


COORDINATE_LIMIT = 4096
_V0_LUI = 0x3C020000
_V1_LUI = 0x3C030000


@dataclass(frozen=True)
class Banner:
    name: str
    original: tuple
    words: tuple  # (address, axis, lui prefix) per animation constant


#: Banners whose position a layout may move, by the image that draws them and
#: the DTT records that form the phrase.
BANNERS = {
    "fis-1781-unprotected-slz-0xDD740-98C80.png": {
        (1, 2): Banner("Guard Break", (90, 160), (
            (0x004DB070, 0, _V0_LUI),  # animation target X
            (0x004DB09C, 0, _V1_LUI),  # animation completion X
            (0x004DB594, 1, _V1_LUI),  # animation anchor Y
        )),
        (5, 6, 7): Banner("Over Attack!", (225, 358), (
            (0x004DC37C, 0, _V0_LUI),  # animation target X
            (0x004DC3B4, 0, _V0_LUI),  # animation completion X
            (0x004DC390, 1, _V0_LUI),  # animation target Y
        )),
    },
}


def position_word(value, prefix):
    """The ``lui`` instruction that loads ``value`` as a float's high half."""
    bits = struct.unpack("<I", struct.pack("<f", float(value)))[0]
    if bits & 0xFFFF:
        raise ValueError("coordinate %d cannot be encoded by this animation "
                         "instruction" % value)
    return prefix | (bits >> 16)


def edits(image, groups):
    """The overlay edits that move ``groups`` of ``image``'s banner records.

    Each group is ``(records, from, to)``; ``from`` must be the banner's
    original position.
    """
    banners = BANNERS.get(image)
    if banners is None:
        raise ValueError("no banner positions are known for image %s" % image)
    changes, seen = [], set()
    for records, before, after in groups:
        records = tuple(records)
        banner = banners.get(records)
        if banner is None:
            raise ValueError("records %r form no banner with known positions"
                             % (records,))
        if records in seen:
            raise ValueError("records %r are moved twice" % (records,))
        seen.add(records)
        before, after = tuple(before), tuple(after)
        if before != banner.original:
            raise ValueError("%s from must be its original position %r"
                             % (banner.name, banner.original))
        if any(abs(value) > COORDINATE_LIMIT for value in after):
            raise ValueError("%s to must stay within +/-%d"
                             % (banner.name, COORDINATE_LIMIT))
        for address, axis, prefix in banner.words:
            try:
                replacement = position_word(after[axis], prefix)
            except ValueError as exc:
                raise ValueError("%s to: %s" % (banner.name, exc))
            changes.append(Edit(
                offset_of(address), word(position_word(before[axis], prefix)),
                word(replacement),
                "%s %s position" % (banner.name, "xy"[axis])))
    return changes
