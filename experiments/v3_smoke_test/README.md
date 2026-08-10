# YAMNet-1024 V3 functional smoke test

This six-clip set checks that the newly flashed firmware responds to every
displayed class. It is deliberately separate from the locked final evaluation
and must not be reported as an unbiased accuracy estimate.

Five sources were previously judged canonical and normally audible in the
second pilot listening review. The speech source is the unboosted version of a
canonical normal-conversation source because the pilot rendering was judged
too loud. Short siren, glass, and gunshot sources are repeated with silent gaps
without changing their amplitude. Every output includes one second of leading
and trailing silence.

Prepare the deterministic audio files with:

```powershell
..\ml-workspace\.venv\Scripts\python.exe .\ml\prepare_v3_smoke_test.py
```

Run the screen-observation test with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\run_v3_smoke_test.ps1
```

Before board playback, the deployment-form int8 model was run on the exact six
prepared files. It classified all six clips correctly. This is a deterministic
sanity check of the files and preprocessing, not an accuracy estimate: the
clips were intentionally selected to be clear examples. Detailed host results
are stored under `../results/hazard5v4_patch_balanced_v3_smoke_host`.
