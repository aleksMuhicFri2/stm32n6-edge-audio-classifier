/**
  ******************************************************************************
  * @file    audio_event_filter.c
  * @brief   EMA smoothing and decision hysteresis for audio-event inference.
  ******************************************************************************
  */

#include "audio_event_filter.h"

#include <string.h>

#include "ai_model_config.h"
#include "app_config.h"

static float s_smoothed_scores[CTRL_X_CUBE_AI_MODEL_CLASS_NUMBER];
static bool s_scores_initialized;
static uint32_t s_frame_index;
static uint32_t s_silent_frames;
static uint32_t s_stable_index = AUDIO_EVENT_NO_CLASS;
static AudioEventState_t s_state = AUDIO_EVENT_WAITING;

static void rank_top_scores(uint32_t class_count, AudioEventResult_t *result)
{
  for (uint32_t rank = 0U; rank < AUDIO_EVENT_TOP_COUNT; rank++)
  {
    uint32_t best_index = AUDIO_EVENT_NO_CLASS;
    float best_score = -1.0F;

    for (uint32_t index = 0U; index < class_count; index++)
    {
      bool already_selected = false;
      for (uint32_t previous = 0U; previous < rank; previous++)
      {
        if (result->top_indices[previous] == index)
        {
          already_selected = true;
          break;
        }
      }

      if ((!already_selected) && (s_smoothed_scores[index] > best_score))
      {
        best_index = index;
        best_score = s_smoothed_scores[index];
      }
    }

    result->top_indices[rank] = best_index;
    result->top_scores[rank] = (best_index == AUDIO_EVENT_NO_CLASS) ? 0.0F : best_score;
  }
}

void AudioEventFilter_Init(void)
{
  memset(s_smoothed_scores, 0, sizeof(s_smoothed_scores));
  s_scores_initialized = false;
  s_frame_index = 0U;
  s_silent_frames = 0U;
  s_stable_index = AUDIO_EVENT_NO_CLASS;
  s_state = AUDIO_EVENT_WAITING;
}

void AudioEventFilter_Update(const float *scores,
                             uint32_t class_count,
                             bool audio_active,
                             AudioEventResult_t *result)
{
  AudioEventState_t previous_state = s_state;
  uint32_t previous_index = s_stable_index;

  if ((scores == NULL) || (result == NULL) || (class_count == 0U) ||
      (class_count > CTRL_X_CUBE_AI_MODEL_CLASS_NUMBER))
  {
    return;
  }

  memset(result, 0, sizeof(*result));
  for (uint32_t rank = 0U; rank < AUDIO_EVENT_TOP_COUNT; rank++)
  {
    result->top_indices[rank] = AUDIO_EVENT_NO_CLASS;
  }

  s_frame_index++;
  result->frame_index = s_frame_index;
  result->audio_active = audio_active;

  if (audio_active)
  {
    s_silent_frames = 0U;
    if (!s_scores_initialized)
    {
      memcpy(s_smoothed_scores, scores, class_count * sizeof(float));
      s_scores_initialized = true;
    }
    else
    {
      for (uint32_t index = 0U; index < class_count; index++)
      {
        s_smoothed_scores[index] =
            AUDIO_EVENT_EMA_ALPHA * scores[index] +
            (1.0F - AUDIO_EVENT_EMA_ALPHA) * s_smoothed_scores[index];
      }
    }
  }
  else
  {
    s_silent_frames++;
    if (s_silent_frames >= AUDIO_EVENT_SILENCE_TO_WAIT_FRAMES)
    {
      memset(s_smoothed_scores, 0, sizeof(s_smoothed_scores));
      s_scores_initialized = false;
      s_stable_index = AUDIO_EVENT_NO_CLASS;
      s_state = AUDIO_EVENT_WAITING;
    }
  }

  rank_top_scores(class_count, result);

  if (audio_active)
  {
    const uint32_t candidate_index = result->top_indices[0];
    const float candidate_score = result->top_scores[0];

    if (s_stable_index == AUDIO_EVENT_NO_CLASS)
    {
      if (candidate_score >= AUDIO_EVENT_ENTER_THRESHOLD)
      {
        s_stable_index = candidate_index;
        s_state = AUDIO_EVENT_CLASS;
      }
      else
      {
        s_state = AUDIO_EVENT_UNKNOWN;
      }
    }
    else
    {
      const float stable_score = s_smoothed_scores[s_stable_index];

      if (candidate_index == s_stable_index)
      {
        if (stable_score < AUDIO_EVENT_RELEASE_THRESHOLD)
        {
          s_stable_index = AUDIO_EVENT_NO_CLASS;
          s_state = AUDIO_EVENT_UNKNOWN;
        }
        else
        {
          s_state = AUDIO_EVENT_CLASS;
        }
      }
      else if ((candidate_score >= AUDIO_EVENT_ENTER_THRESHOLD) &&
               (candidate_score >= (stable_score + AUDIO_EVENT_SWITCH_MARGIN)))
      {
        s_stable_index = candidate_index;
        s_state = AUDIO_EVENT_CLASS;
      }
      else if (stable_score < AUDIO_EVENT_RELEASE_THRESHOLD)
      {
        if (candidate_score >= AUDIO_EVENT_ENTER_THRESHOLD)
        {
          s_stable_index = candidate_index;
          s_state = AUDIO_EVENT_CLASS;
        }
        else
        {
          s_stable_index = AUDIO_EVENT_NO_CLASS;
          s_state = AUDIO_EVENT_UNKNOWN;
        }
      }
      else
      {
        s_state = AUDIO_EVENT_CLASS;
      }
    }
  }

  result->state = s_state;
  result->decision_index = (s_state == AUDIO_EVENT_CLASS) ?
                           s_stable_index : AUDIO_EVENT_NO_CLASS;
  if (s_state == AUDIO_EVENT_CLASS)
  {
    result->decision_confidence = s_smoothed_scores[s_stable_index];
  }
  else if (s_state == AUDIO_EVENT_UNKNOWN)
  {
    result->decision_confidence = result->top_scores[0];
  }
  else
  {
    result->decision_confidence = 0.0F;
  }
  result->decision_changed = (previous_state != s_state) ||
                             (previous_index != s_stable_index);
}
