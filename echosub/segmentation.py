# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Splitting one stretch of speech into runs, one per voice."""
import logging

from . import audio

SR = audio.SAMPLE_RATE

log = logging.getLogger(__name__)


def speaker_runs(speakers, seg, regions):
    """Split an utterance where the voice changes -> [(start, end, speaker_id)]."""
    if speakers is None:
        return [(0, len(seg), None)]
    try:
        long_regions = [r for r in regions if r[1] - r[0] >= SR * 1.0]
        if len(long_regions) < 2:
            return [(0, len(seg), speakers.identify(seg))]

        labels = []
        for a, b in regions:
            labels.append(speakers.identify(seg[a:b]) if b - a >= SR * 1.0 else None)
        # Short regions inherit the voice of the preceding (or following) region
        for k in range(len(labels)):
            if labels[k] is None:
                labels[k] = labels[k - 1] if k and labels[k - 1] is not None else None
        for k in reversed(range(len(labels))):
            if labels[k] is None and k + 1 < len(labels):
                labels[k] = labels[k + 1]

        runs = []
        for (a, b), spk in zip(regions, labels):
            if runs and runs[-1][2] == spk:
                runs[-1][1] = b
            else:
                runs.append([a, b, spk])
        # Cut halfway through the pauses; first/last run reach the segment edges
        for k in range(len(runs) - 1):
            mid = (runs[k][1] + runs[k + 1][0]) // 2
            runs[k][1], runs[k + 1][0] = mid, mid
        runs[0][0], runs[-1][1] = 0, len(seg)
        return [tuple(r) for r in runs]
    except Exception:
        log.exception("Speaker detection failed for a segment")
        return [(0, len(seg), None)]
