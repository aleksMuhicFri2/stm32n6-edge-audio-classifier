# Hazard candidate physical-playback protocol

Status: prepared but not started. Physical playback begins only after the
candidate model includes every class being compared.

## Fixed setup

- Board: STM32N6570-DK using the onboard digital MEMS microphone.
- Board orientation: display facing the operator; microphone position marked.
- Speaker: use one speaker and one playback device throughout a run.
- Initial distance: 1.00 m measured from speaker to board microphone.
- Initial volume: fixed percentage recorded in the trial log.
- Room: record room identity and notable background sources.
- Silence gap: at least 2 s before and after every clip.

Do not change volume or distance within a run. If either changes, begin a new
run ID.

## Pilot schedule

For every candidate class:

1. Select ten validation clips not used to tune an individual threshold.
2. Randomize the presentation order with seed 120.
3. Play each clip once at 1.00 m in a quiet room.
4. Capture the complete UART output.
5. Record expected class, predicted class, peak confidence, latency, and alert.
6. Repeat representative failures once without changing the setup; retain both
   observations rather than replacing the first.

Then play at least five examples from every hard-negative group in
`ml/data/hazard_candidates/hard_negative_plan.csv`.

## Trial fields

The `Playback Trials` sheet in `hazard_candidate_selection.xlsx` is the source
of truth. One row represents one playback attempt. Unknown values remain blank.
Never enter zero merely to indicate that a measurement was not collected.

## Stop conditions

Stop the run and document the reason if:

- the speaker volume or position changes accidentally;
- the board resets or the display freezes;
- UART capture stops;
- another uncontrolled sound masks a presented clip;
- the wrong audio file is played.

The affected trial is retained with an explanatory note and excluded only by a
documented analysis rule.

## Candidate gate

A candidate should normally achieve at least 80% playback recall and no more
than 10% trigger rate across its planned hard negatives. These are selection
targets for a research prototype rather than safety-certification claims.
