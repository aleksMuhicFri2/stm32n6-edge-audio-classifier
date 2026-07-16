/**
  ******************************************************************************
  * @file    audio_display.h
  * @brief   Minimal STM32N6570-DK LCD UI for audio-event detections.
  ******************************************************************************
  */

#ifndef AUDIO_DISPLAY_H
#define AUDIO_DISPLAY_H

#include <stdbool.h>

bool AudioDisplay_Init(void);
void AudioDisplay_Update(const char *class_name, float confidence);

#endif /* AUDIO_DISPLAY_H */
