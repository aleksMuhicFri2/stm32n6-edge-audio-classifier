# Result of the first transient-event extraction review

The review was completed before any model was trained on the derived windows.
It therefore acts as a data-quality gate rather than a post-hoc explanation of
model accuracy.

## Predefined gate result

- Reviewed windows: 30
- Valid events overall: 26/30 (86.67%)
- Valid gunshot/gunfire events: 15/15 (100.00%)
- Valid glass-breaking events: 11/15 (73.33%)
- Truncated events: 3/30 (10.00%)
- Gate passed: no

The required overall validity was 90%, with at least 85% validity in each
class. The rejected dataset was not used for training.

## Root-cause finding

Review notes and source metadata showed that the existing FSD50K
`glass_breaking` selection was drawn from the broad AudioSet parent label
`Glass`. That parent also contains glass clinks, bottle ringing, liquid in a
glass, handling noises, and similar non-breaking events. Some reviewed clips
therefore had no genuine shatter for an event locator to find.

The next dataset revision keeps explicit ESC-50 glass-breaking clips and uses
only FSD50K records carrying both the `Shatter` and `Glass` labels. Training
and validation uploaders are disjoint. A refined locator also favors
broadband high-frequency activity followed by a fragment tail, and reserves
more of the one-second window after the initial impact.
