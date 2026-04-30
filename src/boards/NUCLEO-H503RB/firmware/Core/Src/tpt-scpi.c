/**
 * TPT SCPI command callbacks + optimised pulse generator.
 *
 * Bare-metal — no HAL / LL.  Pulse timing via DWT cycle counter.
 *
 * Key optimisations over the previous version:
 *   1. Pre-computed DWT cycle counts in TPT_AddPulse (no 64-bit math at runtime)
 *   2. Pre-computed BSRR values (no branch in the hot loop)
 *   3. Fully inlined pulse loop (no function calls inside __disable_irq)
 *   4. Configurable deadtime via CONF:DEAD <seconds>  (default 100 ns)
 */
#include "tpt-scpi.h"
#include "scpi/scpi.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ── SCPI command table ── */

scpi_command_t scpi_commands[] = {
    /* IEEE mandated */
    { .pattern = "*CLS",  .callback = SCPI_CoreCls },
    { .pattern = "*ESE",  .callback = SCPI_CoreEse },
    { .pattern = "*ESE?", .callback = SCPI_CoreEseQ },
    { .pattern = "*ESR?", .callback = SCPI_CoreEsrQ },
    { .pattern = "*IDN?", .callback = SCPI_CoreIdnQ },
    { .pattern = "*OPC",  .callback = SCPI_CoreOpc },
    { .pattern = "*OPC?", .callback = TPT_CoreOpcQ },
    { .pattern = "*RST",  .callback = SCPI_CoreRst },
    { .pattern = "*SRE",  .callback = SCPI_CoreSre },
    { .pattern = "*SRE?", .callback = SCPI_CoreSreQ },
    { .pattern = "*STB?", .callback = SCPI_CoreStbQ },
    { .pattern = "*TST?", .callback = SCPI_CoreTstQ },
    { .pattern = "*WAI",  .callback = SCPI_CoreWai },

    /* Required SCPI */
    { .pattern = "SYSTem:ERRor[:NEXT]?", .callback = SCPI_SystemErrorNextQ },
    { .pattern = "SYSTem:ERRor:COUNt?",  .callback = SCPI_SystemErrorCountQ },
    { .pattern = "SYSTem:VERSion?",      .callback = SCPI_SystemVersionQ },

    /* TPT pulse generator */
    { .pattern = "CONFigure:PULses:ADD",      .callback = TPT_AddPulse },
    { .pattern = "CONFigure:PULses:CLEAR",    .callback = TPT_ClearPulses },
    { .pattern = "CONFigure:PULses?",         .callback = TPT_ReadPulses },
    { .pattern = "CONFigure:PULses:MINimum?", .callback = TPT_GetMinimumPulse },
    { .pattern = "CONFigure:PULses:MAXimum?", .callback = TPT_GetMaximumPulse },
    { .pattern = "CONFigure:DEADtime",        .callback = TPT_SetDeadtime },
    { .pattern = "CONFigure:DEADtime?",       .callback = TPT_GetDeadtime },
    { .pattern = "APPlication:PULses:RUN",    .callback = TPT_RunPulses },
    { .pattern = "APPlication:PULses:COUNT?",  .callback = TPT_GetCountPulses },

    SCPI_CMD_LIST_END
};

scpi_interface_t scpi_interface = {
    .error   = SCPI_Error,
    .write   = SCPI_Write,
    .control = SCPI_Control,
    .flush   = SCPI_Flush,
    .reset   = SCPI_Reset,
};

/* ── SCPI buffers ── */

char scpi_input_buffer[SCPI_INPUT_BUFFER_LENGTH];
scpi_error_t scpi_error_queue_data[SCPI_ERROR_QUEUE_SIZE];
scpi_t scpi_context;

/* ── Pulse storage ── */

/* SCPI-layer storage (quantised to minimum_period for readback) */
static uint64_t pulse_periods[TPT_MAXIMUM_NUMBER_PULSES];

/* Execution-layer storage (pre-computed for the hot loop) */
static uint32_t pulse_delay_cycles[TPT_MAXIMUM_NUMBER_PULSES];
static uint32_t pulse_bsrr[TPT_MAXIMUM_NUMBER_PULSES];

static size_t current_number_pulses = 0;
static bool   running = false;
static size_t run_trains = 0;

static double minimum_period = 1e-8;   /* 10 ns resolution */
static double maximum_period = 0.05;   /* 50 ms */

/* ── Deadtime (configurable via CONF:DEAD) ── */

#define DEFAULT_DEADTIME_NS  100U
static uint32_t deadtime_ns     = DEFAULT_DEADTIME_NS;
static uint32_t deadtime_cycles = 0;  /* computed in init_dwt() */

/* ── DWT cycle counter ── */

static bool dwt_initialized = false;

static void init_dwt(void)
{
    if (!dwt_initialized) {
        CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
        DWT->CYCCNT = 0;
        DWT->CTRL  |= DWT_CTRL_CYCCNTENA_Msk;
        dwt_initialized = true;
    }
    /* (Re)compute deadtime in DWT cycles */
    deadtime_cycles = (uint32_t)((uint64_t)SystemCoreClock * deadtime_ns / 1000000000ULL);
}

/* ── Pin helpers ── */

/* BSRR value that drives both pulse pins LOW */
#define BOTH_OFF  ((PositivePulse_Pin | NegativePulse_Pin) << 16U)

void reset_pins(void)
{
    GPIOB->BSRR = BOTH_OFF;
}

/* ── SCPI interface callbacks ── */

size_t SCPI_Write(scpi_t *context, const char *data, size_t len)
{
    (void)context;
    return fwrite(data, 1, len, stdout);
}

scpi_result_t SCPI_Flush(scpi_t *context)
{
    (void)context;
    return SCPI_RES_OK;
}

int SCPI_Error(scpi_t *context, int_fast16_t err)
{
    (void)context;
    fprintf(stderr, "**ERROR: %d, \"%s\" from %s\r\n",
            (int16_t)err, SCPI_ErrorTranslate(err), context->buffer.data);
    return 0;
}

scpi_result_t SCPI_Control(scpi_t *context, scpi_ctrl_name_t ctrl, scpi_reg_val_t val)
{
    (void)context;
    if (SCPI_CTRL_SRQ == ctrl)
        fprintf(stderr, "**SRQ: 0x%X (%d)\r\n", val, val);
    else
        fprintf(stderr, "**CTRL %02x: 0x%X (%d)\r\n", ctrl, val, val);
    return SCPI_RES_OK;
}

scpi_result_t SCPI_Reset(scpi_t *context)
{
    (void)context;
    current_number_pulses = 0;
    run_trains = 0;
    running = false;
    reset_pins();
    return SCPI_RES_OK;
}

scpi_result_t SCPI_SystemCommTcpipControlQ(scpi_t *context)
{
    (void)context;
    return SCPI_RES_ERR;
}

scpi_result_t SCPI_CoreWai(scpi_t *context)
{
    (void)context;
    return SCPI_RES_OK;
}

/* ── TPT pulse commands ── */

scpi_result_t TPT_AddPulse(scpi_t *context)
{
    double period;
    if (!SCPI_ParamDouble(context, &period, TRUE))
        return SCPI_RES_ERR;

    if (current_number_pulses >= TPT_MAXIMUM_NUMBER_PULSES)
        return SCPI_RES_ERR;

    /* Store quantised period for SCPI readback */
    pulse_periods[current_number_pulses] = (uint64_t)round(period / minimum_period);

    /* Pre-compute DWT cycle count from full-precision period */
    pulse_delay_cycles[current_number_pulses] =
        (uint32_t)(period * (double)SystemCoreClock + 0.5);

    /* Match the H:\OpenTPT.zip firmware logic: anti-phase toggle.
     *  Even index -> PositivePulse_Pin HIGH, NegativePulse_Pin LOW
     *  Odd  index -> PositivePulse_Pin LOW,  NegativePulse_Pin HIGH
     * Each BSRR write also clears the opposite pin so reset_pins() before is
     * not strictly required; the deadtime-path will still emit BOTH_OFF first. */
    if (current_number_pulses % 2 == 0) {
        pulse_bsrr[current_number_pulses] =
            (NegativePulse_Pin << 16U) | PositivePulse_Pin;   /* PB10 HIGH, PB4 LOW */
    } else {
        pulse_bsrr[current_number_pulses] =
            (PositivePulse_Pin << 16U) | NegativePulse_Pin;   /* PB10 LOW,  PB4 HIGH */
    }

    current_number_pulses++;
    return SCPI_RES_OK;
}

scpi_result_t TPT_ClearPulses(scpi_t *context)
{
    (void)context;
    current_number_pulses = 0;
    return SCPI_RES_OK;
}

scpi_result_t TPT_ReadPulses(scpi_t *context)
{
    double aux[TPT_MAXIMUM_NUMBER_PULSES];
    for (size_t i = 0; i < current_number_pulses; i++)
        aux[i] = pulse_periods[i] * minimum_period;
    SCPI_ResultArrayDouble(context, aux, current_number_pulses, 0);
    return SCPI_RES_OK;
}

scpi_result_t TPT_GetMinimumPulse(scpi_t *context)
{
    SCPI_ResultDouble(context, minimum_period);
    return SCPI_RES_OK;
}

scpi_result_t TPT_GetMaximumPulse(scpi_t *context)
{
    SCPI_ResultDouble(context, maximum_period);
    return SCPI_RES_OK;
}

scpi_result_t TPT_SetDeadtime(scpi_t *context)
{
    double dt;
    if (!SCPI_ParamDouble(context, &dt, TRUE))
        return SCPI_RES_ERR;
    deadtime_ns = (uint32_t)(dt * 1e9 + 0.5);
    /* Recompute cycles */
    deadtime_cycles = (uint32_t)((uint64_t)SystemCoreClock * deadtime_ns / 1000000000ULL);
    return SCPI_RES_OK;
}

scpi_result_t TPT_GetDeadtime(scpi_t *context)
{
    SCPI_ResultDouble(context, deadtime_ns * 1e-9);
    return SCPI_RES_OK;
}

/* ── Pulse execution (the hot path) ── */

/*
 * Two separate inner loops:
 *   - Zero-deadtime path: atomic BSRR switching (one write per edge),
 *     no BOTH_OFF step — the pre-computed BSRR value simultaneously
 *     resets the old pin and sets the new one.
 *   - Deadtime path: explicit BOTH_OFF → delay → set active pin.
 *
 * Both paths use __attribute__((optimize("O3"))) to let GCC aggressively
 * optimise the loop (unroll, schedule, use LDM/STM, etc.).
 */

__attribute__((optimize("O3")))
static void run_train_no_deadtime(size_t n,
                                  const uint32_t *bsrr,
                                  const uint32_t *delays)
{
    /* Estimate of per-iteration overhead in DWT cycles.
     * BSRR write (1-2) + array loads (2) + DWT read+compare+branch (4)
     * + loop control (3) ≈ 12 cycles.  Subtract from delay so the
     * *total* half-period matches what the user requested. */
    const uint32_t OVERHEAD = 12;

    for (size_t i = 0; i < n; i++) {
        GPIOB->BSRR = bsrr[i];          /* atomic switch: old pin off + new pin on */

        uint32_t d = delays[i];
        if (d > OVERHEAD) {
            d -= OVERHEAD;
            uint32_t s = DWT->CYCCNT;
            while ((DWT->CYCCNT - s) < d) {}
        }
    }
}

__attribute__((optimize("O3")))
static void run_train_with_deadtime(size_t n,
                                    const uint32_t *bsrr,
                                    const uint32_t *delays,
                                    uint32_t dt_cycles)
{
    const uint32_t OVERHEAD = 18;  /* slightly higher: extra BSRR write + DWT spin */

    for (size_t i = 0; i < n; i++) {
        /* Deadtime: drive both pins LOW (matches H:\OpenTPT.zip logic) */
        GPIOB->BSRR = BOTH_OFF;
        {
            uint32_t s = DWT->CYCCNT;
            while ((DWT->CYCCNT - s) < dt_cycles) {}
        }

        /* Set active pin */
        GPIOB->BSRR = bsrr[i];

        /* Remaining pulse duration */
        uint32_t d = delays[i];
        if (d > (dt_cycles + OVERHEAD)) {
            d -= dt_cycles + OVERHEAD;
            uint32_t s = DWT->CYCCNT;
            while ((DWT->CYCCNT - s) < d) {}
        }
    }
}

scpi_result_t TPT_RunPulses(scpi_t *context)
{
    size_t number_repetitions;
    if (!SCPI_ParamUInt32(context, (uint32_t *)&number_repetitions, TRUE))
        return SCPI_RES_ERR;

    init_dwt();
    reset_pins();
    running = true;

    number_repetitions += run_trains;

    for (; run_trains < number_repetitions; run_trains++) {
        reset_pins();

        __disable_irq();

        if (deadtime_cycles == 0) {
            run_train_no_deadtime(current_number_pulses,
                                  pulse_bsrr, pulse_delay_cycles);
        } else {
            run_train_with_deadtime(current_number_pulses,
                                    pulse_bsrr, pulse_delay_cycles,
                                    deadtime_cycles);
        }

        __enable_irq();
        reset_pins();
    }

    running = false;
    reset_pins();
    return SCPI_RES_OK;
}

scpi_result_t TPT_GetCountPulses(scpi_t *context)
{
    SCPI_ResultUInt32(context, run_trains);
    return SCPI_RES_OK;
}

scpi_result_t TPT_CoreOpcQ(scpi_t *context)
{
    SCPI_ResultInt32(context, running ? 0 : 1);
    return SCPI_RES_OK;
}
