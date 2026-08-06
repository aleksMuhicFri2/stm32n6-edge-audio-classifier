# Rejected speech-2x retry

This controlled retry repeated the 192 speech training rows once while leaving
the 278 development-validation clips unchanged. It tested whether simple class
weighting through oversampling could improve speech recognition.

The quantized model classified 235 of 278 clips correctly (84.53%). Speech
recall remained 17/24 (70.83%), while dog-bark recall fell to 76.67% and glass
breaking recall fell to 75%. Because speech did not improve and overall hazard
performance decreased, this model was rejected and was never compiled or
flashed. The balanced one-copy model was retained for guard calibration.

Reserved ESC-50 fold 5 and FSD50K evaluation data were not used.
