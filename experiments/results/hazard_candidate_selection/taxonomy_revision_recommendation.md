# Hazard taxonomy revision after the speech hard-negative audit

The deployed five-class taxonomy performs strongly as a closed set, but live
quiet voices and the 24-clip speech audit expose a structural problem:
`screaming` is acoustically too close to ordinary speech for this dataset and
YAMNet-256 head. Closed-set confidence rejects only 4/24 speech clips, and the
best binary gate that preserves hazards rejects 21/24 rather than the required
23/24.

The existing seven-candidate embedding study was re-analysed without using any
reserved-test data:

| Five-class option | Validation accuracy | Macro recall | Closest centroid pair | Similarity |
|---|---:|---:|---|---:|
| Current (`screaming`) | 97.71% | 97.49% | screaming / siren | 0.9764 |
| Replace with `glass_breaking` | 92.86% | 90.59% | glass / gunshot | 0.9296 |
| Replace with `crackling_fire` | 93.53% | 89.50% | fire / thunderstorm | 0.9735 |

`glass_breaking` is the recommended revision. It removes ordinary voice from
the user-facing taxonomy, has the lowest maximum inter-class centroid
similarity, is safe and simple to demonstrate using recorded audio, and is a
useful break-in or accident event. Its preliminary recall is 49/60 = 81.67%,
so it must be retrained and pass the same background, NPU, and physical-playback
gates before replacing the current model. The current firmware remains the
rollback baseline until the user approves this taxonomy change.
