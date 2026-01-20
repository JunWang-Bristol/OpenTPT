/**
  ******************************************************************************
  * @file    pmbus_ll.h
  * @brief   Low-Level PMBus driver using I2C registers directly
  *          This driver uses LL (Low-Level) I2C for PMBus communication,
  *          avoiding dependency on HAL_SMBUS driver files.
  ******************************************************************************
  */

#ifndef __PMBUS_LL_H
#define __PMBUS_LL_H

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include <stdint.h>
#include <stdbool.h>

/* Exported defines ----------------------------------------------------------*/

/* I2C2 Configuration for PMBus on NUCLEO-H503RB */
/* PB10 - I2C2_SCL (CN9 pin 7 / D6 on Arduino header) */
/* PB11 - I2C2_SDA (CN9 pin 5 / D5 on Arduino header) */
#define PMBUS_I2C                       I2C2
#define PMBUS_I2C_CLK_ENABLE()          __HAL_RCC_I2C2_CLK_ENABLE()
#define PMBUS_I2C_CLK_DISABLE()         __HAL_RCC_I2C2_CLK_DISABLE()
#define PMBUS_GPIO_PORT                 GPIOB
#define PMBUS_GPIO_CLK_ENABLE()         __HAL_RCC_GPIOB_CLK_ENABLE()
#define PMBUS_SCL_PIN                   GPIO_PIN_10
#define PMBUS_SDA_PIN                   GPIO_PIN_11
#define PMBUS_GPIO_AF                   GPIO_AF4_I2C2

/* I2C timing for 100kHz @ 250MHz PCLK1 */
/* Calculated using STM32CubeMX I2C timing calculator */
#define PMBUS_I2C_TIMING                0x40B285C2U

/* Default CoolX600 PMBus address (may need adjustment per actual device) */
#define PMBUS_DEFAULT_ADDRESS           0x5AU

/* Timeout in milliseconds */
#define PMBUS_TIMEOUT_MS                100

/* Standard PMBus command codes */
#define PMBUS_CMD_PAGE                  0x00
#define PMBUS_CMD_OPERATION             0x01
#define PMBUS_CMD_ON_OFF_CONFIG         0x02
#define PMBUS_CMD_CLEAR_FAULTS          0x03
#define PMBUS_CMD_VOUT_MODE             0x20
#define PMBUS_CMD_VOUT_COMMAND          0x21
#define PMBUS_CMD_VOUT_MAX              0x24
#define PMBUS_CMD_STATUS_BYTE           0x78
#define PMBUS_CMD_STATUS_WORD           0x79
#define PMBUS_CMD_STATUS_VOUT           0x7A
#define PMBUS_CMD_STATUS_IOUT           0x7B
#define PMBUS_CMD_STATUS_INPUT          0x7C
#define PMBUS_CMD_STATUS_TEMP           0x7D
#define PMBUS_CMD_READ_VIN              0x88
#define PMBUS_CMD_READ_IIN              0x89
#define PMBUS_CMD_READ_VOUT             0x8B
#define PMBUS_CMD_READ_IOUT             0x8C
#define PMBUS_CMD_READ_TEMP1            0x8D
#define PMBUS_CMD_READ_TEMP2            0x8E
#define PMBUS_CMD_READ_POUT             0x96
#define PMBUS_CMD_READ_PIN              0x97
#define PMBUS_CMD_MFR_ID                0x99
#define PMBUS_CMD_MFR_MODEL             0x9A
#define PMBUS_CMD_MFR_REVISION          0x9B
#define PMBUS_CMD_MFR_SERIAL            0x9E

/* Exported types ------------------------------------------------------------*/
typedef enum {
    PMBUS_OK = 0,
    PMBUS_ERROR,
    PMBUS_TIMEOUT,
    PMBUS_NACK
} PMBus_StatusTypeDef;

/* Exported functions --------------------------------------------------------*/

/* Initialization */
PMBus_StatusTypeDef PMBus_LL_Init(void);
PMBus_StatusTypeDef PMBus_LL_DeInit(void);

/* Address configuration */
void PMBus_LL_SetAddress(uint8_t address);
uint8_t PMBus_LL_GetAddress(void);

/* Low-level PMBus operations */
PMBus_StatusTypeDef PMBus_LL_SendByte(uint8_t cmd);
PMBus_StatusTypeDef PMBus_LL_WriteByte(uint8_t cmd, uint8_t data);
PMBus_StatusTypeDef PMBus_LL_WriteWord(uint8_t cmd, uint16_t data);
PMBus_StatusTypeDef PMBus_LL_ReadByte(uint8_t cmd, uint8_t *data);
PMBus_StatusTypeDef PMBus_LL_ReadWord(uint8_t cmd, uint16_t *data);
PMBus_StatusTypeDef PMBus_LL_ReadBlock(uint8_t cmd, uint8_t *data, uint8_t max_len, uint8_t *actual_len);

/* Power control */
PMBus_StatusTypeDef PMBus_LL_PowerOn(void);
PMBus_StatusTypeDef PMBus_LL_PowerOff(void);
PMBus_StatusTypeDef PMBus_LL_ClearFaults(void);

/* Voltage control */
PMBus_StatusTypeDef PMBus_LL_SetVout(double voltage);
double PMBus_LL_ReadVout(void);
double PMBus_LL_ReadVin(void);

/* Current reading */
double PMBus_LL_ReadIout(void);
double PMBus_LL_ReadIin(void);

/* Power reading */
double PMBus_LL_ReadPout(void);
double PMBus_LL_ReadPin(void);

/* Temperature reading */
double PMBus_LL_ReadTemp1(void);
double PMBus_LL_ReadTemp2(void);

/* Status reading */
uint8_t PMBus_LL_ReadStatusByte(void);
uint16_t PMBus_LL_ReadStatusWord(void);

/* Manufacturer info */
PMBus_StatusTypeDef PMBus_LL_ReadMfrId(char *buffer, uint8_t max_len);
PMBus_StatusTypeDef PMBus_LL_ReadMfrModel(char *buffer, uint8_t max_len);
PMBus_StatusTypeDef PMBus_LL_ReadMfrSerial(char *buffer, uint8_t max_len);

#ifdef __cplusplus
}
#endif

#endif /* __PMBUS_LL_H */
