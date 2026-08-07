# Blinded pilot-stimulus listening review

This review determines whether the speech, glass-breaking, and gunshot source
recordings are representative of the intended product. It is separate from the
board result: the review runner does not show predictions, confidence, or
pass/fail status.

The original pilot scores remain unchanged regardless of this review. Review
labels are used to interpret the pilot and design the next dataset, not to
silently remove failed trials.

## Review labels

Representativeness:

- `canonical`: a clear, ordinary example appropriate for the intended product;
- `atypical_valid`: unusual (for example whispering, screaming, weak glass, or a
  distant shot) but still genuinely belongs to the stated class;
- `ambiguous_wrong`: the intended sound is unclear, dominated by another sound,
  or likely mislabeled.

Audibility at the computer:

- `normal`: clearly audible without sounding overloaded;
- `quiet`: difficult to hear at the fixed review volume;
- `loud_distorted`: clipped, overloaded, or obviously distorted.

## Procedure

1. Keep Windows volume fixed for the complete review.
2. Run `tools/run_pilot_listening_review.ps1` from the repository root.
3. Listen to all 15 speech, glass, and gunshot clips once before consulting the
   board results.
4. Assign one representativeness label, one audibility label, and an optional
   short note after each clip.
5. Do not change a label after looking at whether the board passed that trial.

The responses are written incrementally to
`experiments/pilot_evaluation/listening_review_responses.csv`, allowing the
review to be resumed after interruption.

## Use in the next experiment

Define inclusion rules before selecting new validation clips. Canonical and
atypical-but-valid clips should be reported as separate strata. Ambiguous or
incorrectly labeled clips may be excluded only by the listening rule, before
the new model is evaluated. Curated presentation clips must be reported
separately from the formal evaluation set.
