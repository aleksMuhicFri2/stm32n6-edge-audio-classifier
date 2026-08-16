/**
  ******************************************************************************
  * @file    audio_bm.c
  * @author  MCD Application Team
  * @version V2.2.0
  * @date    12-Jan-2025
  * @brief
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
/* Includes ------------------------------------------------------------------*/
#include "stm32n6xx_hal.h"
#include "stm32n6570_discovery.h"
#include "stm32n6570_discovery_xspi.h"
#include "stm32n6570_discovery_audio.h"
#include "app_config.h"
#include "system_clock_config.h"
#include "misc_toolbox.h"
#ifdef APP_DVFS
#include "pm_dvfs.h"
#endif
#ifdef CPU_STATS
#include "cpu_stats.h"
#endif
#include "AudioCapture_ring_buff.h"
#include "preproc_dpu.h"                           /* Preprocessing includes  */
#include "postproc_dpu.h"                          /* Postprocessing includes */
#include "ai_dpu.h"                                /* AI includes             */
#include "test.h"
#include "audio_bm.h"
#include "audio_display.h"
#include "audio_event_filter.h"

#include <stdio.h>
#include <string.h>

/* Private define ------------------------------------------------------------*/
#define AUDIO_ACQ_LEN     (CTRL_X_CUBE_AI_ACQ_LENGTH)
#if (CTRL_X_CUBE_AI_SPECTROGRAM_COL_OVL > 0)
#define AUDIO_ACQ_OFFSET  ((CTRL_X_CUBE_AI_SPECTROGRAM_COL_OVL*2 -1)*CTRL_X_CUBE_AI_SPECTROGRAM_HOP_LENGTH+CTRL_X_CUBE_AI_SPECTROGRAM_WINDOW_LENGTH)
#else
#define AUDIO_ACQ_OFFSET  (CTRL_X_CUBE_AI_SPECTROGRAM_WINDOW_LENGTH-CTRL_X_CUBE_AI_SPECTROGRAM_HOP_LENGTH)
#endif
#define AUDIO_OUT_FIRST   (CTRL_X_CUBE_AI_SPECTROGRAM_COL_OVL*CTRL_X_CUBE_AI_SPECTROGRAM_HOP_LENGTH)

/* Target-domain audio capture service. The first 2 MiB of HyperRAM are kept
 * below both display framebuffers (0x90E80000 and 0x90F3B800). The normal
 * product remains at 14400 baud; only an explicit PCM_CAPTURE_MODE command
 * enters this service and switches the serial link to 921600 baud. */
#define TARGET_CAPTURE_BUFFER_ADDRESS       (0x90000000UL)
#define TARGET_CAPTURE_SAMPLE_RATE          (16000UL)
#define TARGET_CAPTURE_MAX_SAMPLES          (960000UL)
#define TARGET_CAPTURE_HIGH_BAUDRATE         (921600UL)
#define TARGET_CAPTURE_COMMAND              "PCM_CAPTURE_MODE"
#define TARGET_CAPTURE_LINE_CAPACITY         (64U)
#define TARGET_CAPTURE_TX_CHUNK_BYTES        (4096U)
/* Instrumentation build used only while collecting target-domain audio. The
 * normal production image is restored after collection. */
#define TARGET_CAPTURE_AUTOSTART              (0U)

/* Private function prototypes -----------------------------------------------*/
static void IAC_Config(void);
static void MPU_Config(void);
static void Ext_Mem_Config(void);
static void Int_Mem_Config(void);
static void SleepClks_init(void);
static void Record_Init(void);
static void NPU_SettingsLog(void);
static bool TargetCapture_CommandReceived(void);
static void TargetCapture_Feed(const int16_t *samples, uint32_t sample_count);
static void TargetCapture_Service(void);

#ifdef CPU_STATS
static void printCpuStats(void);
#endif

#if (CTRL_X_CUBE_AI_AUDIO_OUT==COM_TYPE_HEADSET)
static void initAudioPlayBack(AudioBM_play_back_t *ctx_ptr);
static void AudioPlayBack(AudioBM_play_back_t *ctx_ptr, int16_t *pData, \
                                                uint16_t nbSamples);
static float vumeter(int16_t * pAudioSmp,int nb_sample);
#endif

/* Private variables ---------------------------------------------------------*/
static bool AudioProcIsOn;
static volatile bool AudioFilterResetRequested;
static volatile bool TargetCaptureActive;
static volatile bool TargetCaptureComplete;
static volatile bool TargetCaptureServiceMode;
static volatile uint32_t TargetCaptureRequestedSamples;
static volatile uint32_t TargetCaptureWrittenSamples;
static volatile bool TargetCaptureCommandReady;
static char TargetCaptureCommandBuffer[TARGET_CAPTURE_LINE_CAPACITY];
static uint32_t TargetCaptureCommandLength;
static uint8_t TargetCaptureRxByte;
static int16_t *const TargetCaptureBuffer =
    (int16_t *)TARGET_CAPTURE_BUFFER_ADDRESS;

#ifdef APP_BARE_METAL
static AudioBM_acq_t  audio_acq_ctx;
static AudioBM_proc_t audio_proc_ctx;
#endif
#if (CTRL_X_CUBE_AI_AUDIO_OUT==COM_TYPE_HEADSET)
int16_t  playback_buf[PLAYBACK_BUFFER_SIZE] __NON_CACHEABLE;
#endif

static const char *sAiAudioClassLabels[CTRL_X_CUBE_AI_MODEL_CLASS_NUMBER] = \
                                                 CTRL_X_CUBE_AI_MODEL_CLASS_LIST;

/**
  * @brief  Initializes the system according to the application
  *         system requirement.
  * @param  None
  * @retval None
  */
void init_bm(void)
{
  /* Power on ICACHE */
  MEMSYSCTL->MSCR |= MEMSYSCTL_MSCR_ICACTIVE_Msk;

  /* Set back system and CPU clock source to HSI */
  __HAL_RCC_CPUCLK_CONFIG(RCC_CPUCLKSOURCE_HSI);
  __HAL_RCC_SYSCLK_CONFIG(RCC_SYSCLKSOURCE_HSI);

  HAL_Init();

  SystemClock_Config_Full();

#ifdef APP_DVFS
  pm_init_dvfs();
#endif
  /* Force fusing of the OTP when using a Nucleo/DK board only */
#if (defined(USE_STM32N6xx_NUCLEO) || defined(USE_STM32N6570_DK))
  fuse_vddio();
#endif

  MPU_Config();
  Int_Mem_Config();
  Ext_Mem_Config();
  NPU_Config();
  AudioDisplay_SecurityConfig();
  IAC_Config();
  SCB_EnableICache();
  SCB_EnableDCache();
  port_dwt_init_imp();
  SleepClks_init(); /* configures for sleep */

  /* BSP inits */
  UART_Config();
  HAL_NVIC_SetPriority(USART1_IRQn, 5U, 0U);
  HAL_NVIC_EnableIRQ(USART1_IRQn);
  if (HAL_UART_Receive_IT(&UartHandle, &TargetCaptureRxByte, 1U) != HAL_OK)
  {
    Error_Handler();
  }
  BSP_PB_Init(BUTTON_USER1, BUTTON_MODE_EXTI);
  BSP_PB_Init(BUTTON_TAMP, BUTTON_MODE_EXTI);
  BSP_LED_Init(LED_GREEN);
  BSP_LED_Init(LED_RED);

  if (!AudioDisplay_Init())
  {
    my_printf("WARNING: LCD initialization failed; audio processing will continue.\r\n");
  }

  /* configuration information on console */
  displaySystemSetting();

  /* by default processing is active */
  AudioProcIsOn = true;
  AudioFilterResetRequested = false;
  TargetCaptureActive = false;
  TargetCaptureComplete = false;
  TargetCaptureServiceMode = false;
  TargetCaptureRequestedSamples = 0U;
  TargetCaptureWrittenSamples = 0U;
  TargetCaptureCommandLength = 0U;
  TargetCaptureCommandReady = false;
}

#ifdef APP_BARE_METAL
/**
  * @brief  main loop for bare metal implementation.
  * @param  None
  * @retval None
  */
void exec_bm(void)
{
  bool cont = true;
  time_stats_init();

  initAudioProc(&audio_proc_ctx);
  initAudioCapture(&audio_acq_ctx);
  startAudioCapture(&audio_acq_ctx);
#if TARGET_CAPTURE_AUTOSTART
  TargetCapture_Service();
#endif
  printHeader();

  while(cont)
  {
    __NOP(); /* to be resilient to gcc optim ... to investigate */
    if (TargetCapture_CommandReceived())
    {
      TargetCapture_Service();
    }
#ifdef  APP_LP
    HAL_SuspendTick();
    HAL_PWR_EnterSLEEPMode(0, PWR_SLEEPENTRY_WFI);
    HAL_ResumeTick();
#endif /* APP_LP */
     if (audio_acq_ctx.ring_buff.availableSamples >= AUDIO_ACQ_LEN)
     {
        cont = audio_process(&audio_acq_ctx,&audio_proc_ctx);
#ifdef CPU_STATS
        printCpuStats();
#endif
     }
  }
  stopAudioCapture();

#if (CTRL_X_CUBE_AI_AUDIO_OUT==COM_TYPE_HEADSET)
  stopAudioPlayBack();
#endif

  test_dump();
  my_printf("\n\r# End Processing\n\r");
}
#endif
/**
 * @brief  Initializes all Audio processing
 * @param  proc_ctx_ptr pointer to processing context
 * @retval None
 */
void initAudioProc(AudioBM_proc_t * ctx_ptr)
{
  /* init test facilities */
  test_init();
  /* get the AI model */
  AiDPULoadModel( &ctx_ptr->aiCtx);
  ctx_ptr->aiCtx.classes = sAiAudioClassLabels;
  ctx_ptr->ai_in_ptr = (int8_t *) ctx_ptr->aiCtx.p_stai_inputs[0];
  ctx_ptr->ai_out_ptr = (LL_Buffer_InfoTypeDef *) ctx_ptr->aiCtx.p_stai_outputs[0];

  /* clear input samples array ( get silence on first overlayed patch */
  memset(ctx_ptr->proc_buff,0,PATCH_LENGTH*sizeof(int16_t));
  /* Audio Preprocessing init */
  PreProc_DPUInit(&ctx_ptr->audioPreCtx);
  /* Audio Postprocessing init */
  PostProc_DPUInit(&ctx_ptr->audioPostCtx);
  AudioEventFilter_Init();
  /* transfer quantization parametres included in AI model to the Audio DPU   */
  ctx_ptr->audioPreCtx.output_Q_offset    = ctx_ptr->aiCtx.input_Q_offset;
  ctx_ptr->audioPreCtx.output_Q_inv_scale =
            (PREPROC_FLOAT_T) ctx_ptr->aiCtx.input_Q_inv_scale;
  ctx_ptr->audioPreCtx.quant.output_Q_inv_scale = ctx_ptr->audioPreCtx.output_Q_inv_scale;
  ctx_ptr->audioPreCtx.quant.output_Q_offset = ctx_ptr->audioPreCtx.output_Q_offset;
  ctx_ptr->cnt = 0;
#if (CTRL_X_CUBE_AI_AUDIO_OUT==COM_TYPE_HEADSET)
  initAudioPlayBack(&ctx_ptr->audioPlayBackCtx);
#endif
}

/**
  * @brief  audio processing - pre, main, and post
  * @param  acq_ctx_ptr pointer to acquisition context
  * @param  proc_ctx_ptr pointer to processing context
  * @retval true if continue condition is met
  */
bool audio_process(AudioBM_acq_t * acq_ctx_ptr,AudioBM_proc_t * proc_ctx_ptr)
{

#if (CTRL_X_CUBE_AI_MODEL_OUTPUT_1 == CTRL_AI_CLASS_DISTRIBUTION )
  bool isNotSilence, isPlayback;
#endif

  uint8_t *proc_buf = (uint8_t *) proc_ctx_ptr->proc_buff;
  uint8_t *proc_buf_ovl = (uint8_t *) (&proc_ctx_ptr->proc_buff[AUDIO_ACQ_LEN]);
  uint8_t *acq_buf = (uint8_t *) (&proc_ctx_ptr->proc_buff[AUDIO_ACQ_OFFSET]);
  bool cont = true;

#ifdef APP_DVFS
  pm_set_opp_min(OPP_MAX);
#endif /* APP_DVFS */

  /* Prepare overlapping samples from the previous patch. With the 480 ms
   * inference step the source and destination overlap, so memmove is required
   * here; memcpy would have undefined behaviour. */
  memmove(proc_buf,proc_buf_ovl,AUDIO_ACQ_OFFSET*sizeof(int16_t));

  /* Audio samples acquisition */
  AudioCapture_ring_buff_consume(acq_buf,&acq_ctx_ptr->ring_buff,AUDIO_ACQ_LEN);
#ifdef APP_LP
  NPU_SRAM_on();
#endif /* APP_LP */

  /* Audio pre processing */
  PreProc_DPU(&proc_ctx_ptr->audioPreCtx, proc_buf, proc_ctx_ptr->ai_in_ptr );

#if (CTRL_X_CUBE_AI_MODEL_OUTPUT_1 == CTRL_AI_CLASS_DISTRIBUTION )
  isNotSilence = (proc_ctx_ptr->audioPreCtx.S_Spectr.spectro_sum > CTRL_X_CUBE_AI_SPECTROGRAM_SILENCE_THR);
  isPlayback = test_probe_in(&proc_ctx_ptr->aiCtx,&proc_ctx_ptr->audioPreCtx);
#endif

#ifdef APP_LP
  NPU_on();
#endif /* APP_LP */
  /* AI processing */
  AiDPUProcess(&proc_ctx_ptr->aiCtx);

#if (CTRL_X_CUBE_AI_MODEL_OUTPUT_1 == CTRL_AI_CLASS_DISTRIBUTION )
  printInferenceResults(&proc_ctx_ptr->aiCtx, isNotSilence || isPlayback,
                        proc_ctx_ptr->audioPreCtx.S_Spectr.spectro_sum);
#endif

#if (CTRL_X_CUBE_AI_POSTPROC==CTRL_AI_ISTFT)
  PostProc_DPU(&proc_ctx_ptr->audioPostCtx,
      proc_ctx_ptr->audioPreCtx.pCplxSpectrum,
      (float32_t *) proc_ctx_ptr->ai_out_ptr,
      proc_ctx_ptr->audio_out);
#endif

#if (CTRL_X_CUBE_AI_AUDIO_OUT==COM_TYPE_HEADSET)
  int16_t * audioPtr = (AudioProcIsOn) ?
      &proc_ctx_ptr->audio_out[AUDIO_OUT_FIRST] : (int16_t *)acq_buf ;
  AudioPlayBack(&proc_ctx_ptr->audioPlayBackCtx, audioPtr , AUDIO_ACQ_LEN);
#endif

#ifdef APP_LP
  NPU_off();
#endif /* APP_LP */

#ifdef APP_DVFS 
  pm_set_opp_min(OPP_MIN);
#endif 

  BSP_LED_Toggle(LED_GREEN);
  
  return cont;
}

/**
* @brief  Initializes Audio capture from microphone
* @param  acq_ctx_ptr pointer to acquisition context
* @retval None
*/
void initAudioCapture(AudioBM_acq_t *ctx_ptr)
{
  ctx_ptr->ring_buff.nbSamples = ((PATCH_LENGTH / CAPTURE_BUFFER_SIZE) + 1 ) \
                                                        * CAPTURE_BUFFER_SIZE ;
  ctx_ptr->ring_buff.nbBytesPerSample = 2;
  ctx_ptr->ring_buff.nbFrames = 2;
  AudioCapture_ring_buff_alloc(&ctx_ptr->ring_buff);
  /* Initialize record */
  Record_Init();
}

/**
* @brief  Starts Audio capture from microphone
* @param  acq_ctx_ptr pointer to acquisition context
* @retval None
*/
void startAudioCapture(AudioBM_acq_t * ctx_ptr)
{
  /* Start record */
  if (BSP_ERROR_NONE != BSP_AUDIO_IN_Record(1, (uint8_t *) ctx_ptr->acq_buf,
                                         CAPTURE_BUFFER_SIZE * sizeof(int16_t)))
  {
    Error_Handler();
  }
}

#if (CTRL_X_CUBE_AI_AUDIO_OUT==COM_TYPE_HEADSET)
/**
* @brief  Stops Audio Playback
* @param  None
* @retval None
*/
void stopAudioPlayBack(void)
{
  BSP_AUDIO_OUT_Stop(1);
}
#endif

/**
* @brief  Stops Audio Capture
* @param  None
* @retval None
*/
void stopAudioCapture(void)
{
  BSP_AUDIO_IN_Stop(1);
}

#ifdef APP_LP

/**
* @brief  NPU (Neural Processing Unit) RAM power on.
* @param  None.
* @retval None.
*/
void NPU_SRAM_on(void)
{
  RAMCFG_HandleTypeDef hramcfg = {0};
  hramcfg.Instance =  RAMCFG_SRAM6_AXI;
  HAL_RAMCFG_EnableAXISRAM(&hramcfg);
  __HAL_RCC_AXISRAM6_MEM_CLK_ENABLE();
  __HAL_RCC_CACHEAXIRAM_MEM_CLK_ENABLE();
}

/**
* @brief  NPU (Neural Processing Unit) power ram off.
* @param  None.
* @retval None.
*/
void NPU_SRAM_off(void)
{
  RAMCFG_HandleTypeDef hramcfg = {0};
  hramcfg.Instance =  RAMCFG_SRAM6_AXI;
  HAL_RAMCFG_DisableAXISRAM(&hramcfg);
  __HAL_RCC_AXISRAM6_MEM_CLK_DISABLE();
  __HAL_RCC_CACHEAXIRAM_MEM_CLK_DISABLE();
}

/**
* @brief  NPU (Neural Processing Unit) power on.
* @param  None.
* @retval None.
*/
void NPU_on(void)
{
  NPU_SRAM_on();
  NPU_Config();
  __HAL_RCC_XSPI2_CLK_ENABLE();
}

/**
* @brief  NPU (Neural Processing Unit) power off.
* @param  None.
* @retval None.
*/
void NPU_off(void)
{
  __HAL_RCC_NPU_CLK_DISABLE();
  __HAL_RCC_CACHEAXI_CLK_DISABLE();
  NPU_SRAM_off();
  __HAL_RCC_XSPI2_CLK_DISABLE();
}

#endif /* APP_LP */

#ifdef APP_DVFS
/**
  * @brief Initialize the UART MSP.
  * @param huart UART handle.
  * @retval None
  */
void HAL_UART_MspInit(UART_HandleTypeDef *huart)
{
  /* Prevent unused argument(s) compilation warning */
  UNUSED(huart);

  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_MSI;
  RCC_OscInitStruct.MSIState       = RCC_MSI_ON;
  RCC_OscInitStruct.MSIFrequency   = RCC_MSI_FREQ_4MHZ;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    /* Initialization Error */
    while(1);
  }

  RCC_PeriphCLKInitTypeDef PeriphClkInit = {0};
  /*  Select MSI for UART */
  PeriphClkInit.PeriphClockSelection = RCC_PERIPHCLK_USART1;
  PeriphClkInit.Usart1ClockSelection = RCC_USART1CLKSOURCE_MSI;
  if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInit) != HAL_OK)
  {
  __BKPT(0);
  }
}
#endif /* APP_DVFS */

void printHeader(void)
{
	my_printf(SEPARATION_LINE);
	my_printf("# Start Processing\n\r");
	my_printf(SEPARATION_LINE);

#if (CTRL_X_CUBE_AI_AUDIO_OUT==COM_TYPE_HEADSET)
	my_printf("| Vu meter          ");
#else
	my_printf("                    ");
#endif
#ifdef CPU_STATS
	my_printf("| Frame   |  Cpu  |  Pre |  AI  | Post |");
#endif
	my_printf("\r\n");
	printf("AED_CSV_HEADER,frame,audio_active,spectrogram_sum,decision,decision_confidence,"
	       "top1,top1_confidence,top2,top2_confidence,top3,top3_confidence,changed\r\n");
}

#ifdef CPU_STATS
void printCpuStats(void)
{
	/* display real time statistics */
	float pre_load = 100 * time_stats_get_avg(TIME_STAT_PRE_PROC)/CTRL_X_CUBE_AI_ACQ_LENGTH_MS;
	float ai_load = 100 * time_stats_get_avg(TIME_STAT_AI_PROC)/CTRL_X_CUBE_AI_ACQ_LENGTH_MS;
	float post_load = 100 * time_stats_get_avg(TIME_STAT_POST_PROC)/CTRL_X_CUBE_AI_ACQ_LENGTH_MS;
#if (CTRL_X_CUBE_AI_AUDIO_OUT!=COM_TYPE_HEADSET)
	my_printf("                    ");
#endif
	printf ("| %-8d|%6.2f%%|%6.2f|%6.2f|%6.2f|\r",time_stats_get_cnt(TIME_STAT_AI_PROC),pre_load+ai_load+post_load,pre_load, ai_load, post_load);
	fflush(stdout);
}
#endif

#if (CTRL_X_CUBE_AI_MODEL_OUTPUT_1 == CTRL_AI_CLASS_DISTRIBUTION )
/**
* @brief  Displays Inference processing outputs
* @param  None
* @retval None
*/
void printInferenceResults(const AIProcCtx_t* AIProcCtx, bool audio_active,
                           float spectrogram_sum)
{
  /**
  * Specifies the labels for the classes of the demo.
  */

  const char* sAiClassLabels[CTRL_X_CUBE_AI_MODEL_CLASS_NUMBER]  = CTRL_X_CUBE_AI_MODEL_CLASS_LIST;
  float *nn_out =  (float *) AIProcCtx->p_stai_outputs[0];
  AudioEventResult_t result;
  const char *top_labels[AUDIO_EVENT_TOP_COUNT];
  const char *decision_label;

  if (AudioFilterResetRequested)
  {
    AudioFilterResetRequested = false;
    AudioEventFilter_Init();
  }

  if (!AudioProcIsOn)
  {
    static const char *paused_labels[AUDIO_EVENT_TOP_COUNT] =
        {"unknown", "unknown", "unknown"};
    static const float paused_scores[AUDIO_EVENT_TOP_COUNT] =
        {0.0F, 0.0F, 0.0F};
    AudioDisplay_Update("waiting", 0.0F, paused_labels, paused_scores, false);
    return;
  }

  AudioEventFilter_Update(nn_out, CTRL_X_CUBE_AI_MODEL_CLASS_NUMBER,
                          audio_active, &result);

  for (uint32_t rank = 0U; rank < AUDIO_EVENT_TOP_COUNT; rank++)
  {
    top_labels[rank] = (result.top_indices[rank] == AUDIO_EVENT_NO_CLASS) ?
                       "unknown" : sAiClassLabels[result.top_indices[rank]];
  }

  if (result.state == AUDIO_EVENT_CLASS)
  {
    decision_label = sAiClassLabels[result.decision_index];
  }
  else if (result.state == AUDIO_EVENT_UNKNOWN)
  {
    decision_label = "unknown";
  }
  else
  {
    decision_label = "waiting";
  }
#ifdef CPU_STATS
   my_printf("\r\n");
#endif

  if (result.decision_changed)
  {
    my_printf("{\"class\":\"%s\"}\r\n", decision_label);
  }

  printf("AED_CSV,%lu,%u,%.2f,%s,%.4f,%s,%.4f,%s,%.4f,%s,%.4f,%u\r\n",
         (unsigned long)result.frame_index,
         result.audio_active ? 1U : 0U,
         (double)spectrogram_sum,
         decision_label,
         (double)result.decision_confidence,
         top_labels[0], (double)result.top_scores[0],
         top_labels[1], (double)result.top_scores[1],
         top_labels[2], (double)result.top_scores[2],
         result.decision_changed ? 1U : 0U);

  AudioDisplay_Update(decision_label, result.decision_confidence,
                      top_labels, result.top_scores,
                      result.state != AUDIO_EVENT_WAITING);

}

#endif

/**
* @brief  Displays System Settings
* @param  None
* @retval None
*/
void displaySystemSetting(void)
{
  my_printf("\n\r");
  my_printf(SEPARATION_LINE);
  my_printf("        System configuration (%s)\n\r",APP_CONF_STR);
  my_printf(SEPARATION_LINE);
  printf("\n\rLog Level: %s\n\n\r", getLogLevelStr(LOG_LEVEL));
  systemSettingLog();
  NPU_SettingsLog();
#if defined (APP_DVFS) || defined (APP_LP)
  my_printf("\r\nLow Power Options:");
#ifdef APP_LP
  my_printf("\r\n DPS");
#endif /* APP_LP */
#ifdef APP_DVFS  
  my_printf("\r\n DFVS");
#endif /* APP_DFVS */
  my_printf("\r\n");
#endif /* APP_DVFS || APP_LP */
}

void toggle_audio_proc(void)
{
  BSP_LED_Toggle(LED_RED);
  AudioProcIsOn = !AudioProcIsOn;
  AudioFilterResetRequested = true;
  AudioDisplay_SetMonitoring(AudioProcIsOn);
}

/**
* @brief  Manages the BSP audio half transfer.
* @param  pHdle pointer to audio ring buffer handle
* @param  pData pointer to audio acquired samples buffer
* @param  half_buf id ( 0 or 1 )
* @retval None.
*/
void AudioCapture_half_buf_cb(AudioCapture_ring_buff_t *pHdle, int16_t *pData, uint8_t half_buf)
{
  int16_t *in_p = pData + half_buf * (CAPTURE_BUFFER_SIZE/ 2);
  TargetCapture_Feed(in_p, CAPTURE_BUFFER_SIZE / 2U);
  if (!TargetCaptureServiceMode)
  {
    AudioCapture_ring_buff_feed(pHdle, (uint8_t *)in_p, CAPTURE_BUFFER_SIZE/ 2);
  }
}

#ifdef APP_BARE_METAL
/**
* @brief  Manage the BSP audio in transfer complete event.
* @param  Instance Audio in instance.
* @retval None.
*/
void BSP_AUDIO_IN_TransferComplete_CallBack(uint32_t Instance)
{
  if (Instance == 1U)
  {
    AudioCapture_half_buf_cb(&audio_acq_ctx.ring_buff, audio_acq_ctx.acq_buf, 1U);
  }
}

/**
* @brief  Manage the BSP audio in half transfer complete event.
* @param  Instance Audio in instance.
* @retval None.
*/
void BSP_AUDIO_IN_HalfTransfer_CallBack(uint32_t Instance)
{
  if (Instance == 1U)
  {
    AudioCapture_half_buf_cb(&audio_acq_ctx.ring_buff, audio_acq_ctx.acq_buf, 0U);
  }
}
#if (CTRL_X_CUBE_AI_AUDIO_OUT==COM_TYPE_HEADSET)
/**
  * @brief  Tx Transfer completed callbacks.
  * @param  None.
  * @retval None.
  */
void BSP_AUDIO_OUT_TransferComplete_CallBack(uint32_t Instance)
{
  AudioCapture_ring_buff_consume_no_cpy(&audio_proc_ctx.audioPlayBackCtx.ring_buff, PLAYBACK_BUFFER_SIZE/2);
}

/**
  * @brief  Tx Transfer Half completed callbacks
  * @param  None.
  * @retval None.
  */
void BSP_AUDIO_OUT_HalfTransfer_CallBack(uint32_t Instance)
{
  AudioCapture_ring_buff_consume_no_cpy(&audio_proc_ctx.audioPlayBackCtx.ring_buff, PLAYBACK_BUFFER_SIZE/2);
}
#endif /* (CTRL_X_CUBE_AI_AUDIO_OUT==COM_TYPE_HEADSET)  */

/**
* @brief  Manages the BSP audio in error event.
* @param  Instance Audio in instance.
* @retval None.
*/
void BSP_AUDIO_IN_Error_CallBack(uint32_t Instance)
{
  Error_Handler();
}

void BSP_PB_Callback(Button_TypeDef Button)
{
  if (BUTTON_USER1 == Button)
  {
    toggle_audio_proc();
  }
  else if (BUTTON_TAMP == Button)
  {
    AudioDisplay_RequestAcknowledge();
  }
}
#endif

/*==============================================================================
                  target-domain PCM capture service
 =============================================================================*/

static void TargetCapture_ProcessCommandByte(uint8_t value)
{
  if ((value == '\r') || (value == '\n'))
  {
    if (TargetCaptureCommandLength == 0U)
    {
      return;
    }

    TargetCaptureCommandBuffer[TargetCaptureCommandLength] = '\0';
    TargetCaptureCommandReady =
        (strcmp(TargetCaptureCommandBuffer, TARGET_CAPTURE_COMMAND) == 0);
    TargetCaptureCommandLength = 0U;
    return;
  }

  if ((value >= 0x20U) && (value <= 0x7EU))
  {
    if (TargetCaptureCommandLength < (TARGET_CAPTURE_LINE_CAPACITY - 1U))
    {
      TargetCaptureCommandBuffer[TargetCaptureCommandLength++] = (char)value;
    }
    else
    {
      TargetCaptureCommandLength = 0U;
    }
  }
}

static void TargetCapture_UartTransmit(const void *data, uint32_t byte_count)
{
  const uint8_t *cursor = (const uint8_t *)data;

  while (byte_count > 0U)
  {
    const uint16_t chunk = (byte_count > TARGET_CAPTURE_TX_CHUNK_BYTES) ?
                           TARGET_CAPTURE_TX_CHUNK_BYTES :
                           (uint16_t)byte_count;
    if (HAL_UART_Transmit(&UartHandle, cursor, chunk, HAL_MAX_DELAY) != HAL_OK)
    {
      Error_Handler();
    }
    cursor += chunk;
    byte_count -= chunk;
  }
}

static void TargetCapture_UartTransmitText(const char *text)
{
  TargetCapture_UartTransmit(text, (uint32_t)strlen(text));
}

static bool TargetCapture_CommandReceived(void)
{
  bool received;

  __disable_irq();
  received = TargetCaptureCommandReady;
  if (received)
  {
    TargetCaptureCommandReady = false;
  }
  __enable_irq();

  return received;
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
  if (huart->Instance != USART1)
  {
    return;
  }

  TargetCapture_ProcessCommandByte(TargetCaptureRxByte);
  if (!TargetCaptureCommandReady)
  {
    (void)HAL_UART_Receive_IT(&UartHandle, &TargetCaptureRxByte, 1U);
  }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
  if (huart->Instance != USART1)
  {
    return;
  }

  TargetCaptureCommandLength = 0U;
  __HAL_UART_CLEAR_OREFLAG(&UartHandle);
  (void)HAL_UART_Receive_IT(&UartHandle, &TargetCaptureRxByte, 1U);
}

/* The project does not otherwise link the extended UART source module, while
 * HAL_UART_IRQHandler still references its legacy optional callbacks. */
void HAL_UARTEx_WakeupCallback(UART_HandleTypeDef *huart)
{
  UNUSED(huart);
}

void HAL_UARTEx_RxFifoFullCallback(UART_HandleTypeDef *huart)
{
  UNUSED(huart);
}

void HAL_UARTEx_TxFifoEmptyCallback(UART_HandleTypeDef *huart)
{
  UNUSED(huart);
}

static void TargetCapture_Feed(const int16_t *samples, uint32_t sample_count)
{
  if (!TargetCaptureActive)
  {
    return;
  }

  const uint32_t written = TargetCaptureWrittenSamples;
  const uint32_t requested = TargetCaptureRequestedSamples;
  const uint32_t remaining = requested - written;
  const uint32_t to_copy = (sample_count < remaining) ? sample_count : remaining;

  memcpy(&TargetCaptureBuffer[written], samples, to_copy * sizeof(int16_t));
  __DMB();
  TargetCaptureWrittenSamples = written + to_copy;

  if (TargetCaptureWrittenSamples >= requested)
  {
    TargetCaptureActive = false;
    __DMB();
    TargetCaptureComplete = true;
  }
}

static bool TargetCapture_ReadLine(char *line, uint32_t capacity)
{
  uint32_t length = 0U;
  uint8_t value;

  if (capacity < 2U)
  {
    return false;
  }

  for (;;)
  {
    if (HAL_UART_Receive(&UartHandle, &value, 1U, HAL_MAX_DELAY) != HAL_OK)
    {
      return false;
    }

    if ((value == '\r') || (value == '\n'))
    {
      if (length == 0U)
      {
        continue;
      }
      line[length] = '\0';
      return true;
    }

    if ((value >= 0x20U) && (value <= 0x7EU))
    {
      if (length < (capacity - 1U))
      {
        line[length++] = (char)value;
      }
      else
      {
        length = 0U;
      }
    }
  }
}

static bool TargetCapture_ParseSampleCount(const char *line, uint32_t *sample_count)
{
  static const char prefix[] = "CAPTURE,";
  uint32_t value = 0U;
  const char *cursor;

  if (strncmp(line, prefix, sizeof(prefix) - 1U) != 0)
  {
    return false;
  }

  cursor = line + sizeof(prefix) - 1U;
  if (*cursor == '\0')
  {
    return false;
  }

  while (*cursor != '\0')
  {
    if ((*cursor < '0') || (*cursor > '9'))
    {
      return false;
    }
    if (value > ((TARGET_CAPTURE_MAX_SAMPLES - 9U) / 10U))
    {
      return false;
    }
    value = value * 10U + (uint32_t)(*cursor - '0');
    cursor++;
  }

  if ((value < TARGET_CAPTURE_SAMPLE_RATE) ||
      (value > TARGET_CAPTURE_MAX_SAMPLES))
  {
    return false;
  }

  *sample_count = value;
  return true;
}

static uint32_t TargetCapture_Crc32(const uint8_t *data, uint32_t byte_count)
{
  uint32_t crc = 0xFFFFFFFFUL;

  for (uint32_t index = 0U; index < byte_count; index++)
  {
    crc ^= data[index];
    for (uint32_t bit = 0U; bit < 8U; bit++)
    {
      const uint32_t mask = 0UL - (crc & 1UL);
      crc = (crc >> 1U) ^ (0xEDB88320UL & mask);
    }
  }

  return ~crc;
}

static void TargetCapture_Service(void)
{
  char line[TARGET_CAPTURE_LINE_CAPACITY];
  char response[128];

  TargetCaptureServiceMode = true;
  __DMB();
  HAL_NVIC_DisableIRQ(USART1_IRQn);
  (void)HAL_UART_AbortReceive(&UartHandle);
  TargetCapture_UartTransmitText("PCM_SWITCH,921600\r\n");
  HAL_Delay(250U);
  UartHandle.Init.BaudRate = TARGET_CAPTURE_HIGH_BAUDRATE;
  if (HAL_UART_Init(&UartHandle) != HAL_OK)
  {
    Error_Handler();
  }
  HAL_Delay(250U);

  (void)snprintf(response, sizeof(response),
                 "PCM_READY,%lu,16,1,%lu\r\n",
                 (unsigned long)TARGET_CAPTURE_SAMPLE_RATE,
                 (unsigned long)TARGET_CAPTURE_MAX_SAMPLES);
  TargetCapture_UartTransmitText(response);

  for (;;)
  {
    uint32_t requested_samples;

    if (!TargetCapture_ReadLine(line, sizeof(line)))
    {
      Error_Handler();
    }

    if (strcmp(line, "PING") == 0)
    {
      TargetCapture_UartTransmitText("PCM_PONG\r\n");
      continue;
    }
    if (strcmp(line, "RESET") == 0)
    {
      TargetCapture_UartTransmitText("PCM_RESETTING\r\n");
      HAL_Delay(50U);
      NVIC_SystemReset();
    }
    if (!TargetCapture_ParseSampleCount(line, &requested_samples))
    {
      TargetCapture_UartTransmitText("PCM_ERROR,EXPECTED_CAPTURE_SAMPLE_COUNT\r\n");
      continue;
    }

    (void)snprintf(response, sizeof(response), "PCM_ARMED,%lu\r\n",
                   (unsigned long)requested_samples);
    TargetCapture_UartTransmitText(response);

    __disable_irq();
    TargetCaptureWrittenSamples = 0U;
    TargetCaptureRequestedSamples = requested_samples;
    TargetCaptureComplete = false;
    TargetCaptureActive = true;
    __enable_irq();

    while (!TargetCaptureComplete)
    {
      __WFI();
    }

    const uint32_t byte_count = requested_samples * sizeof(int16_t);
    const uint32_t crc = TargetCapture_Crc32((const uint8_t *)TargetCaptureBuffer,
                                             byte_count);
    (void)snprintf(response, sizeof(response),
                   "PCM_BEGIN,%lu,%lu,%08lX\r\n",
                   (unsigned long)requested_samples,
                   (unsigned long)byte_count,
                   (unsigned long)crc);
    TargetCapture_UartTransmitText(response);
    TargetCapture_UartTransmit(TargetCaptureBuffer, byte_count);
    (void)snprintf(response, sizeof(response), "\r\nPCM_END,%08lX\r\n",
                   (unsigned long)crc);
    TargetCapture_UartTransmitText(response);
  }
}

/*==============================================================================
                    private  functions definition
 ============================================================================= */

#if (CTRL_X_CUBE_AI_AUDIO_OUT==COM_TYPE_HEADSET)
/**
  * @brief  Playback initialization
  * @param  ctx_ptr play back execution context
  * @retval None
  */
static void initAudioPlayBack(AudioBM_play_back_t *ctx_ptr)
{
   BSP_AUDIO_Init_t AudioInit;

  /* Configure playback */
  AudioInit.Device        = AUDIO_OUT_DEVICE_HEADPHONE;
  AudioInit.SampleRate    = AUDIO_FREQUENCY;
  AudioInit.BitsPerSample = AUDIO_RESOLUTION_16B;
  AudioInit.ChannelsNbr   = 1;
  AudioInit.Volume        = 0; /* not used */

  if (BSP_ERROR_NONE != BSP_AUDIO_OUT_Init(0, &AudioInit))
  {
    Error_Handler();
  }
  ctx_ptr->ring_buff.readSampleIndex  = 0 ;
  ctx_ptr->ring_buff.writeSampleIndex = 0 ;
  ctx_ptr->ring_buff.nbFrames = 1;
  ctx_ptr->ring_buff.nbBytesPerSample = 2;
  ctx_ptr->ring_buff.nbSamples = PLAYBACK_BUFFER_SIZE;
  ctx_ptr->ring_buff.pData = (uint8_t *) playback_buf;
  ctx_ptr->cnt = 0 ;
}

static void AudioPlayBack(AudioBM_play_back_t *ctx_ptr, int16_t *pData,\
    uint16_t nbSamples)
{
  float lev_db = vumeter((int16_t *)pData,nbSamples);
  if (lev_db < CTRL_X_CUBE_AI_AUDIO_OUT_DB_THRESHOLD)
  {
    for (int i=0; i<nbSamples; i++){
      pData[i] = 0;
    }
  }
  AudioCapture_ring_buff_feed(& ctx_ptr->ring_buff,(uint8_t *) pData, nbSamples);

  if (ctx_ptr->cnt== 1) 
  {
    /* Start the playback */
    if (BSP_ERROR_NONE != BSP_AUDIO_OUT_Play(0, ctx_ptr->ring_buff.pData, \
      PLAYBACK_BUFFER_SIZE * sizeof(int16_t)))
    {
      Error_Handler();
    }
  }
  ctx_ptr->cnt++;
}

/**
 * @brief  Displays level of audio on the console in the from of a colored bar
 * @param  IN pAudioSmp : pointer to audio samples
 * @param  IN nb_samples : number of samples
 * @retval audio level in dB
 */
static float vumeter(int16_t * pAudioSmp,int nb_samples)
{
	float sum=0 ;
	for (int i = 0 ; i < nb_samples ; i ++)
	{
		sum += pAudioSmp[i]*pAudioSmp[i];
	}
	// Float value here corresponds to log10(2**30)
	float lev_db = (float)(10*(log10(sum/(nb_samples)) - 9.03089986F));
	// Casting it back to int and removing scale factor for display
	int lev = (int) (lev_db + 10 * 9.03089986F) / 5;
  lev=(lev<0)? 0 : lev;
  lev=(lev>20)? 20 : lev;
	printf("\r\033[42m");
	for (int i = 0 ; i < lev && i < 6 ; i ++)
	{
		printf(" ");
	}
	printf("\033[43m");
	for (int i = 6 ; i < lev && i < 12 ; i ++)
	{
		printf(" ");
	}
	printf("\033[41m");
	for (int i = 12 ; i < lev ; i ++)
	{
		printf(" ");
	}
	printf("\033[0m");
	for (int i = 0 ; i < 20 - lev ; i ++)
	{
		printf(" ");
	}
	fflush(stdout);
	return lev_db;
}

#endif

static void Int_Mem_Config(void)
{
  RAMCFG_HandleTypeDef hramcfg = {0};

  __HAL_RCC_SYSCFG_CLK_ENABLE();
  __HAL_RCC_CRC_CLK_ENABLE();

#ifdef APP_LP
/*  hramcfg.Instance =  RAMCFG_SRAM2_AXI;
  HAL_RAMCFG_DisableAXISRAM(&hramcfg);
  HAL_RAMCFG_EnableAXISRAM(&hramcfg); */
  hramcfg.Instance =  RAMCFG_SRAM6_AXI;
  HAL_RAMCFG_EnableAXISRAM(&hramcfg);

  __HAL_RCC_CACHEAXIRAM_MEM_CLK_ENABLE();
  __HAL_RCC_AXISRAM6_MEM_CLK_ENABLE();

/*  __HAL_RCC_AXISRAM2_MEM_CLK_DISABLE(); */
  __HAL_RCC_AHBSRAM1_MEM_CLK_DISABLE();
  __HAL_RCC_AHBSRAM2_MEM_CLK_DISABLE();
  __HAL_RCC_BKPSRAM_MEM_CLK_DISABLE();

#else /* APP_LP */

  RCC->MEMENR |= RCC_MEMENR_AXISRAM3EN | RCC_MEMENR_AXISRAM4EN | RCC_MEMENR_AXISRAM5EN | RCC_MEMENR_AXISRAM6EN;
  RCC->MEMENR |= RCC_MEMENR_CACHEAXIRAMEN; 
  hramcfg.Instance =  RAMCFG_SRAM2_AXI;
  HAL_RAMCFG_EnableAXISRAM(&hramcfg);
  hramcfg.Instance =  RAMCFG_SRAM3_AXI;
  HAL_RAMCFG_EnableAXISRAM(&hramcfg);
  hramcfg.Instance =  RAMCFG_SRAM4_AXI;
  HAL_RAMCFG_EnableAXISRAM(&hramcfg);
  hramcfg.Instance =  RAMCFG_SRAM5_AXI;
  HAL_RAMCFG_EnableAXISRAM(&hramcfg);
  hramcfg.Instance =  RAMCFG_SRAM6_AXI;
  HAL_RAMCFG_EnableAXISRAM(&hramcfg);

  __HAL_RCC_CACHEAXIRAM_MEM_CLK_ENABLE();
  __HAL_RCC_AXISRAM2_MEM_CLK_ENABLE();
  __HAL_RCC_AXISRAM3_MEM_CLK_ENABLE();
  __HAL_RCC_AXISRAM4_MEM_CLK_ENABLE();
  __HAL_RCC_AXISRAM5_MEM_CLK_ENABLE();
  __HAL_RCC_AXISRAM6_MEM_CLK_ENABLE();

#endif 
  /* Allow caches to be activated. Default value is 1, but the current boot sets it to 0 */
  MEMSYSCTL->MSCR |= MEMSYSCTL_MSCR_DCACTIVE_Msk | MEMSYSCTL_MSCR_ICACTIVE_Msk;
}

/**
* @brief  Record initialization
* @param  None
* @retval None
*/
static void Record_Init(void)
{
  BSP_AUDIO_Init_t AudioInit;
  uint32_t         GetData;

  /* Test of state */
  if (BSP_ERROR_NONE != BSP_AUDIO_IN_GetState(1, &GetData)) Error_Handler();
  if (GetData != AUDIO_IN_STATE_RESET) Error_Handler();

  AudioInit.Device        = AUDIO_IN_DEVICE_DIGITAL_MIC;
  AudioInit.SampleRate    = AUDIO_FREQUENCY;
  AudioInit.BitsPerSample = AUDIO_RESOLUTION_16B;
  AudioInit.ChannelsNbr   = 1;
  AudioInit.Volume        = 80; /* Not used */

  if (BSP_ERROR_NONE != BSP_AUDIO_IN_Init(1, &AudioInit))
  {
    Error_Handler();
  }

  /* Test of state */
  if (BSP_ERROR_NONE != BSP_AUDIO_IN_GetState(1, &GetData)) Error_Handler();
  if (GetData != AUDIO_IN_STATE_STOP) Error_Handler();

  /* Test set and get functions */
  if (BSP_ERROR_FEATURE_NOT_SUPPORTED != BSP_AUDIO_IN_SetVolume(1, 10)) Error_Handler();
  /*if (BSP_ERROR_NONE != BSP_AUDIO_IN_SetSampleRate(1, SAI_AUDIO_FREQUENCY_96K)) Error_Handler(); */
  if (BSP_ERROR_NONE != BSP_AUDIO_IN_SetDevice(1, AUDIO_IN_DEVICE_ANALOG_MIC)) Error_Handler();
  if (BSP_ERROR_FEATURE_NOT_SUPPORTED != BSP_AUDIO_IN_SetBitsPerSample(1, AUDIO_RESOLUTION_8B)) Error_Handler();
  if (BSP_ERROR_NONE != BSP_AUDIO_IN_SetBitsPerSample(1, AUDIO_RESOLUTION_16B)) Error_Handler();
  if (BSP_ERROR_FEATURE_NOT_SUPPORTED != BSP_AUDIO_IN_SetBitsPerSample(1, AUDIO_RESOLUTION_24B)) Error_Handler();
  if (BSP_ERROR_FEATURE_NOT_SUPPORTED != BSP_AUDIO_IN_SetBitsPerSample(1, AUDIO_RESOLUTION_32B)) Error_Handler();
  if (BSP_ERROR_FEATURE_NOT_SUPPORTED != BSP_AUDIO_IN_SetChannelsNbr(1, 2)) Error_Handler();
  if (BSP_ERROR_NONE != BSP_AUDIO_IN_SetChannelsNbr(1, 1)) Error_Handler();

  if (BSP_ERROR_FEATURE_NOT_SUPPORTED != BSP_AUDIO_IN_GetVolume(1, &GetData)) Error_Handler();
  if (BSP_ERROR_NONE != BSP_AUDIO_IN_GetSampleRate(1, &GetData)) Error_Handler();
  /*if (GetData != AUDIO_FREQUENCY_96K) Error_Handler();*/
  if (BSP_ERROR_NONE != BSP_AUDIO_IN_GetDevice(1, &GetData)) Error_Handler();
  if (GetData != AUDIO_IN_DEVICE_DIGITAL_MIC) Error_Handler();
  if (BSP_ERROR_NONE != BSP_AUDIO_IN_GetBitsPerSample(1, &GetData)) Error_Handler();
  if (GetData != AUDIO_RESOLUTION_16B) Error_Handler();
  if (BSP_ERROR_NONE != BSP_AUDIO_IN_GetChannelsNbr(1, &GetData)) Error_Handler();
  if (GetData != 1U) Error_Handler();

  /* Set the initial sample rate */
  if (BSP_ERROR_NONE != BSP_AUDIO_IN_SetSampleRate(1, AudioInit.SampleRate)) Error_Handler();
}

static void NPU_SettingsLog(void)
{
    struct mcu_conf sys_conf;
    getSysConf(&sys_conf);
    my_printf("\n\rNPU Runtime configuration...\r\n");
    my_printf(" NPU clock    : %u MHz\r\n", (int)sys_conf.extra[1]/1000000);
    my_printf(" NIC clock    : %u MHz\r\n", (int)sys_conf.extra[2]/1000000);
}

/**
* @brief  external memories configuration (Flash & RAM).
* @param  None.
* @retval None.
*/
static void Ext_Mem_Config(void)
{
  BSP_XSPI_NOR_Init_t Flash;

  if (BSP_XSPI_RAM_Init(0) != BSP_ERROR_NONE)
  {
    __BKPT(0);
  }
  if (BSP_XSPI_RAM_EnableMemoryMappedMode(0) != BSP_ERROR_NONE)
  {
    __BKPT(0);
  }

  Flash.InterfaceMode = MX66UW1G45G_OPI_MODE;
  Flash.TransferRate = MX66UW1G45G_DTR_TRANSFER;

  if(BSP_XSPI_NOR_Init(0, &Flash) != BSP_ERROR_NONE)
  {
    __BKPT(0);
  }
  BSP_XSPI_NOR_EnableMemoryMappedMode(0);
  MODIFY_REG(XSPI2->CR, XSPI_CR_NOPREF, HAL_XSPI_AUTOMATIC_PREFETCH_DISABLE); /* Hotfix for xspi: no prefetch */

}
static void IAC_Config(void)
{
/* Configure IAC to trap illegal access events */
  __HAL_RCC_IAC_CLK_ENABLE();
  __HAL_RCC_IAC_FORCE_RESET();
  __HAL_RCC_IAC_RELEASE_RESET();
}

static void MPU_Config(void)
{
  MPU_Region_InitTypeDef default_config = {0};
  MPU_Attributes_InitTypeDef attr_config = {0};
  uint32_t primask_bit = __get_PRIMASK();
  __disable_irq();
  /* disable the MPU */
  HAL_MPU_Disable();
  /* create an attribute configuration for the MPU */
  attr_config.Attributes = INNER_OUTER(MPU_NOT_CACHEABLE);
  attr_config.Number = MPU_ATTRIBUTES_NUMBER0;
  HAL_MPU_ConfigMemoryAttributes(&attr_config);
  /* Create a non cacheable region */
  /*Normal memory type, code execution allowed */
  default_config.Enable = MPU_REGION_ENABLE;
  default_config.Number = MPU_REGION_NUMBER0;
  default_config.BaseAddress = __NON_CACHEABLE_SECTION_BEGIN;
  default_config.LimitAddress = __NON_CACHEABLE_SECTION_END;
  default_config.DisableExec = MPU_INSTRUCTION_ACCESS_ENABLE;
  default_config.AccessPermission = MPU_REGION_ALL_RW;
  default_config.IsShareable = MPU_ACCESS_NOT_SHAREABLE;
  default_config.AttributesIndex = MPU_ATTRIBUTES_NUMBER0;
  HAL_MPU_ConfigRegion(&default_config);
  /* enable the MPU */
  HAL_MPU_Enable(MPU_PRIVILEGED_DEFAULT);
  /* Exit critical section to lock the system and avoid any issue around MPU mechanisme */
  __set_PRIMASK(primask_bit);
}

static void SleepClks_init(void)
{
  /* Keep all IP's enabled during WFE so they can wake up CPU. Fine tune
     this if you want to save maximum power
     this is specially needed when  LL_ATON_RT_MODE=LL_ATON_RT_ASYNC is used
  */
  LL_BUS_EnableClockLowPower(~0);
  LL_MEM_EnableClockLowPower(~0);
  LL_AHB1_GRP1_EnableClockLowPower(~0);
  LL_AHB2_GRP1_EnableClockLowPower(~0);
  LL_AHB3_GRP1_EnableClockLowPower(~0);
  LL_AHB4_GRP1_EnableClockLowPower(~0);
  LL_AHB5_GRP1_EnableClockLowPower(~0);
  LL_APB1_GRP1_EnableClockLowPower(~0);
  LL_APB1_GRP2_EnableClockLowPower(~0);
  LL_APB2_GRP1_EnableClockLowPower(~0);
  LL_APB4_GRP1_EnableClockLowPower(~0);
  LL_APB4_GRP2_EnableClockLowPower(~0);
  LL_APB5_GRP1_EnableClockLowPower(~0);
  LL_MISC_EnableClockLowPower(~0);
}

