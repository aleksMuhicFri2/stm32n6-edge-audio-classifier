# Final-taxonomy YAMNet-256 development model

This run uses dog bark, glass breaking, gunshot/gunfire, emergency siren, and
thunderstorm. The model output order is alphabetical and matches the firmware
class list.

The independently evaluated int8 model classified 225/254 development clips
correctly (88.58%) with 88.81% macro recall. Per-class recall was 81.67% for
dog bark, 81.67% for glass breaking, 90.74% for gunshot/gunfire, 90% for siren,
and 100% for thunderstorm. The float model reached 88.98% clip accuracy, so
int8 quantization cost 0.40 percentage points.

The model is a development deployment, not the final thesis test. ESC-50 fold
5 and FSD50K evaluation remain reserved. Several rejection architectures were
tested and rejected because none simultaneously preserved danger recall and
rejected 95% of speech. Live firmware therefore retains the five-class model
and logs `spectrogram_sum` for a controlled physical sensitivity calibration.

ST Edge AI Core 4.0.1 produced 148,417 bytes of Neural-ART weights. The bare-
metal build completed with zero errors and one pre-existing RWX linker warning.
Both weights and the signed application passed external-flash read-back
verification; FSBL and OTP were not modified. Normal-boot LCD/UART confirmation
is pending moving the physical boot selector back to run mode.
