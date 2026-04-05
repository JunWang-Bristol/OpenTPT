/**
 * Bare-metal main header for TPT SCPI Server (NUCLEO-H503RB).
 * No HAL / LL dependencies — CMSIS register definitions only.
 */
#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32h5xx.h"
#include <stdbool.h>
#include <stdint.h>

/* ── Pin definitions (bit masks for GPIOB->BSRR / GPIOA->BSRR) ── */
#define PositivePulse_Pin    (1U << 10)   /* PB10 */
#define NegativePulse_Pin    (1U << 4)    /* PB4  */
#define LED2_Pin             (1U << 5)    /* PA5  */
#define USER_BUTTON_Pin      (1U << 13)   /* PC13 */

/* ── LED blink periods (ms) ── */
#define LED_BLINK_FAST   200
#define LED_BLINK_SLOW   500
#define LED_BLINK_ERROR  1000

/* ── Millisecond tick (replaces HAL_GetTick / HAL_IncTick) ── */
extern volatile uint32_t uwTick;

/* ── Exported functions ── */
void Error_Handler(void);
void UserButton_Callback(void);
void USART_CharReception_Callback(void);
void Error_Callback(void);

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
