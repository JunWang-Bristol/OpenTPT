#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "scpi/scpi.h"
#include "tpt-scpi.h"

scpi_command_t scpi_commands[] = {
	/* IEEE Mandated Commands (SCPI std V1999.0 4.1.1) */
	{ .pattern = "*CLS", .callback = SCPI_CoreCls,},
	{ .pattern = "*ESE", .callback = SCPI_CoreEse,},
	{ .pattern = "*ESE?", .callback = SCPI_CoreEseQ,},
	{ .pattern = "*ESR?", .callback = SCPI_CoreEsrQ,},
	{ .pattern = "*IDN?", .callback = SCPI_CoreIdnQ,},
	{ .pattern = "*OPC", .callback = SCPI_CoreOpc,},
	{ .pattern = "*OPC?", .callback = SCPI_CoreOpcQ,},
	{ .pattern = "*RST", .callback = SCPI_CoreRst,},
	{ .pattern = "*SRE", .callback = SCPI_CoreSre,},
	{ .pattern = "*SRE?", .callback = SCPI_CoreSreQ,},
	{ .pattern = "*STB?", .callback = SCPI_CoreStbQ,},
	{ .pattern = "*TST?", .callback = SCPI_CoreTstQ,},
	{ .pattern = "*WAI", .callback = SCPI_CoreWai,},

	/* Required SCPI commands (SCPI std V1999.0 4.2.1) */
	{.pattern = "SYSTem:ERRor[:NEXT]?", .callback = SCPI_SystemErrorNextQ,},
	{.pattern = "SYSTem:ERRor:COUNt?", .callback = SCPI_SystemErrorCountQ,},
	{.pattern = "SYSTem:VERSion?", .callback = SCPI_SystemVersionQ,},


    {.pattern = "CONFigure:PULses:ADD", .callback = TPT_AddPulse,},
    {.pattern = "CONFigure:PULses:CLEAR", .callback = TPT_ClearPulses,},
    {.pattern = "CONFigure:PULses?", .callback = TPT_ReadPulses,},
    {.pattern = "CONFigure:PULses:MINimum?", .callback = TPT_GetMinimumPeriod,},
    {.pattern = "CONFigure:PULses:RUN", .callback = TPT_RunPulses,},
    {.pattern = "CONFigure:PULses:COUNT?", .callback = TPT_GetCountPulses,},
	SCPI_CMD_LIST_END
};

scpi_interface_t scpi_interface = {
    .error = SCPI_Error,
    .write = SCPI_Write,
    .control = SCPI_Control,
    .flush = SCPI_Flush,
    .reset = SCPI_Reset,
};

char scpi_input_buffer[SCPI_INPUT_BUFFER_LENGTH];
scpi_error_t scpi_error_queue_data[SCPI_ERROR_QUEUE_SIZE];

scpi_t scpi_context;
uint32_t pulse_periods[TPT_MAXIMUM_NUMBER_PULSES];
size_t current_number_pulses = 0;
size_t count_trains = 0;

size_t SCPI_Write(scpi_t * context, const char * data, size_t len) {
    (void) context;
    return fwrite(data, 1, len, stdout);
}

scpi_result_t SCPI_Flush(scpi_t * context) {
    (void) context;
    return SCPI_RES_OK;
}

int SCPI_Error(scpi_t * context, int_fast16_t err) {
    (void) context;

    fprintf(stderr, "**ERROR: %d, \"%s\"\r\n", (int16_t) err, SCPI_ErrorTranslate(err));
    return 0;
}

scpi_result_t SCPI_Control(scpi_t * context, scpi_ctrl_name_t ctrl, scpi_reg_val_t val) {
    (void) context;

    if (SCPI_CTRL_SRQ == ctrl) {
        fprintf(stderr, "**SRQ: 0x%X (%d)\r\n", val, val);
    } else {
        fprintf(stderr, "**CTRL %02x: 0x%X (%d)\r\n", ctrl, val, val);
    }
    return SCPI_RES_OK;
}

scpi_result_t SCPI_Reset(scpi_t * context) {
    (void) context;

    current_number_pulses = 0;
    count_trains = 0;
    fprintf(stderr, "**Reset\r\n");
    return SCPI_RES_OK;
}

scpi_result_t SCPI_SystemCommTcpipControlQ(scpi_t * context) {
    (void) context;

    return SCPI_RES_ERR;
}


scpi_result_t TPT_AddPulse(scpi_t * context) {
    double period;

    if (!SCPI_ParamDouble(context, &period, TRUE)) {
        return SCPI_RES_ERR;
    }

    pulse_periods[current_number_pulses] = period * 1e6;
    current_number_pulses++;
    return SCPI_RES_OK;
}

scpi_result_t TPT_ClearPulses(scpi_t * context) {
    current_number_pulses = 0;
    return SCPI_RES_OK;
}

scpi_result_t TPT_ReadPulses(scpi_t * context) {
	double aux_pulse_periods[current_number_pulses];
    for (size_t pulse_index=0; pulse_index<current_number_pulses; pulse_index++) {
    	aux_pulse_periods[pulse_index] = pulse_periods[pulse_index] / 1e6;
    }
    SCPI_ResultArrayDouble(context, aux_pulse_periods, current_number_pulses, 0);
    return SCPI_RES_OK;
}

scpi_result_t TPT_GetMinimumPeriod(scpi_t * context) {
	double minimum_period = 1e-6;
    SCPI_ResultDouble(context, minimum_period);
    return SCPI_RES_OK;
}

void delay_half_us (uint16_t us)
{
	__HAL_TIM_SET_COUNTER(&htim2,0);  // set the counter value a 0
	while (__HAL_TIM_GET_COUNTER(&htim2) < us);  // wait for the counter to reach the us input in the parameter
}

scpi_result_t TPT_RunPulses(scpi_t * context) {
    size_t number_repetitions;
    if (!SCPI_ParamUInt32(context, &number_repetitions, TRUE)) {
        return SCPI_RES_ERR;
    }
    else {
    	number_repetitions += count_trains;
        for (count_trains; count_trains<number_repetitions; count_trains++) {
        	__disable_irq();
            for (size_t pulse_index=0; pulse_index<current_number_pulses; pulse_index++) {
        		uint32_t tmp = GPIOB->ODR;
        		GPIOB->BSRR = (tmp << 16) | (~tmp & 0xFFFF);
        		delay_half_us(pulse_periods[pulse_index]);
        		tmp = GPIOB->ODR;
        		GPIOB->BSRR = (tmp << 16) | (~tmp & 0xFFFF);
        		delay_half_us(pulse_periods[pulse_index]);
            }
        	__enable_irq();
        }
    }
    return SCPI_RES_OK;
}

scpi_result_t TPT_GetCountPulses(scpi_t * context) {
	SCPI_ResultUInt32(context, count_trains);
    return SCPI_RES_OK;
}
