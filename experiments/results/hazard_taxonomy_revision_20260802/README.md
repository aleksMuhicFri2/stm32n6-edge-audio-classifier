# Hazard taxonomy revision experiment series

This directory summarizes the controlled experiments performed after the user
approved removing screaming and chainsaw. The selected final visible taxonomy
is dog bark, glass breaking, gunshot/gunfire, siren, and thunderstorm.

`model_comparison.csv` supports the accuracy-versus-memory graph.
`rejection_comparison.csv` records why confidence filtering and both binary
gates were rejected. `taxonomy_revision_tradeoffs.png` combines these two
engineering decisions in a thesis-ready figure.

All numbers are development results. ESC-50 fold 5 and FSD50K evaluation were
kept reserved throughout selection, training, threshold calibration, and
deployment.
