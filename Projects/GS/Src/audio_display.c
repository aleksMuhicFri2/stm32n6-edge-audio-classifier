/**
  ******************************************************************************
  * @file    audio_display.c
  * @brief   Simple acoustic safety display for the STM32N6570-DK.
  *
  * The dashboard renders into a hidden RGB565 framebuffer and presents it at
  * LTDC vertical blank. The visible interface deliberately contains only the
  * current result, its confidence, the three strongest predictions, and basic
  * device status. Event grouping and UART evidence remain available without
  * adding visual clutter.
  ******************************************************************************
  */

#include "audio_display.h"

#include <stdio.h>
#include <string.h>

#include "stm32n6xx_hal.h"
#include "stm32n6570_discovery_conf.h"
#include "mcu_cache.h"

#define DISPLAY_WIDTH                    800U
#define DISPLAY_HEIGHT                   480U
#define DISPLAY_BYTES_PER_PIXEL          2U
#define DISPLAY_FB_BYTES                 (DISPLAY_WIDTH * DISPLAY_HEIGHT * DISPLAY_BYTES_PER_PIXEL)
#define DASHBOARD_HISTORY_COUNT          3U
#define DASHBOARD_CLASS_SWITCH_CONFIRM_WINDOWS  2U

/* RGB565 product palette. */
#define COLOR_BACKGROUND                 0x0883U
#define COLOR_HEADER                     0x0927U
#define COLOR_CARD                       0x1148U
#define COLOR_CARD_ALT                   0x19AAU
#define COLOR_DIVIDER                    0x2A6DU
#define COLOR_WHITE                      0xFFFFU
#define COLOR_MUTED                      0x9D34U
#define COLOR_CYAN                       0x2E5BU
#define COLOR_GREEN                      0x36D2U
#define COLOR_ORANGE                     0xFD84U
#define COLOR_RED                        0xFA6BU
#define COLOR_BLUE                       0x5D5FU
#define COLOR_BAR_BACKGROUND             0x324EU

typedef struct
{
  char character;
  uint8_t rows[7];
} Glyph5x7_t;

typedef enum
{
  HAZARD_INFO = 0,
  HAZARD_WARNING,
  HAZARD_DANGER
} HazardLevel_t;

typedef struct
{
  const char *model_label;
  const char *display_label;
  HazardLevel_t hazard;
} SoundProfile_t;

typedef struct
{
  char label[24];
  uint32_t confidence_percent;
  uint32_t timestamp_seconds;
  HazardLevel_t hazard;
  bool valid;
} DashboardEvent_t;

static const Glyph5x7_t s_glyphs[] =
{
  {' ', {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}},
  {'%', {0x19, 0x19, 0x02, 0x04, 0x08, 0x13, 0x13}},
  {'-', {0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00}},
  {'.', {0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C}},
  {':', {0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x00}},
  {'/', {0x01, 0x02, 0x02, 0x04, 0x08, 0x08, 0x10}},
  {'0', {0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E}},
  {'1', {0x04, 0x0C, 0x14, 0x04, 0x04, 0x04, 0x1F}},
  {'2', {0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F}},
  {'3', {0x1E, 0x01, 0x01, 0x0E, 0x01, 0x01, 0x1E}},
  {'4', {0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02}},
  {'5', {0x1F, 0x10, 0x10, 0x1E, 0x01, 0x01, 0x1E}},
  {'6', {0x0E, 0x10, 0x10, 0x1E, 0x11, 0x11, 0x0E}},
  {'7', {0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08}},
  {'8', {0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E}},
  {'9', {0x0E, 0x11, 0x11, 0x0F, 0x01, 0x01, 0x0E}},
  {'A', {0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11}},
  {'B', {0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E}},
  {'C', {0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E}},
  {'D', {0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E}},
  {'E', {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F}},
  {'F', {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10}},
  {'G', {0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F}},
  {'H', {0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11}},
  {'I', {0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x1F}},
  {'J', {0x07, 0x02, 0x02, 0x02, 0x12, 0x12, 0x0C}},
  {'K', {0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11}},
  {'L', {0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F}},
  {'M', {0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11}},
  {'N', {0x11, 0x19, 0x19, 0x15, 0x13, 0x13, 0x11}},
  {'O', {0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E}},
  {'P', {0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10}},
  {'Q', {0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D}},
  {'R', {0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11}},
  {'S', {0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E}},
  {'T', {0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04}},
  {'U', {0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E}},
  {'V', {0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04}},
  {'W', {0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0A}},
  {'X', {0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11}},
  {'Y', {0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04}},
  {'Z', {0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F}}
};

static const SoundProfile_t s_sound_profiles[] =
{
  {"dog_bark",         "DOG BARK",         HAZARD_WARNING},
  {"glass_breaking",   "GLASS BREAKING",   HAZARD_DANGER},
  {"gunshot_gunfire",  "GUNSHOT",          HAZARD_DANGER},
  {"siren",            "EMERGENCY SIREN",   HAZARD_DANGER},
  {"speech",           "HUMAN SPEECH",      HAZARD_INFO},
  {"thunderstorm",     "THUNDERSTORM",      HAZARD_DANGER}
};

static volatile uint16_t *s_framebuffer =
    (volatile uint16_t *)LCD_LAYER_0_ADDRESS;
static uint32_t s_active_framebuffer_address = LCD_LAYER_0_ADDRESS;
static bool s_display_ready;
static volatile bool s_acknowledge_requested;
static volatile bool s_monitoring_enabled = true;
static bool s_session_active;
static bool s_session_recognized;
static char s_session_label[24];
static uint32_t s_session_percent;
static HazardLevel_t s_session_hazard;
static char s_challenger_label[24];
static uint32_t s_challenger_count;
static DashboardEvent_t s_history[DASHBOARD_HISTORY_COUNT];
static uint32_t s_event_count;
static uint32_t s_alert_count;
static bool s_alert_latched;
static char s_alert_label[24];
static HazardLevel_t s_alert_hazard;
static uint32_t s_last_render_second = UINT32_MAX;
static char s_last_decision[24];
static uint32_t s_last_decision_percent = UINT32_MAX;
static char s_last_top_labels[AUDIO_EVENT_TOP_COUNT][24];
static uint32_t s_last_top_percent[AUDIO_EVENT_TOP_COUNT] =
    {UINT32_MAX, UINT32_MAX, UINT32_MAX};

static uint32_t confidence_percent(float confidence)
{
  return (confidence <= 0.0F) ? 0U :
         ((confidence >= 1.0F) ? 100U :
          (uint32_t)(confidence * 100.0F + 0.5F));
}

static const uint8_t *glyph_rows(char character)
{
  for (uint32_t index = 0U; index < (sizeof(s_glyphs) / sizeof(s_glyphs[0])); index++)
  {
    if (s_glyphs[index].character == character)
    {
      return s_glyphs[index].rows;
    }
  }
  return s_glyphs[0].rows;
}

static char display_character(char character)
{
  if ((character >= 'a') && (character <= 'z'))
  {
    return (char)(character - ('a' - 'A'));
  }
  if (character == '_')
  {
    return ' ';
  }
  return character;
}

static void fill_rect(uint32_t x, uint32_t y, uint32_t width, uint32_t height,
                      uint16_t color)
{
  if ((x >= DISPLAY_WIDTH) || (y >= DISPLAY_HEIGHT))
  {
    return;
  }
  if ((x + width) > DISPLAY_WIDTH)
  {
    width = DISPLAY_WIDTH - x;
  }
  if ((y + height) > DISPLAY_HEIGHT)
  {
    height = DISPLAY_HEIGHT - y;
  }

  for (uint32_t row = 0U; row < height; row++)
  {
    volatile uint16_t *pixel = &s_framebuffer[(y + row) * DISPLAY_WIDTH + x];
    for (uint32_t column = 0U; column < width; column++)
    {
      pixel[column] = color;
    }
  }
}

static void outline_rect(uint32_t x, uint32_t y, uint32_t width, uint32_t height,
                         uint32_t thickness, uint16_t color)
{
  fill_rect(x, y, width, thickness, color);
  fill_rect(x, y + height - thickness, width, thickness, color);
  fill_rect(x, y, thickness, height, color);
  fill_rect(x + width - thickness, y, thickness, height, color);
}

static void draw_character(uint32_t x, uint32_t y, char character,
                           uint32_t scale, uint16_t color)
{
  const uint8_t *rows = glyph_rows(display_character(character));
  for (uint32_t row = 0U; row < 7U; row++)
  {
    for (uint32_t column = 0U; column < 5U; column++)
    {
      if ((rows[row] & (1U << (4U - column))) != 0U)
      {
        fill_rect(x + column * scale, y + row * scale, scale, scale, color);
      }
    }
  }
}

static void draw_text(uint32_t x, uint32_t y, const char *text,
                      uint32_t scale, uint16_t color)
{
  while (*text != '\0')
  {
    draw_character(x, y, *text, scale, color);
    x += 6U * scale;
    text++;
  }
}

static uint32_t text_width(const char *text, uint32_t scale)
{
  const uint32_t length = (uint32_t)strlen(text);
  return (length == 0U) ? 0U : (length * 6U * scale - scale);
}

static void draw_text_centered_in(uint32_t x, uint32_t width, uint32_t y,
                                  const char *text, uint32_t scale,
                                  uint16_t color)
{
  const uint32_t rendered_width = text_width(text, scale);
  draw_text(x + ((rendered_width < width) ? ((width - rendered_width) / 2U) : 0U),
            y, text, scale, color);
}

static void clean_framebuffer(void)
{
  const uint32_t address = (uint32_t)s_framebuffer;
  mcu_cache_clean_range(address, address + DISPLAY_FB_BYTES);
  __DSB();
}

static void select_inactive_framebuffer(void)
{
  const uint32_t inactive_address =
      (s_active_framebuffer_address == LCD_LAYER_0_ADDRESS) ?
      LCD_LAYER_1_ADDRESS : LCD_LAYER_0_ADDRESS;
  s_framebuffer = (volatile uint16_t *)inactive_address;
}

static void present_framebuffer(void)
{
  const uint32_t address = (uint32_t)s_framebuffer;

  /* VBR defers the address reload until vertical blank, so every visible LCD
   * scan uses one complete frame.  Updates arrive much slower than one frame,
   * therefore the next render cannot overtake this pending swap. */
  LTDC_Layer1->CFBAR = address;
  LTDC_Layer1->RCR = LTDC_LxRCR_VBR | LTDC_LxRCR_GRMSK;
  s_active_framebuffer_address = address;
}

static const SoundProfile_t *find_profile(const char *model_label)
{
  for (uint32_t index = 0U;
       index < (sizeof(s_sound_profiles) / sizeof(s_sound_profiles[0]));
       index++)
  {
    if (strcmp(model_label, s_sound_profiles[index].model_label) == 0)
    {
      return &s_sound_profiles[index];
    }
  }
  return NULL;
}

static const char *friendly_label(const char *model_label)
{
  const SoundProfile_t *profile = find_profile(model_label);
  return (profile == NULL) ? model_label : profile->display_label;
}

static HazardLevel_t hazard_for_label(const char *model_label)
{
  const SoundProfile_t *profile = find_profile(model_label);
  return (profile == NULL) ? HAZARD_INFO : profile->hazard;
}

static uint16_t hazard_color(HazardLevel_t hazard)
{
  if (hazard == HAZARD_DANGER)
  {
    return COLOR_RED;
  }
  if (hazard == HAZARD_WARNING)
  {
    return COLOR_ORANGE;
  }
  return COLOR_BLUE;
}

static void format_elapsed(uint32_t seconds, char *text, size_t text_size)
{
  const uint32_t minutes = (seconds / 60U) % 100U;
  const uint32_t remaining_seconds = seconds % 60U;
  (void)snprintf(text, text_size, "%02lu:%02lu",
                 (unsigned long)minutes,
                 (unsigned long)remaining_seconds);
}

static void add_event(const char *label, uint32_t percent, HazardLevel_t hazard,
                      uint32_t timestamp_seconds)
{
  for (uint32_t index = DASHBOARD_HISTORY_COUNT - 1U; index > 0U; index--)
  {
    s_history[index] = s_history[index - 1U];
  }

  (void)snprintf(s_history[0].label, sizeof(s_history[0].label), "%s", label);
  s_history[0].confidence_percent = percent;
  s_history[0].timestamp_seconds = timestamp_seconds;
  s_history[0].hazard = hazard;
  s_history[0].valid = true;
  s_event_count++;
  if (hazard != HAZARD_INFO)
  {
    s_alert_count++;
  }
}

static void revise_current_event(const char *label, uint32_t percent,
                                 HazardLevel_t hazard)
{
  if (!s_history[0].valid)
  {
    return;
  }

  if ((s_history[0].hazard == HAZARD_INFO) && (hazard != HAZARD_INFO))
  {
    s_alert_count++;
  }
  else if ((s_history[0].hazard != HAZARD_INFO) && (hazard == HAZARD_INFO) &&
           (s_alert_count > 0U))
  {
    s_alert_count--;
  }

  (void)snprintf(s_history[0].label, sizeof(s_history[0].label), "%s", label);
  s_history[0].confidence_percent = percent;
  s_history[0].hazard = hazard;
}

static void latch_alert(const char *label, HazardLevel_t hazard)
{
  if ((hazard == HAZARD_INFO) ||
      (s_alert_latched && (hazard < s_alert_hazard)))
  {
    return;
  }

  s_alert_latched = true;
  s_alert_hazard = hazard;
  (void)snprintf(s_alert_label, sizeof(s_alert_label), "%s", label);
}

static void update_audio_session(const char *decision_label, uint32_t percent,
                                 uint32_t now_seconds)
{
  const bool waiting = (strcmp(decision_label, "waiting") == 0);
  const bool unknown = (strcmp(decision_label, "unknown") == 0);

  if (waiting)
  {
    s_session_active = false;
    s_session_recognized = false;
    s_session_label[0] = '\0';
    s_session_percent = 0U;
    s_session_hazard = HAZARD_INFO;
    s_challenger_label[0] = '\0';
    s_challenger_count = 0U;
    return;
  }

  if (!s_session_active)
  {
    s_session_active = true;
    s_session_recognized = false;
    s_session_label[0] = '\0';
    s_session_percent = 0U;
    s_session_hazard = HAZARD_INFO;
    s_challenger_label[0] = '\0';
    s_challenger_count = 0U;
  }

  if (unknown)
  {
    s_challenger_label[0] = '\0';
    s_challenger_count = 0U;
    return;
  }

  const char *display_label = friendly_label(decision_label);
  const HazardLevel_t hazard = hazard_for_label(decision_label);

  if (!s_session_recognized)
  {
    s_session_recognized = true;
    (void)snprintf(s_session_label, sizeof(s_session_label), "%s", display_label);
    s_session_percent = percent;
    s_session_hazard = hazard;
    s_challenger_label[0] = '\0';
    s_challenger_count = 0U;
    add_event(display_label, percent, hazard, now_seconds);
    latch_alert(display_label, hazard);
  }
  else if (strcmp(s_session_label, display_label) == 0)
  {
    s_challenger_label[0] = '\0';
    s_challenger_count = 0U;
    if (percent > s_session_percent)
    {
      s_session_percent = percent;
      s_history[0].confidence_percent = percent;
    }
  }
  else
  {
    if (strcmp(s_challenger_label, display_label) == 0)
    {
      s_challenger_count++;
    }
    else
    {
      (void)snprintf(s_challenger_label, sizeof(s_challenger_label),
                     "%s", display_label);
      s_challenger_count = 1U;
    }

    if (s_challenger_count >= DASHBOARD_CLASS_SWITCH_CONFIRM_WINDOWS)
    {
      const bool revising_latched_alert =
          s_alert_latched && (strcmp(s_alert_label, s_session_label) == 0);
      (void)snprintf(s_session_label, sizeof(s_session_label), "%s", display_label);
      s_session_percent = percent;
      s_session_hazard = hazard;
      s_challenger_label[0] = '\0';
      s_challenger_count = 0U;
      revise_current_event(display_label, percent, hazard);
      if (revising_latched_alert && (hazard == HAZARD_INFO))
      {
        s_alert_latched = false;
        s_alert_label[0] = '\0';
        s_alert_hazard = HAZARD_INFO;
      }
      latch_alert(display_label, hazard);
    }
  }
}

static void draw_header(void)
{
  char uptime[20];
  char uptime_text[32];
  const uint32_t now_seconds = HAL_GetTick() / 1000U;

  fill_rect(0U, 0U, DISPLAY_WIDTH, 68U, COLOR_HEADER);
  draw_text(24U, 20U, "AUDIO HAZARD DETECTOR", 3U, COLOR_WHITE);

  format_elapsed(now_seconds, uptime, sizeof(uptime));
  (void)snprintf(uptime_text, sizeof(uptime_text), "UPTIME %s", uptime);
  draw_text(628U, 26U, uptime_text, 2U, COLOR_WHITE);
}

static void draw_confidence(uint32_t percent, uint16_t color)
{
  char text[12];
  const uint32_t bounded_percent = (percent > 100U) ? 100U : percent;
  const uint32_t bar_width = (530U * bounded_percent) / 100U;

  draw_text(48U, 236U, "CONFIDENCE", 1U, COLOR_MUTED);
  fill_rect(142U, 237U, 530U, 10U, COLOR_BAR_BACKGROUND);
  fill_rect(142U, 237U, bar_width, 10U, color);
  (void)snprintf(text, sizeof(text), "%lu%%", (unsigned long)bounded_percent);
  draw_text(696U, 233U, text, 2U, COLOR_WHITE);
}

static void draw_top_predictions(
    const char *const top_labels[AUDIO_EVENT_TOP_COUNT],
    const uint32_t top_percent[AUDIO_EVENT_TOP_COUNT])
{
  char percent_text[12];

  draw_text(44U, 309U, "TOP PREDICTIONS", 2U, COLOR_MUTED);
  for (uint32_t rank = 0U; rank < AUDIO_EVENT_TOP_COUNT; rank++)
  {
    const uint32_t y = 341U + rank * 31U;
    const uint32_t bounded_percent =
        (top_percent[rank] > 100U) ? 100U : top_percent[rank];
    const uint32_t bar_width = (230U * bounded_percent) / 100U;

    draw_text(44U, y, friendly_label(top_labels[rank]), 1U,
              (rank == 0U) ? COLOR_WHITE : COLOR_MUTED);
    fill_rect(164U, y, 230U, 9U, COLOR_BAR_BACKGROUND);
    fill_rect(164U, y, bar_width, 9U,
              (rank == 0U) ? COLOR_CYAN : COLOR_BLUE);
    (void)snprintf(percent_text, sizeof(percent_text), "%lu%%",
                   (unsigned long)bounded_percent);
    draw_text(430U, y, percent_text, 1U,
              (rank == 0U) ? COLOR_WHITE : COLOR_MUTED);
  }
}

static void draw_recent_predictions(void)
{
  char percent_text[12];
  char time_text[12];

  draw_text(536U, 309U, "RECENT DETECTIONS", 1U, COLOR_MUTED);
  for (uint32_t index = 0U; index < DASHBOARD_HISTORY_COUNT; index++)
  {
    const uint32_t y = 339U + index * 31U;
    if (s_history[index].valid)
    {
      format_elapsed(s_history[index].timestamp_seconds,
                     time_text, sizeof(time_text));
      (void)snprintf(percent_text, sizeof(percent_text), "%lu%%",
                     (unsigned long)s_history[index].confidence_percent);
      draw_text(536U, y, s_history[index].label, 1U, COLOR_WHITE);
      draw_text(722U, y, percent_text, 1U,
                hazard_color(s_history[index].hazard));
      draw_text(536U, y + 13U, time_text, 1U, COLOR_MUTED);
    }
    else
    {
      draw_text(536U, y + 5U, "NO RECENT DETECTION", 1U, COLOR_MUTED);
    }
  }
}

static void draw_live_card(
    const char *decision_label,
    uint32_t decision_percent,
    const char *const top_labels[AUDIO_EVENT_TOP_COUNT],
    const uint32_t top_percent[AUDIO_EVENT_TOP_COUNT])
{
  const bool waiting = (strcmp(decision_label, "waiting") == 0);
  const bool unknown = (strcmp(decision_label, "unknown") == 0);
  const char *primary_label = NULL;
  const char *subtitle = NULL;
  uint16_t accent = COLOR_GREEN;
  uint32_t label_scale = 5U;

  fill_rect(24U, 84U, 752U, 184U, COLOR_CARD);
  outline_rect(24U, 84U, 752U, 184U, 1U, COLOR_DIVIDER);
  draw_text(48U, 103U, "CURRENT SOUND", 2U, COLOR_MUTED);

  if (!s_monitoring_enabled)
  {
    primary_label = "PAUSED";
    subtitle = "PRESS USER1 TO RESUME MONITORING";
    accent = COLOR_ORANGE;
    decision_percent = 0U;
  }
  else if (!waiting)
  {
    const HazardLevel_t live_hazard = hazard_for_label(top_labels[0]);

    accent = unknown ? COLOR_ORANGE : hazard_color(live_hazard);
    primary_label = unknown ? "UNKNOWN" : friendly_label(top_labels[0]);
    subtitle = unknown ? "LOW CONFIDENCE - NOT CONFIRMED" : "DETECTED";
    decision_percent = top_percent[0];
  }
  else
  {
    primary_label = "WAITING";
    subtitle = "LISTENING FOR SOUND";
    decision_percent = 0U;
  }

  if (text_width(primary_label, label_scale) > 690U)
  {
    label_scale = 4U;
  }
  draw_text_centered_in(48U, 704U, 146U, primary_label, label_scale, accent);
  draw_text_centered_in(48U, 704U, 197U, subtitle, 1U, COLOR_MUTED);
  draw_confidence(decision_percent, accent);

  fill_rect(24U, 286U, 480U, 142U, COLOR_CARD);
  outline_rect(24U, 286U, 480U, 142U, 1U, COLOR_DIVIDER);
  draw_top_predictions(top_labels, top_percent);

  fill_rect(516U, 286U, 260U, 142U, COLOR_CARD);
  outline_rect(516U, 286U, 260U, 142U, 1U, COLOR_DIVIDER);
  draw_recent_predictions();
}

static void draw_footer(void)
{
  char footer_text[64];

  fill_rect(0U, 444U, DISPLAY_WIDTH, 36U, COLOR_HEADER);
  if (s_alert_latched)
  {
    (void)snprintf(footer_text, sizeof(footer_text),
                   "ALERT: %s / PRESS TAMP TO CLEAR", s_alert_label);
    draw_text_centered_in(0U, DISPLAY_WIDTH, 456U, footer_text, 1U,
                          hazard_color(s_alert_hazard));
  }
  else
  {
    draw_text_centered_in(0U, DISPLAY_WIDTH, 456U,
                          "USER1 PAUSE / RESUME     6 SOUND CLASSES",
                          1U, COLOR_MUTED);
  }
}

static void render_dashboard(
    const char *decision_label,
    uint32_t decision_percent,
    const char *const top_labels[AUDIO_EVENT_TOP_COUNT],
    const uint32_t top_percent[AUDIO_EVENT_TOP_COUNT])
{
  fill_rect(0U, 0U, DISPLAY_WIDTH, DISPLAY_HEIGHT, COLOR_BACKGROUND);
  draw_header();
  draw_live_card(decision_label, decision_percent, top_labels, top_percent);
  draw_footer();
  clean_framebuffer();
}

static bool configure_panel(void)
{
  GPIO_InitTypeDef gpio = {0};
  RCC_OscInitTypeDef oscillator = {0};
  RCC_PeriphCLKInitTypeDef peripheral_clock = {0};

  oscillator.OscillatorType = RCC_OSCILLATORTYPE_NONE;
  oscillator.PLL1.PLLState = RCC_PLL_NONE;
  oscillator.PLL2.PLLState = RCC_PLL_NONE;
  oscillator.PLL3.PLLState = RCC_PLL_NONE;
  oscillator.PLL4.PLLState = RCC_PLL_ON;
  oscillator.PLL4.PLLSource = RCC_PLLSOURCE_HSI;
  oscillator.PLL4.PLLM = 8U;
  oscillator.PLL4.PLLFractional = 0U;
  oscillator.PLL4.PLLN = 225U;
  oscillator.PLL4.PLLP1 = 6U;
  oscillator.PLL4.PLLP2 = 6U;
  if (HAL_RCC_OscConfig(&oscillator) != HAL_OK)
  {
    return false;
  }

  peripheral_clock.PeriphClockSelection = RCC_PERIPHCLK_LTDC;
  peripheral_clock.LtdcClockSelection = RCC_LTDCCLKSOURCE_IC16;
  peripheral_clock.ICSelection[RCC_IC16].ClockSelection = RCC_ICCLKSOURCE_PLL4;
  peripheral_clock.ICSelection[RCC_IC16].ClockDivider = 2U;
  if (HAL_RCCEx_PeriphCLKConfig(&peripheral_clock) != HAL_OK)
  {
    return false;
  }

  __HAL_RCC_LTDC_CLK_ENABLE();
  __HAL_RCC_LTDC_FORCE_RESET();
  __HAL_RCC_LTDC_RELEASE_RESET();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOE_CLK_ENABLE();
  __HAL_RCC_GPIOG_CLK_ENABLE();
  __HAL_RCC_GPIOH_CLK_ENABLE();
  __HAL_RCC_GPIOQ_CLK_ENABLE();

  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  gpio.Alternate = GPIO_AF14_LCD;
  gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_2 | GPIO_PIN_7 |
             GPIO_PIN_8 | GPIO_PIN_15;
  HAL_GPIO_Init(GPIOA, &gpio);
  gpio.Pin = GPIO_PIN_2 | GPIO_PIN_4 | GPIO_PIN_11 | GPIO_PIN_12 |
             GPIO_PIN_13 | GPIO_PIN_14 | GPIO_PIN_15;
  HAL_GPIO_Init(GPIOB, &gpio);
  gpio.Pin = GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_15;
  HAL_GPIO_Init(GPIOD, &gpio);
  gpio.Pin = GPIO_PIN_11;
  HAL_GPIO_Init(GPIOE, &gpio);
  gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_6 | GPIO_PIN_8 |
             GPIO_PIN_11 | GPIO_PIN_12;
  HAL_GPIO_Init(GPIOG, &gpio);
  gpio.Pin = GPIO_PIN_3 | GPIO_PIN_4 | GPIO_PIN_6;
  HAL_GPIO_Init(GPIOH, &gpio);

  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Pull = GPIO_NOPULL;
  gpio.Pin = GPIO_PIN_1;
  HAL_GPIO_Init(GPIOE, &gpio);
  gpio.Pin = GPIO_PIN_3 | GPIO_PIN_6;
  HAL_GPIO_Init(GPIOQ, &gpio);
  gpio.Pin = GPIO_PIN_13;
  HAL_GPIO_Init(GPIOG, &gpio);

  HAL_GPIO_WritePin(GPIOE, GPIO_PIN_1, GPIO_PIN_RESET);
  HAL_Delay(20U);
  HAL_GPIO_WritePin(GPIOE, GPIO_PIN_1, GPIO_PIN_SET);
  HAL_Delay(20U);

  LTDC->GCR &= ~(LTDC_GCR_HSPOL | LTDC_GCR_VSPOL |
                 LTDC_GCR_DEPOL | LTDC_GCR_PCPOL);
  LTDC->SSCR = (3U << 16U) | 3U;
  LTDC->BPCR = (7U << 16U) | 7U;
  LTDC->AWCR = (807U << 16U) | 487U;
  LTDC->TWCR = (811U << 16U) | 491U;
  LTDC->BCCR = 0U;

  LTDC_Layer1->WHPCR = (807U << 16U) | 8U;
  LTDC_Layer1->WVPCR = (487U << 16U) | 8U;
  LTDC_Layer1->PFCR = 4U;
  LTDC_Layer1->DCCR = 0U;
  LTDC_Layer1->CACR = 255U;
  LTDC_Layer1->BFCR = 0x0607U;
  LTDC_Layer1->CFBAR = LCD_LAYER_0_ADDRESS;
  LTDC_Layer1->CFBLR = (1600U << 16U) | 1607U;
  LTDC_Layer1->CFBLNR = DISPLAY_HEIGHT;
  LTDC_Layer1->CR = LTDC_LxCR_LEN;
  LTDC_Layer1->RCR = LTDC_LxRCR_IMR | LTDC_LxRCR_GRMSK;

  LTDC->GCR |= LTDC_GCR_LTDCEN;
  HAL_GPIO_WritePin(GPIOQ, GPIO_PIN_3 | GPIO_PIN_6, GPIO_PIN_SET);
  HAL_GPIO_WritePin(GPIOG, GPIO_PIN_13, GPIO_PIN_SET);
  return true;
}

void AudioDisplay_SecurityConfig(void)
{
  RIMC_MasterConfig_t master = {0};

  __HAL_RCC_RIFSC_CLK_ENABLE();
  master.MasterCID = RIF_CID_1;
  master.SecPriv = RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_PRIV;
  (void)HAL_RIF_RIMC_ConfigMasterAttributes(RIF_MASTER_INDEX_LTDC1, &master);
  (void)HAL_RIF_RIMC_ConfigMasterAttributes(RIF_MASTER_INDEX_LTDC2, &master);
  (void)HAL_RIF_RISC_SetSlaveSecureAttributes(
      RIF_RISC_PERIPH_INDEX_LTDC, RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_PRIV);
  (void)HAL_RIF_RISC_SetSlaveSecureAttributes(
      RIF_RISC_PERIPH_INDEX_LTDCL1, RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_PRIV);
  (void)HAL_RIF_RISC_SetSlaveSecureAttributes(
      RIF_RISC_PERIPH_INDEX_LTDCL2, RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_PRIV);
}

bool AudioDisplay_Init(void)
{
  static const char *initial_top_labels[AUDIO_EVENT_TOP_COUNT] =
      {"dog_bark", "glass_breaking", "gunshot_gunfire"};
  static const uint32_t initial_top_percent[AUDIO_EVENT_TOP_COUNT] = {0U, 0U, 0U};

  s_display_ready = false;
  s_acknowledge_requested = false;
  s_monitoring_enabled = true;
  s_framebuffer = (volatile uint16_t *)LCD_LAYER_0_ADDRESS;
  s_active_framebuffer_address = LCD_LAYER_0_ADDRESS;
  s_session_active = false;
  s_session_recognized = false;
  s_session_label[0] = '\0';
  s_session_percent = 0U;
  s_session_hazard = HAZARD_INFO;
  s_challenger_label[0] = '\0';
  s_challenger_count = 0U;
  memset(s_history, 0, sizeof(s_history));
  s_event_count = 0U;
  s_alert_count = 0U;
  s_alert_latched = false;
  s_alert_label[0] = '\0';
  s_alert_hazard = HAZARD_INFO;
  s_last_render_second = UINT32_MAX;
  s_last_decision[0] = '\0';
  s_last_decision_percent = UINT32_MAX;
  for (uint32_t rank = 0U; rank < AUDIO_EVENT_TOP_COUNT; rank++)
  {
    s_last_top_labels[rank][0] = '\0';
    s_last_top_percent[rank] = UINT32_MAX;
  }

  render_dashboard("waiting", 0U, initial_top_labels, initial_top_percent);
  s_display_ready = configure_panel();
  return s_display_ready;
}

void AudioDisplay_RequestAcknowledge(void)
{
  s_acknowledge_requested = true;
}

void AudioDisplay_SetMonitoring(bool enabled)
{
  s_monitoring_enabled = enabled;
  s_last_render_second = UINT32_MAX;
}

void AudioDisplay_Update(
    const char *decision_label,
    float decision_confidence,
    const char *const top_labels[AUDIO_EVENT_TOP_COUNT],
    const float top_scores[AUDIO_EVENT_TOP_COUNT],
    bool show_predictions)
{
  char current_label[24];
  uint32_t current_percent;
  uint32_t top_percent[AUDIO_EVENT_TOP_COUNT];
  const uint32_t now_seconds = HAL_GetTick() / 1000U;
  bool unchanged;
  bool force_render = false;

  (void)show_predictions;

  if ((!s_display_ready) || (decision_label == NULL) ||
      (top_labels == NULL) || (top_scores == NULL))
  {
    return;
  }

  if (s_acknowledge_requested)
  {
    s_acknowledge_requested = false;
    s_alert_latched = false;
    s_alert_label[0] = '\0';
    s_alert_hazard = HAZARD_INFO;
    force_render = true;
  }

  current_percent = confidence_percent(decision_confidence);
  (void)snprintf(current_label, sizeof(current_label), "%s", decision_label);
  update_audio_session(current_label, current_percent, now_seconds);

  unchanged = (!force_render) &&
              (strcmp(current_label, s_last_decision) == 0) &&
              (current_percent == s_last_decision_percent) &&
              (now_seconds == s_last_render_second);
  for (uint32_t rank = 0U; rank < AUDIO_EVENT_TOP_COUNT; rank++)
  {
    top_percent[rank] = confidence_percent(top_scores[rank]);
    unchanged = unchanged &&
                (strcmp(top_labels[rank], s_last_top_labels[rank]) == 0) &&
                (top_percent[rank] == s_last_top_percent[rank]);
  }

  if (unchanged)
  {
    return;
  }

  (void)snprintf(s_last_decision, sizeof(s_last_decision), "%s", current_label);
  s_last_decision_percent = current_percent;
  s_last_render_second = now_seconds;
  for (uint32_t rank = 0U; rank < AUDIO_EVENT_TOP_COUNT; rank++)
  {
    (void)snprintf(s_last_top_labels[rank], sizeof(s_last_top_labels[rank]),
                   "%s", top_labels[rank]);
    s_last_top_percent[rank] = top_percent[rank];
  }

  select_inactive_framebuffer();
  render_dashboard(current_label, current_percent, top_labels, top_percent);
  present_framebuffer();
}
