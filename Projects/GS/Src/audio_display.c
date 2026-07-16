/**
  ******************************************************************************
  * @file    audio_display.c
  * @brief   Lightweight detected-sound display for the STM32N6570-DK.
  *
  * The framebuffer is RGB565 across AXI SRAM3/SRAM4. The implementation uses the
  * board panel timing and GPIO mapping from ST's STM32N6570-DK BSP, while
  * keeping the audio demo independent from TouchGFX during this first UI step.
  ******************************************************************************
  */

#include "audio_display.h"

#include <stdio.h>
#include <string.h>

#include "stm32n6xx_hal.h"
#include "stm32n6570_discovery_conf.h"
#include "mcu_cache.h"

#define DISPLAY_WIDTH             800U
#define DISPLAY_HEIGHT            480U
#define DISPLAY_BYTES_PER_PIXEL   2U
#define DISPLAY_FB_BYTES          (DISPLAY_WIDTH * DISPLAY_HEIGHT * DISPLAY_BYTES_PER_PIXEL)

#define COLOR_BACKGROUND          0x0861U
#define COLOR_HEADER              0x01EBU
#define COLOR_CARD                0x10A2U
#define COLOR_WHITE               0xFFFFU
#define COLOR_MUTED               0xBDF7U
#define COLOR_GREEN               0x07E0U
#define COLOR_ORANGE              0xFD20U

typedef struct
{
  char character;
  uint8_t rows[7];
} Glyph5x7_t;

static const Glyph5x7_t s_glyphs[] =
{
  {' ', {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}},
  {'%', {0x19, 0x19, 0x02, 0x04, 0x08, 0x13, 0x13}},
  {'-', {0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00}},
  {'.', {0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C}},
  {':', {0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x00}},
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

static volatile uint16_t *const s_framebuffer =
    (volatile uint16_t *)LCD_LAYER_0_ADDRESS;
static bool s_display_ready;
static char s_last_class[32];
static uint32_t s_last_percent = 101U;

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

static void fill_rect(uint32_t x, uint32_t y, uint32_t width, uint32_t height, uint16_t color)
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

static void draw_character(uint32_t x, uint32_t y, char character, uint32_t scale, uint16_t color)
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

static void draw_text(uint32_t x, uint32_t y, const char *text, uint32_t scale, uint16_t color)
{
  while (*text != '\0')
  {
    draw_character(x, y, *text, scale, color);
    x += 6U * scale;
    text++;
  }
}

static void draw_text_centered(uint32_t y, const char *text, uint32_t scale, uint16_t color)
{
  uint32_t width = (uint32_t)strlen(text) * 6U * scale;
  if (width >= scale)
  {
    width -= scale;
  }
  draw_text((width < DISPLAY_WIDTH) ? ((DISPLAY_WIDTH - width) / 2U) : 0U,
            y, text, scale, color);
}

static void clean_framebuffer(void)
{
  mcu_cache_clean_range(LCD_LAYER_0_ADDRESS, LCD_LAYER_0_ADDRESS + DISPLAY_FB_BYTES);
  __DSB();
}

static bool configure_panel(void)
{
  GPIO_InitTypeDef gpio = {0};
  RCC_OscInitTypeDef oscillator = {0};
  RCC_PeriphCLKInitTypeDef peripheral_clock = {0};

  /* The audio application leaves PLL4 disabled.  The DK display pixel clock
   * is IC16 = PLL4 / 2, so enable the same 50 MHz PLL4 configuration used by
   * ST's STM32N6570-DK image-classification example before releasing LTDC. */
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

  gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_2 | GPIO_PIN_7 | GPIO_PIN_8 | GPIO_PIN_15;
  HAL_GPIO_Init(GPIOA, &gpio);
  gpio.Pin = GPIO_PIN_2 | GPIO_PIN_4 | GPIO_PIN_11 | GPIO_PIN_12 | GPIO_PIN_13 |
             GPIO_PIN_14 | GPIO_PIN_15;
  HAL_GPIO_Init(GPIOB, &gpio);
  gpio.Pin = GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_15;
  HAL_GPIO_Init(GPIOD, &gpio);
  gpio.Pin = GPIO_PIN_11;
  HAL_GPIO_Init(GPIOE, &gpio);
  gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_6 | GPIO_PIN_8 | GPIO_PIN_11 | GPIO_PIN_12;
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

  /* RK050HR18: sync, back porch, active area, total area. */
  LTDC->GCR &= ~(LTDC_GCR_HSPOL | LTDC_GCR_VSPOL | LTDC_GCR_DEPOL | LTDC_GCR_PCPOL);
  LTDC->SSCR = (3U << 16U) | 3U;
  LTDC->BPCR = (7U << 16U) | 7U;
  LTDC->AWCR = (807U << 16U) | 487U;
  LTDC->TWCR = (811U << 16U) | 491U;
  LTDC->BCCR = 0U;

  LTDC_Layer1->WHPCR = (807U << 16U) | 8U;
  LTDC_Layer1->WVPCR = (487U << 16U) | 8U;
  LTDC_Layer1->PFCR = 4U; /* RGB565 */
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

  /* The audio example does not normally use LTDC, so its RIF resources are
   * not opened by the base application. This must run before IAC_Config(),
   * matching the ordering in ST's STM32N6570-DK display examples. */
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
  s_display_ready = false;
  s_last_class[0] = '\0';
  s_last_percent = 101U;

  fill_rect(0U, 0U, DISPLAY_WIDTH, DISPLAY_HEIGHT, COLOR_BACKGROUND);
  fill_rect(0U, 0U, DISPLAY_WIDTH, 82U, COLOR_HEADER);
  draw_text_centered(14U, "EDGE AUDIO RADAR", 5U, COLOR_WHITE);
  draw_text_centered(92U, "STM32N6  NEURAL ART", 2U, COLOR_MUTED);
  fill_rect(28U, 125U, 744U, 294U, COLOR_CARD);
  fill_rect(48U, 145U, 14U, 14U, COLOR_GREEN);
  draw_text(76U, 143U, "LISTENING", 2U, COLOR_GREEN);
  draw_text_centered(182U, "DETECTED SOUND", 3U, COLOR_MUTED);
  draw_text_centered(244U, "WAITING", 7U, COLOR_WHITE);
  draw_text_centered(340U, "CONFIDENCE: --", 3U, COLOR_ORANGE);
  draw_text_centered(440U, "BARE METAL AUDIO EVENT DETECTION", 2U, COLOR_MUTED);
  clean_framebuffer();

  s_display_ready = configure_panel();
  return s_display_ready;
}

void AudioDisplay_Update(const char *class_name, float confidence)
{
  char label[32];
  char confidence_text[32];
  uint32_t percent;

  if ((!s_display_ready) || (class_name == NULL))
  {
    return;
  }

  percent = (confidence <= 0.0F) ? 0U :
            ((confidence >= 1.0F) ? 100U : (uint32_t)(confidence * 100.0F + 0.5F));
  (void)snprintf(label, sizeof(label), "%s", class_name);
  if ((strcmp(label, s_last_class) == 0) && (percent == s_last_percent))
  {
    return;
  }

  (void)snprintf(s_last_class, sizeof(s_last_class), "%s", label);
  s_last_percent = percent;

  fill_rect(45U, 220U, 710U, 150U, COLOR_CARD);
  draw_text_centered(244U, label, 7U, COLOR_WHITE);
  (void)snprintf(confidence_text, sizeof(confidence_text), "CONFIDENCE: %lu%%",
                 (unsigned long)percent);
  draw_text_centered(340U, confidence_text, 3U, COLOR_ORANGE);
  clean_framebuffer();
}
