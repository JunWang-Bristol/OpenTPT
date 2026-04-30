/**
 * Bare-metal main for TPT SCPI Server (NUCLEO-H503RB).
 *
 * Peripherals initialised with direct register writes — no HAL / LL.
 *   - System clock: HSE 24 MHz → PLL1 → 250 MHz
 *   - USART3 on PA3 (RX) / PA4 (TX), 115 200 baud, RX interrupt
 *   - GPIO: PB10 (PositivePulse), PB4 (NegativePulse), PA5 (LED2), PC13 (Button)
 *   - EXTI13 rising edge for user button
 *   - SysTick 1 ms tick
 *   - ICACHE enabled
 */
#include "main.h"
#include "tpt-scpi.h"
#include <stdio.h>
#include <string.h>

/* ── Millisecond tick ── */
volatile uint32_t uwTick = 0;

/* ── UART double-buffer for single-byte reception ── */
#define RX_BUFFER_SIZE  1
static uint8_t aRXBufferA[RX_BUFFER_SIZE];
static uint8_t aRXBufferB[RX_BUFFER_SIZE];
static volatile uint32_t uwNbReceivedChars;
static volatile uint32_t uwBufferReadyIndication;
static uint8_t *pBufferReadyForUser;
static uint8_t *pBufferReadyForReception;

/* ── Forward declarations ── */
static void SystemClock_Config(void);
static void GPIO_Init(void);
static void USART3_Init(void);
static void ICACHE_Init(void);
static void StartReception(void);
static void HandleContinuousReception(void);

/* ════════════════════════════════════════════════════════════════════ */

int main(void)
{
    SystemClock_Config();
    GPIO_Init();
    USART3_Init();
    ICACHE_Init();

    /* SysTick: 1 ms tick at 250 MHz */
    SysTick_Config(250000000U / 1000U);

    /* LED off */
    GPIOA->BSRR = LED2_Pin << 16;

    /* Start UART reception */
    StartReception();

    /* Initialise SCPI */
    SCPI_Init(&scpi_context,
              scpi_commands,
              &scpi_interface,
              scpi_units_def,
              SCPI_IDN1, SCPI_IDN2, SCPI_IDN3, SCPI_IDN4,
              scpi_input_buffer, SCPI_INPUT_BUFFER_LENGTH,
              scpi_error_queue_data, SCPI_ERROR_QUEUE_SIZE);

    printf("TPT 2402 r2 bare-metal SCPI\r\n");

    reset_pins();

    while (1) {
        HandleContinuousReception();
    }
}

/* ── Clock: HSE 24 MHz → PLL1 → SYSCLK 250 MHz ── */
static void SystemClock_Config(void)
{
    /* Flash latency 5 WS for 250 MHz at VOS0 */
    FLASH->ACR = (FLASH->ACR & ~FLASH_ACR_LATENCY) | FLASH_ACR_LATENCY_5WS;
    while ((FLASH->ACR & FLASH_ACR_LATENCY) != FLASH_ACR_LATENCY_5WS) {}

    /* Voltage scaling VOS0 (highest performance) */
    PWR->VOSCR = (PWR->VOSCR & ~PWR_VOSCR_VOS) | (3U << PWR_VOSCR_VOS_Pos);
    while (!(PWR->VOSSR & PWR_VOSSR_VOSRDY)) {}

    /* Enable HSE (24 MHz crystal on NUCLEO-H503RB) */
    RCC->CR |= RCC_CR_HSEON;
    while (!(RCC->CR & RCC_CR_HSERDY)) {}

    /* Configure PLL1: HSE/12 × 250 / 2 = 250 MHz
     *   PLL input  = 24 / 12 = 2 MHz   (range 2–4 MHz)
     *   VCO output = 2 × 250 = 500 MHz  (wide range)
     *   P output   = 500 / 2 = 250 MHz                    */
    RCC->PLL1CFGR = (3U  << RCC_PLL1CFGR_PLL1SRC_Pos)   /* HSE */
                  | (12U << RCC_PLL1CFGR_PLL1M_Pos)      /* M = 12 */
                  | (1U  << RCC_PLL1CFGR_PLL1RGE_Pos)    /* Input 2–4 MHz */
                  | (0U  << RCC_PLL1CFGR_PLL1VCOSEL_Pos) /* Wide VCO */
                  | RCC_PLL1CFGR_PLL1PEN;                 /* Enable P output */

    /* N = 250 (register value N−1 = 249), P = 2 (P−1 = 1), Q = 2, R = 2 */
    RCC->PLL1DIVR = ((250U - 1U) << RCC_PLL1DIVR_PLL1N_Pos)
                  | ((2U - 1U)   << RCC_PLL1DIVR_PLL1P_Pos)
                  | ((2U - 1U)   << RCC_PLL1DIVR_PLL1Q_Pos)
                  | ((2U - 1U)   << RCC_PLL1DIVR_PLL1R_Pos);

    /* Enable PLL1 */
    RCC->CR |= RCC_CR_PLL1ON;
    while (!(RCC->CR & RCC_CR_PLL1RDY)) {}

    /* Switch SYSCLK to PLL1 */
    RCC->CFGR1 = (RCC->CFGR1 & ~RCC_CFGR1_SW) | (3U << RCC_CFGR1_SW_Pos);
    while ((RCC->CFGR1 & RCC_CFGR1_SWS) != (3U << RCC_CFGR1_SWS_Pos)) {}

    /* AHB / APB prescalers = 1 (default) */
    RCC->CFGR2 = 0;

    SystemCoreClock = 250000000U;
}

/* ── GPIO init ── */
static void GPIO_Init(void)
{
    /* Enable clocks for GPIOA, GPIOB, GPIOC */
    RCC->AHB2ENR |= RCC_AHB2ENR_GPIOAEN | RCC_AHB2ENR_GPIOBEN | RCC_AHB2ENR_GPIOCEN;
    /* Short delay for clock to stabilise */
    __DSB();

    /* ── PB10 (PositivePulse) + PB4 (NegativePulse): output, push-pull, very-high speed, pull-down ── */
    /* MODER: 01 = output */
    GPIOB->MODER &= ~((3U << (10*2)) | (3U << (4*2)));
    GPIOB->MODER |=  ((1U << (10*2)) | (1U << (4*2)));
    /* OTYPER: 0 = push-pull (default) */
    GPIOB->OTYPER &= ~(PositivePulse_Pin | NegativePulse_Pin);
    /* OSPEEDR: 11 = very high */
    GPIOB->OSPEEDR |= ((3U << (10*2)) | (3U << (4*2)));
    /* PUPDR: 10 = pull-down */
    GPIOB->PUPDR &= ~((3U << (10*2)) | (3U << (4*2)));
    GPIOB->PUPDR |=  ((2U << (10*2)) | (2U << (4*2)));
    /* Start LOW */
    GPIOB->BSRR = (PositivePulse_Pin | NegativePulse_Pin) << 16;

    /* ── PA5 (LED2): output, push-pull, low speed ── */
    GPIOA->MODER &= ~(3U << (5*2));
    GPIOA->MODER |=  (1U << (5*2));

    /* ── PA3 (USART3_RX AF13) + PA4 (USART3_TX AF13): alternate function, high speed, pull-up ── */
    GPIOA->MODER &= ~((3U << (3*2)) | (3U << (4*2)));
    GPIOA->MODER |=  ((2U << (3*2)) | (2U << (4*2)));   /* AF mode */
    GPIOA->OSPEEDR |= ((2U << (3*2)) | (2U << (4*2)));   /* high speed */
    GPIOA->PUPDR &= ~((3U << (3*2)) | (3U << (4*2)));
    GPIOA->PUPDR |=  ((1U << (3*2)) | (1U << (4*2)));    /* pull-up */
    GPIOA->OTYPER &= ~((1U << 3) | (1U << 4));           /* push-pull */
    /* AFR[0]: AF13 = 0x0D for PA3 (bits 15:12) and PA4 (bits 19:16) */
    GPIOA->AFR[0] &= ~((0xFU << (3*4)) | (0xFU << (4*4)));
    GPIOA->AFR[0] |=  ((0xDU << (3*4)) | (0xDU << (4*4)));

    /* ── PC13 (USER_BUTTON): input, pull-down ── */
    GPIOC->MODER &= ~(3U << (13*2));   /* input (00) */
    GPIOC->PUPDR &= ~(3U << (13*2));
    GPIOC->PUPDR |=  (2U << (13*2));   /* pull-down */

    /* ── EXTI13 rising edge on PC13 ── */
    EXTI->EXTICR[3] = (EXTI->EXTICR[3] & ~(0xFFU << 8)) | (0x02U << 8);  /* port C, line 13 */
    EXTI->RTSR1 |= (1U << 13);   /* rising trigger */
    EXTI->IMR1  |= (1U << 13);   /* unmask */
    NVIC_SetPriority(EXTI13_IRQn, 3);
    NVIC_EnableIRQ(EXTI13_IRQn);
}

/* ── USART3: 115200 8N1, RX interrupt ── */
static void USART3_Init(void)
{
    /* Enable USART3 clock (APB1) */
    RCC->APB1LENR |= RCC_APB1LENR_USART3EN;
    __DSB();

    /* Disable USART while configuring */
    USART3->CR1 = 0;
    USART3->CR2 = 0;   /* 1 stop bit, async mode */
    USART3->CR3 = 0;   /* no flow control */
    USART3->PRESC = 0; /* prescaler /1 */

    /* BRR = PCLK1 / baud = 250 000 000 / 115 200 ≈ 2170 */
    USART3->BRR = 2170U;

    /* Enable TX + RX + USART */
    USART3->CR1 = USART_CR1_TE | USART_CR1_RE | USART_CR1_UE;

    /* NVIC */
    NVIC_SetPriority(USART3_IRQn, 0);
    NVIC_EnableIRQ(USART3_IRQn);
}

/* ── ICACHE ── */
static void ICACHE_Init(void)
{
    ICACHE->CR |= ICACHE_CR_EN;
}

/* ── putchar for printf → USART3 ── */
int __io_putchar(int ch)
{
    while (!(USART3->ISR & USART_ISR_TC)) {}
    USART3->TDR = (uint8_t)ch;
    return ch;
}

/* ── UART reception helpers (same logic as original) ── */
static void StartReception(void)
{
    pBufferReadyForReception = aRXBufferA;
    pBufferReadyForUser      = aRXBufferB;
    uwNbReceivedChars = 0;
    uwBufferReadyIndication = 0;

    /* Clear overrun flag, enable RXNE + error interrupts */
    USART3->ICR = USART_ICR_ORECF;
    USART3->CR1 |= USART_CR1_RXNEIE_RXFNEIE;
    USART3->CR3 |= USART_CR3_EIE;
}

static void HandleContinuousReception(void)
{
    if (uwBufferReadyIndication != 0) {
        uwBufferReadyIndication = 0;
        SCPI_Input(&scpi_context, (const char *)pBufferReadyForUser,
                   strlen((const char *)pBufferReadyForUser));
        GPIOA->ODR ^= LED2_Pin;   /* toggle LED */
    }
}

/* ── Callbacks (called from ISR context) ── */
void UserButton_Callback(void)
{
    printf("Button pressed\n\r");
}

void USART_CharReception_Callback(void)
{
    uint8_t *ptemp;

    pBufferReadyForReception[uwNbReceivedChars++] =
        (uint8_t)(USART3->RDR & 0xFFU);

    if (uwNbReceivedChars >= RX_BUFFER_SIZE) {
        uwBufferReadyIndication = 1;
        ptemp = pBufferReadyForUser;
        pBufferReadyForUser = pBufferReadyForReception;
        pBufferReadyForReception = ptemp;
        uwNbReceivedChars = 0;
    }
}

void Error_Callback(void)
{
    uint32_t isr = USART3->ISR;
    if (isr & USART_ISR_NE) {
        USART3->ICR = USART_ICR_NECF;
    }
    /* Clear other error flags to avoid stuck IRQ */
    if (isr & USART_ISR_FE)  USART3->ICR = USART_ICR_FECF;
    if (isr & USART_ISR_ORE) USART3->ICR = USART_ICR_ORECF;
}

void Error_Handler(void)
{
    __disable_irq();
    while (1) {}
}

void LED_Blinking(uint32_t period)
{
    while (1) {
        GPIOA->ODR ^= LED2_Pin;
        /* Simple ms delay using SysTick uwTick */
        uint32_t start = uwTick;
        while ((uwTick - start) < period) {}
    }
}

#ifdef USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line) { (void)file; (void)line; }
#endif
