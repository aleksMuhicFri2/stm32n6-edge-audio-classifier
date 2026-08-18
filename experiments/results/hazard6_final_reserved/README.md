# Reserved STM32N6 physical final-evaluation result

Evaluation: `STM32N6-HAZARD6-FINAL-001`  
Attempt: `FE-A01`  
Manifest: `439f00ddb787948d2b2253d450030c0881af766066b36a300cde3121142043ec`

All 70 run IDs, raw UART logs, stimulus hashes, physical settings,
firmware identity, frame totals, and source partitions match the frozen
manifest. The results were generated without changing the deployed model or
thresholds.

## Confirmed target detection

| Output | Detected | Rate | Wilson 95% CI | Active | Rank-1 seen |
|---|---:|---:|---:|---:|---:|
| Dog bark | 6/10 | 60.0% | 31.3--83.2% | 9/10 | 9/10 |
| Glass | 5/10 | 50.0% | 23.7--76.3% | 9/10 | 9/10 |
| Gunshot | 3/10 | 30.0% | 10.8--60.3% | 10/10 | 7/10 |
| Siren | 9/10 | 90.0% | 59.6--98.2% | 10/10 | 9/10 |
| Speech | 10/10 | 100.0% | 72.2--100.0% | 10/10 | 9/10 |
| Thunderstorm | 4/10 | 40.0% | 16.8--68.7% | 9/10 | 8/10 |

Across all six outputs, 37/60 trials produced
the correct confirmed output (61.7%;
Wilson 95% CI 49.0--72.9%).
The five danger outputs produced 27/50 confirmed
target trials (54.0%).

## Speech guard and false alerts

Speech was confirmed in 10/10 trials.
Confirmed danger outputs occurred in 1/10 speech
trials. The OOD set produced 2/10 trials with a
confirmed danger output (20.0%; Wilson 95%
CI 5.7--51.0%). OOD inactivity is
retained as system behavior and is not treated as missing delivery evidence.

## Performance qualification

The stage-time table and figure use firmware-reported telemetry. They quantify
the deployed processing implementation but are not independent oscilloscope or
GPIO measurements. Estimated UART-frame offsets are preserved in the trial
table and must not be presented as precision end-to-end latency.

The generated tables, figures, and summary are retained in this directory.
The historical analysis helper remains available through the repository history.
