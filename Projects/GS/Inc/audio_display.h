/**
  ******************************************************************************
  * @file    audio_display.h
  * @brief   Acoustic safety dashboard for audio-event detections.
  ******************************************************************************
  */

#ifndef AUDIO_DISPLAY_H
#define AUDIO_DISPLAY_H

#include <stdbool.h>

#include "audio_event_filter.h"

void AudioDisplay_SecurityConfig(void);
bool AudioDisplay_Init(void);
void AudioDisplay_RequestAcknowledge(void);
void AudioDisplay_SetMonitoring(bool enabled);
void AudioDisplay_Update(const char *decision_label,
                         float decision_confidence,
                         const char *const top_labels[AUDIO_EVENT_TOP_COUNT],
                         const float top_scores[AUDIO_EVENT_TOP_COUNT],
                         bool show_predictions);

#endif /* AUDIO_DISPLAY_H */
