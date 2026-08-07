# TD-A02 methodological interpretation

The preregistered delivery rule remains unchanged: a trial qualifies only with
at least three active-audio telemetry frames and an operator rating of
`comfortable`. Under that rule, 2/5 TD-A02 trials qualified. Classification
predictions from this calibration are not accuracy results.

## What TD-A02 resolved

- Repeated gunshot source `P2R-018` at net +10 dB was comfortable and produced
  nine active frames. Freeze this source and level for subsequent controlled
  work. This establishes delivery for this source, not general gunshot
  recognition performance.
- Clapping at -18 dB was comfortable and produced twelve active frames.
- Together with TD-A01, both selected glass sequences have qualified at +3 dB.
  The short-transient delivery problem is therefore resolved for the retained
  gunshot and glass development stimuli.

## Out-of-distribution interpretation

The board's `audio_active` field is a decision-gate state, not an independent
sound-level meter. For an out-of-distribution (OOD) sound, remaining inactive
can be the system's valid rejection mechanism. It is therefore inappropriate
to keep increasing an audible OOD stimulus merely to force three active frames:
doing so changes the exposure and can manufacture false positives.

This interpretation does not retroactively change the 2/5 preregistered TD-A02
qualification result. For the final OOD experiment, physical delivery should
instead be accepted when the operator confirms comfortable audibility, while
zero active frames must be preserved and reported as system behavior.

## Frozen or bounded playback settings

| Stimulus | Final development setting | Evidence |
|---|---:|---|
| Glass breaking | +3 dB | Two comfortable TD-A01 sequences passed activity |
| Retained gunshot `P2R-018` | +10 dB | Comfortable; nine active TD-A02 frames |
| Clapping | -18 dB | Comfortable; twelve active TD-A02 frames |
| Clock tick | -12 dB | Comfortable; zero active TD-A02 frames |
| Rain | -15 dB | Comfortable in TD-A01; -13 dB was too loud in TD-A02 |
| Crying baby | -15 dB | Comfortable and active in TD-A01 |
| Wooden-door knock | -14 dB candidate | -15 dB was too quiet; -13 dB was too loud |

The wooden-door midpoint needs only a brief human audibility check before the
final run, not another multi-clip classifier calibration. Windows volume 75%
and a 30 cm speaker-to-microphone distance remain fixed.
