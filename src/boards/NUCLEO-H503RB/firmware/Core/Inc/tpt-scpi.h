#ifndef __SCPI_DEF_H_
#define __SCPI_DEF_H_
#ifdef __cplusplus
extern "C" {
#endif

#include "scpi/scpi.h"
#include "main.h"

#define TPT_MAXIMUM_NUMBER_PULSES 256
#define SCPI_INPUT_BUFFER_LENGTH 256
#define SCPI_ERROR_QUEUE_SIZE 17
#define SCPI_IDN1 "OPEN_TPT"
#define SCPI_IDN2 "2402"
#define SCPI_IDN3 "00000000"
#define SCPI_IDN4 "0.0.1"
extern scpi_command_t scpi_commands[];
extern scpi_interface_t scpi_interface;
extern char scpi_input_buffer[];
extern scpi_error_t scpi_error_queue_data[];
extern scpi_t scpi_context;
extern TIM_HandleTypeDef htim2;

size_t SCPI_Write(scpi_t * context, const char * data, size_t len);
int SCPI_Error(scpi_t * context, int_fast16_t err);
scpi_result_t SCPI_Control(scpi_t * context, scpi_ctrl_name_t ctrl, scpi_reg_val_t val);
scpi_result_t SCPI_Reset(scpi_t * context);
scpi_result_t SCPI_Flush(scpi_t * context);

scpi_result_t TPT_AddPulse(scpi_t * context);
scpi_result_t TPT_ClearPulses(scpi_t * context);
scpi_result_t TPT_ReadPulses(scpi_t * context);
scpi_result_t TPT_GetMinimumPulse(scpi_t * context);
scpi_result_t TPT_GetMaximumPulse(scpi_t * context);
scpi_result_t TPT_RunPulses(scpi_t * context);
scpi_result_t TPT_GetCountPulses(scpi_t * context);
scpi_result_t TPT_CoreOpcQ(scpi_t * context);

#ifdef __cplusplus
}
#endif
#endif /* __SCPI_DEF_H_ */
