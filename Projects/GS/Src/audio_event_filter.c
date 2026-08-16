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

#if CTRL_X_CUBE_AI_MODEL_DOG_CLASS_INDEX >= CTRL_X_CUBE_AI_MODEL_CLASS_NUMBER
#error "Dog class index must reference a configured model output"
#endif

#if CTRL_X_CUBE_AI_MODEL_SPEECH_CLASS_INDEX >= CTRL_X_CUBE_AI_MODEL_CLASS_NUMBER
#error "Speech class index must reference a configured model output"
#endif

#if CTRL_X_CUBE_AI_MODEL_THUNDER_CLASS_INDEX >= CTRL_X_CUBE_AI_MODEL_CLASS_NUMBER
#error "Thunder class index must reference a configured model output"
#endif

#if CTRL_X_CUBE_AI_MODEL_OTHER_CLASS_INDEX >= CTRL_X_CUBE_AI_MODEL_CLASS_NUMBER
#error "Other class index must reference a configured model output"
#endif

#if CTRL_X_CUBE_AI_MODEL_GLASS_CLASS_INDEX >= CTRL_X_CUBE_AI_MODEL_CLASS_NUMBER
#error "Glass class index must reference a configured model output"
#endif

#if CTRL_X_CUBE_AI_MODEL_GUNSHOT_CLASS_INDEX >= CTRL_X_CUBE_AI_MODEL_CLASS_NUMBER
#error "Gunshot class index must reference a configured model output"
#endif

#if CTRL_X_CUBE_AI_MODEL_SIREN_CLASS_INDEX >= CTRL_X_CUBE_AI_MODEL_CLASS_NUMBER
#error "Siren class index must reference a configured model output"
#endif

static float s_smoothed_scores[CTRL_X_CUBE_AI_MODEL_CLASS_NUMBER];
static bool s_scores_initialized;
static uint32_t s_frame_index;
static uint32_t s_silent_frames;
static uint32_t s_candidate_frames[CTRL_X_CUBE_AI_MODEL_CLASS_NUMBER];
static uint32_t s_hazard_to_other_hold_frames;
static uint32_t s_stable_index = AUDIO_EVENT_NO_CLASS;
static AudioEventState_t s_state = AUDIO_EVENT_WAITING;

static bool is_hazard_class(uint32_t class_index)
{
  return (class_index < CTRL_X_CUBE_AI_MODEL_CLASS_NUMBER) &&
         (class_index != CTRL_X_CUBE_AI_MODEL_OTHER_CLASS_INDEX) &&
         (class_index != CTRL_X_CUBE_AI_MODEL_SPEECH_CLASS_INDEX) &&
         (class_index != CTRL_X_CUBE_AI_MODEL_THUNDER_CLASS_INDEX);
}

static float calibrated_score(uint32_t class_index, float score)
{
  if (class_index == CTRL_X_CUBE_AI_MODEL_GLASS_CLASS_INDEX)
  {
    score *= AUDIO_EVENT_GLASS_SCORE_FACTOR;
  }
  return (score > 1.0F) ? 1.0F : score;
}

static float system_score(uint32_t class_index,
                          const float *model_scores,
                          uint32_t class_count)
{
  float score = model_scores[class_index];

  /* Thunder is no longer a product output. The neural network remains frozen,
   * so its thunder probability is marginalized into the broader Other class
   * before smoothing, ranking and threshold decisions. This gives six visible
   * system classes without retraining or discarding probability mass. */
  if (class_index == CTRL_X_CUBE_AI_MODEL_THUNDER_CLASS_INDEX)
  {
    score = 0.0F;
  }
  else if ((class_index == CTRL_X_CUBE_AI_MODEL_OTHER_CLASS_INDEX) &&
           (CTRL_X_CUBE_AI_MODEL_THUNDER_CLASS_INDEX < class_count))
  {
    score += model_scores[CTRL_X_CUBE_AI_MODEL_THUNDER_CLASS_INDEX];
  }

  return calibrated_score(class_index, score);
}

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

static float enter_threshold(uint32_t class_index)
{
  switch (class_index)
  {
    case CTRL_X_CUBE_AI_MODEL_DOG_CLASS_INDEX:
      return AUDIO_EVENT_DOG_ENTER_THRESHOLD;
    case CTRL_X_CUBE_AI_MODEL_GLASS_CLASS_INDEX:
      return AUDIO_EVENT_GLASS_ENTER_THRESHOLD;
    case CTRL_X_CUBE_AI_MODEL_GUNSHOT_CLASS_INDEX:
      return AUDIO_EVENT_GUNSHOT_ENTER_THRESHOLD;
    case CTRL_X_CUBE_AI_MODEL_OTHER_CLASS_INDEX:
      return AUDIO_EVENT_OTHER_ENTER_THRESHOLD;
    case CTRL_X_CUBE_AI_MODEL_SIREN_CLASS_INDEX:
      return AUDIO_EVENT_SIREN_ENTER_THRESHOLD;
    case CTRL_X_CUBE_AI_MODEL_SPEECH_CLASS_INDEX:
      return AUDIO_EVENT_SPEECH_ENTER_THRESHOLD;
    default:
      return 1.0F;
  }
}

static float release_threshold(uint32_t class_index)
{
  switch (class_index)
  {
    case CTRL_X_CUBE_AI_MODEL_DOG_CLASS_INDEX:
      return AUDIO_EVENT_DOG_RELEASE_THRESHOLD;
    case CTRL_X_CUBE_AI_MODEL_GLASS_CLASS_INDEX:
      return AUDIO_EVENT_GLASS_RELEASE_THRESHOLD;
    case CTRL_X_CUBE_AI_MODEL_GUNSHOT_CLASS_INDEX:
      return AUDIO_EVENT_GUNSHOT_RELEASE_THRESHOLD;
    case CTRL_X_CUBE_AI_MODEL_OTHER_CLASS_INDEX:
      return AUDIO_EVENT_OTHER_RELEASE_THRESHOLD;
    case CTRL_X_CUBE_AI_MODEL_SIREN_CLASS_INDEX:
      return AUDIO_EVENT_SIREN_RELEASE_THRESHOLD;
    case CTRL_X_CUBE_AI_MODEL_SPEECH_CLASS_INDEX:
      return AUDIO_EVENT_SPEECH_RELEASE_THRESHOLD;
    default:
      return 1.0F;
  }
}

static uint32_t confirmation_frames(uint32_t class_index)
{
  switch (class_index)
  {
    case CTRL_X_CUBE_AI_MODEL_DOG_CLASS_INDEX:
      return AUDIO_EVENT_DOG_CONFIRM_FRAMES;
    case CTRL_X_CUBE_AI_MODEL_GLASS_CLASS_INDEX:
      return AUDIO_EVENT_GLASS_CONFIRM_FRAMES;
    case CTRL_X_CUBE_AI_MODEL_GUNSHOT_CLASS_INDEX:
      return AUDIO_EVENT_GUNSHOT_CONFIRM_FRAMES;
    case CTRL_X_CUBE_AI_MODEL_OTHER_CLASS_INDEX:
      return AUDIO_EVENT_OTHER_CONFIRM_FRAMES;
    case CTRL_X_CUBE_AI_MODEL_SIREN_CLASS_INDEX:
      return AUDIO_EVENT_SIREN_CONFIRM_FRAMES;
    case CTRL_X_CUBE_AI_MODEL_SPEECH_CLASS_INDEX:
      return AUDIO_EVENT_SPEECH_CONFIRM_FRAMES;
    default:
      return UINT32_MAX;
  }
}

static bool candidate_is_confirmed(uint32_t class_index, float score)
{
  if (class_index >= CTRL_X_CUBE_AI_MODEL_CLASS_NUMBER)
  {
    return false;
  }

  if (score < enter_threshold(class_index))
  {
    return false;
  }

  return s_candidate_frames[class_index] >= confirmation_frames(class_index);
}

void AudioEventFilter_Init(void)
{
  memset(s_smoothed_scores, 0, sizeof(s_smoothed_scores));
  s_scores_initialized = false;
  s_frame_index = 0U;
  s_silent_frames = 0U;
  memset(s_candidate_frames, 0, sizeof(s_candidate_frames));
  s_hazard_to_other_hold_frames = 0U;
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
      for (uint32_t index = 0U; index < class_count; index++)
      {
        s_smoothed_scores[index] = system_score(index, scores, class_count);
      }
      s_scores_initialized = true;
    }
    else
    {
      for (uint32_t index = 0U; index < class_count; index++)
      {
        s_smoothed_scores[index] =
            AUDIO_EVENT_EMA_ALPHA * system_score(index, scores, class_count) +
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
      s_hazard_to_other_hold_frames = 0U;
      s_stable_index = AUDIO_EVENT_NO_CLASS;
      s_state = AUDIO_EVENT_WAITING;
    }
  }

  rank_top_scores(class_count, result);

  if (audio_active)
  {
    const uint32_t candidate_index = result->top_indices[0];
    const float candidate_score = result->top_scores[0];
    if (is_hazard_class(s_stable_index))
    {
      if ((candidate_index == s_stable_index) &&
          (candidate_score >= release_threshold(s_stable_index)))
      {
        s_hazard_to_other_hold_frames =
            AUDIO_EVENT_HAZARD_TO_OTHER_HOLD_FRAMES;
      }
      else if (s_hazard_to_other_hold_frames > 0U)
      {
        s_hazard_to_other_hold_frames--;
      }
    }
    else
    {
      s_hazard_to_other_hold_frames = 0U;
    }
    /* Evidence is tracked independently for every class, even while that
     * class is briefly ranked second or third. It may only become the visible
     * decision when it returns to first place. */
    for (uint32_t index = 0U; index < class_count; index++)
    {
      /* Hazard evidence may be collected while a class is briefly second or
       * third. Other may build fallback evidence only when the top class does
       * not meet its own entry threshold, and never during the post-hazard
       * hold. This recognizes safe hard negatives without letting a frequent
       * runner-up score erase a newly detected event. */
      const bool top_class_meets_its_threshold =
          candidate_score >= enter_threshold(candidate_index);
      const bool other_fallback_allowed =
          (s_hazard_to_other_hold_frames == 0U) &&
          ((candidate_index == CTRL_X_CUBE_AI_MODEL_OTHER_CLASS_INDEX) ||
           !top_class_meets_its_threshold);
      const bool evidence_allowed =
          (index != CTRL_X_CUBE_AI_MODEL_OTHER_CLASS_INDEX) ||
          other_fallback_allowed;
      if (evidence_allowed &&
          (s_smoothed_scores[index] >= enter_threshold(index)))
      {
        const uint32_t required_frames = confirmation_frames(index);
        if (s_candidate_frames[index] < required_frames)
        {
          s_candidate_frames[index]++;
        }
      }
      else
      {
        s_candidate_frames[index] = 0U;
      }
    }

    const bool candidate_confirmed =
        candidate_is_confirmed(candidate_index, candidate_score);
    const bool speech_guard_active =
        (CTRL_X_CUBE_AI_MODEL_SPEECH_CLASS_INDEX < class_count) &&
        (s_smoothed_scores[CTRL_X_CUBE_AI_MODEL_SPEECH_CLASS_INDEX] >=
         AUDIO_EVENT_SPEECH_ENTER_THRESHOLD) &&
        (s_candidate_frames[CTRL_X_CUBE_AI_MODEL_SPEECH_CLASS_INDEX] >=
         AUDIO_EVENT_SPEECH_CONFIRM_FRAMES);
    const float other_score =
        s_smoothed_scores[CTRL_X_CUBE_AI_MODEL_OTHER_CLASS_INDEX];
    const bool other_confirmed =
        (other_score >= AUDIO_EVENT_OTHER_ENTER_THRESHOLD) &&
        (s_candidate_frames[CTRL_X_CUBE_AI_MODEL_OTHER_CLASS_INDEX] >=
         AUDIO_EVENT_OTHER_CONFIRM_FRAMES);
    const bool other_guard_active =
        other_confirmed &&
        (s_hazard_to_other_hold_frames == 0U) &&
        ((candidate_index == CTRL_X_CUBE_AI_MODEL_OTHER_CLASS_INDEX) ||
         (candidate_score < enter_threshold(candidate_index)));

    if (other_guard_active)
    {
      /* Other is informational and may replace a stale hazard only after it
       * has remained the strongest class for its full confirmation period. */
      s_stable_index = CTRL_X_CUBE_AI_MODEL_OTHER_CLASS_INDEX;
      s_state = AUDIO_EVENT_CLASS;
    }
    else if (speech_guard_active)
    {
      /* Speech is informational and may override a stale hazard as soon as
       * its own class-specific evidence requirement is satisfied. */
      s_stable_index = CTRL_X_CUBE_AI_MODEL_SPEECH_CLASS_INDEX;
      s_state = AUDIO_EVENT_CLASS;
    }
    else
    {
      if ((s_stable_index == CTRL_X_CUBE_AI_MODEL_SPEECH_CLASS_INDEX) ||
          (s_stable_index == CTRL_X_CUBE_AI_MODEL_OTHER_CLASS_INDEX))
      {
        s_stable_index = AUDIO_EVENT_NO_CLASS;
      }

      if (s_stable_index == AUDIO_EVENT_NO_CLASS)
      {
        if (candidate_confirmed)
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
          if (stable_score < release_threshold(s_stable_index))
          {
            s_stable_index = AUDIO_EVENT_NO_CLASS;
            s_state = AUDIO_EVENT_UNKNOWN;
          }
          else
          {
            s_state = AUDIO_EVENT_CLASS;
          }
        }
        else if (candidate_confirmed &&
                 (candidate_score >= (stable_score + AUDIO_EVENT_SWITCH_MARGIN)))
        {
          s_stable_index = candidate_index;
          s_state = AUDIO_EVENT_CLASS;
        }
        else if (stable_score < release_threshold(s_stable_index))
        {
          if (candidate_confirmed)
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
  }
  else
  {
    /* Confirmation must consist of consecutive active audio windows. */
    memset(s_candidate_frames, 0, sizeof(s_candidate_frames));
  }

  if ((s_stable_index != previous_index) && is_hazard_class(s_stable_index))
  {
    s_hazard_to_other_hold_frames =
        AUDIO_EVENT_HAZARD_TO_OTHER_HOLD_FRAMES;
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
