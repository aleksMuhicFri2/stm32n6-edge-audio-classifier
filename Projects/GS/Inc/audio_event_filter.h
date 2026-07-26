/**
  ******************************************************************************
  * @file    audio_event_filter.h
  * @brief   Temporal smoothing and hysteresis for audio-event predictions.
  ******************************************************************************
  */

#ifndef AUDIO_EVENT_FILTER_H
#define AUDIO_EVENT_FILTER_H

#include <stdbool.h>
#include <stdint.h>

#define AUDIO_EVENT_TOP_COUNT  (3U)
#define AUDIO_EVENT_NO_CLASS   (UINT32_MAX)

typedef enum
{
  AUDIO_EVENT_WAITING = 0,
  AUDIO_EVENT_UNKNOWN,
  AUDIO_EVENT_CLASS
} AudioEventState_t;

typedef struct
{
  uint32_t frame_index;
  bool audio_active;
  bool decision_changed;
  AudioEventState_t state;
  uint32_t decision_index;
  float decision_confidence;
  uint32_t top_indices[AUDIO_EVENT_TOP_COUNT];
  float top_scores[AUDIO_EVENT_TOP_COUNT];
} AudioEventResult_t;

void AudioEventFilter_Init(void);
void AudioEventFilter_Update(const float *scores,
                             uint32_t class_count,
                             bool audio_active,
                             AudioEventResult_t *result);

#endif /* AUDIO_EVENT_FILTER_H */
