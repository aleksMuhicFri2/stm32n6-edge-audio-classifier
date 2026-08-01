# Hazard-5 open-set confidence audit

This audit runs the unchanged, hardware-validated five-output model on the
common 302-clip development manifest: 182 hazards and 120 non-hazard sounds,
including 24 speech clips. ST's model-zoo preprocessing is reproduced exactly.
All 182 hazard predictions match the prior closed-set evaluation, including
174 correct classifications (95.60%), so this is a regression-consistent
comparison.

## Finding

The current firmware's approximate offline counterpart (`top1 >= 0.55`)
retains 92.31% of hazards but rejects only 29.17% of general background and
16.67% of speech. A grid search over top-one confidence and the top-one versus
top-two margin found no operating point that jointly retained 95% of hazards,
retained at least 85% of every hazard class, and rejected 95% of speech.

The hazard-safe diagnostic rule (`margin >= 0.185`) retained 95.05% of hazards
but rejected only 20.83% of speech. Confidence therefore cannot reliably
separate ordinary speech from hazards. This is especially clear for speech
misclassified as `screaming`: its confidence and ambiguity distributions
almost completely overlap genuine screams.

No firmware change was made from this experiment. The next controlled retry
uses a separate binary gate with more ordinary-speech training examples.
Reserved external test partitions remain untouched.
