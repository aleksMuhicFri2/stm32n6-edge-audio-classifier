# Hazard-5 V4 refined-Shatter YAMNet-1024

This directory contains the detailed host evaluation of the selected refined
taxonomy candidate. FSD50K glass training and validation records must carry the
explicit `Shatter` label, while the explicit ESC-50 glass-breaking class is
retained. Training and validation uploaders are disjoint.

The int8-boundary Open Neural Network Exchange model reached 88.49% clip
accuracy, 90.12% macro recall, and 83.33% glass-breaking recall on 278
development clips. The model remains a host-side candidate and has not been
flashed or tested on the reserved physical final protocol.
