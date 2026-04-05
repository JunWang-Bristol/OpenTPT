/**
 * Bare-metal interrupt handlers for TPT SCPI Server (NUCLEO-H503RB).
 * No HAL / LL — direct register access only.
 */
#include "main.h"

/* ── Cortex-M33 system exceptions ── */

void NMI_Handler(void)          {}
void HardFault_Handler(void)    { while (1) {} }
void MemManage_Handler(void)    { while (1) {} }
void BusFault_Handler(void)     { while (1) {} }
void UsageFault_Handler(void)   { while (1) {} }
void SVC_Handler(void)          {}
void DebugMon_Handler(void)     {}
void PendSV_Handler(void)       {}

void SysTick_Handler(void)
{
    uwTick++;
}

/* ── Peripheral interrupts ── */

void EXTI13_IRQHandler(void)
{
    if (EXTI->RPR1 & (1U << 13)) {
        EXTI->RPR1 = (1U << 13);   /* clear rising pending */
        UserButton_Callback();
    }
}

void USART3_IRQHandler(void)
{
    if ((USART3->ISR & USART_ISR_RXNE_RXFNE) && (USART3->CR1 & USART_CR1_RXNEIE_RXFNEIE)) {
        USART_CharReception_Callback();
    } else {
        Error_Callback();
    }
}
