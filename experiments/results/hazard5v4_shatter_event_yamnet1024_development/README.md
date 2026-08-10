# Hazard-5 V4 event-window ablation

This rejected ablation replaces each gunshot and glass-breaking training
recording with one reviewed, one-second event window. Validation audio is
unchanged. The model reached 83.81% clip accuracy, 85.80% macro recall, 73.33%
glass recall, and 81.48% gunshot recall.

The apparent clip balance concealed a large patch imbalance: glass and gunshot
each contributed 192 training patches, while thunderstorm contributed 2,068.
The model is retained as negative experimental evidence and will not be
deployed.
