# V3 thunder decision calibration

This is a small, non-final calibration experiment for the deployed YAMNet-1024 V3 model. It addresses a specific board observation: thunder was repeatedly the highest-scoring class, but remained below the shared 0.65 decision threshold.

The set contains five manually reviewed thunder clips and eight negatives: the five other deployed classes, rain and wind attenuated by 20 decibels, and a door knock. High-pitched thunder recordings previously rejected during listening review are excluded. Long thunder recordings are reduced to a deterministic six-second excerpt centred on their strongest half-second energy window. Every transformation and file hash is recorded in `manifest.csv`.

Fixed playback conditions:

- Windows volume: 70 percent
- Speaker distance: approximately 30 centimetres
- Board microphone and speaker placement: unchanged during all trials
- Firmware and model: deployed YAMNet-1024 V3 image

This material must not be mixed into the reserved final evaluation. Its only purpose is to select and justify a thunder-specific decision rule before a new smoke test.

## Result

The first rule used a 0.35 threshold and required thunder to rank first in two consecutive active frames. It covered the original six thunder playbacks, but a post-flash replay alternated between thunder and siren and did not trigger. This failed replay was retained as a seventh positive calibration trace.

The revised rule requires a thunder score of at least 0.32 in two consecutive active frames, even if thunder briefly ranks second, and still requires thunder to rank first on the confirmation frame. It covers all seven thunder playbacks and produces no thunder decision on the eight negative playbacks. The revised thunder release threshold is 0.25. All other class thresholds remain unchanged.

This is a preliminary firmware calibration result, not a claim of final system accuracy. The signed candidate was flashed and passed the subsequent six-class physical functional smoke test. The firmware and evaluation protocol can now be frozen before the reserved final evaluation.
