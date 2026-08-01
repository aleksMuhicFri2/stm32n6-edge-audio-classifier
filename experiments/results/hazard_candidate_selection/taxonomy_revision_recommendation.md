# Final Hazard-5 taxonomy revision

The first five-class firmware was accurate as a closed set, but live quiet
voices exposed a product problem: a hazard-only softmax must always choose a
hazard. The user therefore approved removing both `screaming` and `chainsaw`.
No reserved-test clips were used to choose their replacements.

`glass_breaking` replaces `screaming`. It is useful for break-in or accident
detection, simple to demonstrate safely with recorded audio, and avoids making
ordinary voice a neighbor of a user-facing distress class.

The second replacement study compared fire, dog bark, and vehicle horn while
holding glass breaking, gunshot/gunfire, siren, and thunderstorm fixed:

| Replacement | Validation accuracy | Macro recall | Minimum class recall | Closest centroid pair |
|---|---:|---:|---:|---|
| Crackling fire | 88.94% | 89.25% | 75.0% | fire / thunder, 0.9735 |
| Dog bark | **89.29%** | **89.37%** | **78.33%** | dog / siren, 0.9309 |
| Vehicle horn | 89.09% | 88.10% | 71.43% | siren / horn, 0.9364 |

Dog bark was selected because it produced the best macro recall and minimum
class recall, had substantially less centroid overlap than fire, and is a
practical animal or property warning. The final five visible classes are:

1. dog bark;
2. glass breaking;
3. gunshot/gunfire;
4. emergency siren;
5. thunderstorm.

The independently evaluated int8 YAMNet-256 model classified 225/254
development-validation clips correctly (88.58%); class recalls were 81.67%,
81.67%, 90.74%, 90.0%, and 100%, respectively. It compiled to the same
148,417-byte Neural-ART weight footprint as the earlier five-class model and
was flashed with read-back verification.

Background-aware, binary-gate, speech-heavy, seven-output, and confidence/margin
experiments did not jointly retain the required hazard recall and reject 95% of
speech, so none of those models was deployed. The product now logs the exact
on-board spectrogram activity value for controlled live sensitivity calibration.
Reserved ESC-50 fold 5 and FSD50K evaluation data remain untouched until the
taxonomy, sensitivity threshold, and physical protocol are frozen.
