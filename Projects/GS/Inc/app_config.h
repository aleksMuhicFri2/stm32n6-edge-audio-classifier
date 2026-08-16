/**
  ******************************************************************************
  * @file    app_config.h
  * @author  GPM/AIS Application Team
  * @version V2.2.0
  * @date    12-Jan-2025
  * @brief   APP configuration
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2023 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */

#ifndef __APP_CONFIG_H__
#define __APP_CONFIG_H__

#include "logging.h"
#include "app_msg.h"

//#define LOG_LEVEL LOG_DEBUG
#define LOG_LEVEL LOG_INFO

#define INIT_TASK_CFG_HEAP_SIZE (60*1024)

#define INIT_THREAD_STACK_SIZE (4*1024)
#define INIT_THREAD_PRIO (0)

#define FREERTOS_AUDIO_PROC_THREAD_PRIO               (configMAX_PRIORITIES - 3)
#define FREERTOS_AUDIO_PROC_THREAD_STACK_SIZE         (configMINIMAL_STACK_SIZE * 4)  // example size
#define FREERTOS_AUDIO_PROC_THREAD_IN_QUEUE_SIZE      10U
#define FREERTOS_AUDIO_PROC_THREAD_IN_QUEUE_ITEM_SIZE (sizeof(AppMsg_t))

#define FREERTOS_AUDIO_ACQ_THREAD_PRIO               (configMAX_PRIORITIES - 4)
#define FREERTOS_AUDIO_ACQ_THREAD_STACK_SIZE         (configMINIMAL_STACK_SIZE * 4)
#define FREERTOS_AUDIO_ACQ_THREAD_IN_QUEUE_SIZE      10U
#define FREERTOS_AUDIO_ACQ_THREAD_IN_QUEUE_ITEM_SIZE (sizeof(AppMsg_t))

#define FREERTOS_LOAD_GEN_THREAD_PRIO                (configMAX_PRIORITIES - 2)
#define FREERTOS_LOAD_GEN_THREAD_STACK_SIZE          (configMINIMAL_STACK_SIZE * 4)
#define FREERTOS_LOAD_GEN_THREAD_IN_QUEUE_SIZE       10U
#define FREERTOS_LOAD_GEN_THREAD_IN_QUEUE_ITEM_SIZE  (sizeof(AppMsg_t))

/* in this version only  PREPROC_FLOAT_16 and  POSTPROC_FLOAT_16 are supported */
#define PREPROC_FLOAT_16
#define POSTPROC_FLOAT_16

#define my_printf LogInfo

/* UART usage/configuration */
#ifdef APP_DVFS
  #define USE_UART_BAUDRATE               (14400) /* 14400 is max value in DVFS mode */
#else
  #define USE_UART_BAUDRATE               (14400) /* can up set up upto 921600 */
#endif

#ifdef APP_BARE_METAL
#define APP_CONF_STR "Bare Metal"
#define CPU_STATS
#else
#define APP_CONF_STR "RTOS"
#endif

#define SEPARATION_LINE "------------------------------------------------------------\n\r"

/* Audio-event decision filter. Each model window covers 975 ms and a new
 * window starts every 480 ms. Thresholds
 * were initialized from the V5 development predictions and the non-final A02
 * board calibration. A separate lower release threshold prevents flicker. */
#define AUDIO_EVENT_EMA_ALPHA                      (0.65F)
#define AUDIO_EVENT_SWITCH_MARGIN                  (0.08F)
#define AUDIO_EVENT_SILENCE_TO_WAIT_FRAMES         (2U)
#define AUDIO_EVENT_HAZARD_TO_OTHER_HOLD_FRAMES    (4U)

#define AUDIO_EVENT_DOG_ENTER_THRESHOLD            (0.40F)
#define AUDIO_EVENT_DOG_RELEASE_THRESHOLD          (0.30F)
#define AUDIO_EVENT_DOG_CONFIRM_FRAMES             (1U)

#define AUDIO_EVENT_GLASS_ENTER_THRESHOLD          (0.60F)
#define AUDIO_EVENT_GLASS_RELEASE_THRESHOLD        (0.45F)
#define AUDIO_EVENT_GLASS_CONFIRM_FRAMES           (1U)

#define AUDIO_EVENT_GUNSHOT_ENTER_THRESHOLD        (0.65F)
#define AUDIO_EVENT_GUNSHOT_RELEASE_THRESHOLD      (0.50F)
#define AUDIO_EVENT_GUNSHOT_CONFIRM_FRAMES         (2U)

#define AUDIO_EVENT_OTHER_ENTER_THRESHOLD          (0.23F)
#define AUDIO_EVENT_OTHER_RELEASE_THRESHOLD        (0.18F)
#define AUDIO_EVENT_OTHER_CONFIRM_FRAMES           (3U)

#define AUDIO_EVENT_SIREN_ENTER_THRESHOLD          (0.65F)
#define AUDIO_EVENT_SIREN_RELEASE_THRESHOLD        (0.50F)
#define AUDIO_EVENT_SIREN_CONFIRM_FRAMES           (2U)

#define AUDIO_EVENT_SPEECH_ENTER_THRESHOLD         (0.40F)
#define AUDIO_EVENT_SPEECH_RELEASE_THRESHOLD       (0.30F)
#define AUDIO_EVENT_SPEECH_CONFIRM_FRAMES          (1U)

/* The score multiplier changes the ranking as well as the threshold decision.
 * It preserves short glass events that otherwise tend to rank behind other. */
#define AUDIO_EVENT_GLASS_SCORE_FACTOR             (1.225F)

#ifndef USE_NPU_CACHE
  #define USE_NPU_CACHE 1
#endif

/*
#define LOAD_GEN_NB_RUN     (100)
#define LOAD_GEN_TIME_SLICE (100)
#define LOAD_GEN_DUTY_CYCLE (20)
*/
/*
#define RECORD
#define PLAYBACK
*/
#if defined(RECORD) || defined(PLAYBACK)
#undef TEST
#define TEST
#define DUMP_NB 10
#endif

#endif /* __APP_CONFIG_H__ */
