# Speech-guard physical smoke test

Status: completed on 2026-08-07; predefined smoke-test gate passed.

## Purpose

Verify that the deployed speech-aware model treats ordinary human speech as an
informational result or as unknown, without confirming or latching a hazard.
This is a product smoke test and does not use final evaluation data.

## Fixed setup

- Firmware: commit `9a614d2` (`YAMNet-256 Hazard-5 + Speech`).
- Board: STM32N6570-DK using its onboard microphone.
- Position: operator approximately 30 cm from the board microphone.
- Room: quiet; wait for `WAITING` before every attempt.
- Before starting, press `TAMP` once to clear the alert left by the thunderstorm
  test.
- Pause: leave at least 3 s of silence after each attempt.

## Attempts

1. **Normal voice:** say, at conversational volume, "Danes preizkušam sistem
   za prepoznavanje nevarnih zvokov."
2. **Quiet voice:** count slowly from one to ten in Slovenian at a quieter but
   still intelligible level.
3. **Loud voice:** speak naturally but loudly for about 5 s; do not shout
   directly into the microphone.

For each attempt, record the large main result, the highest visible speech
percentage if shown in the top three, and whether any hazard alert was latched.

## Result record

| Attempt | Main result | Speech in top 3? | Highest visible speech % | Hazard latched? | Notes |
|---|---|---|---:|---|---|
| Normal voice | HUMAN SPEECH | Yes | 97% | No | Operator-reported live result. |
| Quiet voice | HUMAN SPEECH | Yes | 85% | No | Speech remained intelligible rather than whispered. |
| Loud voice | HUMAN SPEECH | Yes | 98% | No | Operator-reported live result. |

## Observation and decision

All three intended speech conditions produced `HUMAN SPEECH`, with visible
scores of 97%, 85%, and 98%, and no hazard was reported or latched. Whispering
did not reliably activate the speech class; this is accepted as an operating
limitation because the target negative condition is ordinary audible speech
rather than whispered speech.

The deployed asymmetric speech guard passes the physical smoke test. These are
three operator-observed smoke-test measurements and must not be presented as a
formal accuracy estimate.

## Decision rule

- **Pass:** none of the three speech attempts latches a hazard. `HUMAN SPEECH`
  is preferred, while `UNKNOWN` is acceptable for quiet speech.
- **Needs calibration:** a hazard becomes the confirmed main result or latches
  during any clean speech attempt.
