/**
  ******************************************************************************
  * @file    pmbus_host.h
  * @brief   PMBus host interface for controlling CoolX600 power supply
  *          This module provides SCPI commands to control the power supply
  *          via PMBus protocol.
  ******************************************************************************
  */

#ifndef __PMBUS_HOST_H
#define __PMBUS_HOST_H

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "stm32_SMBUS_stack.h"
#include "stm32_PMBUS_stack.h"
#include "scpi/scpi.h"

/* Exported defines ----------------------------------------------------------*/

/* PMBus timing values for 100kHz at 250MHz sysclk */
/* Calculated for I2C/SMBUS at 100kHz with analog filter enabled */
#define PMBUS_TIMING_100K              0x40B285C2U    /* 100kHz speed for STM32H5 @ 250MHz */
#define PMBUS_TIMEOUT_DEFAULT          0x80618061U

/* I2C2 pinout on NUCLEO-H503RB (Arduino connector compatible) */
/* PB10 - I2C2_SCL (CN9 pin 7 / D6) */
/* PB11 - I2C2_SDA (CN9 pin 5 / D5) */
#define PMBUS_I2C_INSTANCE             I2C2
#define PMBUS_GPIO_PORT                GPIOB
#define PMBUS_SCL_PIN                  GPIO_PIN_10
#define PMBUS_SDA_PIN                  GPIO_PIN_11
#define PMBUS_GPIO_AF                  GPIO_AF4_I2C2

/* CoolX600 CMD-W0 PMBus default addresses */
/* Page 0x00 = System Controller (address may vary, typically 0x5A-0x5F) */
#define COOLX600_DEFAULT_ADDR          0x5AU

/* Maximum number of PMBus devices we can track */
#define MAX_PMBUS_DEVICES              4

/* Exported types ------------------------------------------------------------*/

/**
 * @brief PMBus device context
 */
typedef struct {
    uint8_t address;           /* 7-bit I2C address */
    uint8_t page;              /* Current PMBus page */
    uint8_t online;            /* Device online flag */
} PMBus_DeviceTypeDef;

/**
 * @brief PMBus host context
 */
typedef struct {
    SMBUS_HandleTypeDef hsmbus;
    SMBUS_StackHandleTypeDef context;
    PMBus_DeviceTypeDef devices[MAX_PMBUS_DEVICES];
    uint8_t device_count;
    uint8_t current_device;
    uint8_t initialized;
} PMBus_HostTypeDef;

/* Exported variables --------------------------------------------------------*/
extern PMBus_HostTypeDef pmbus_host;

/* Exported functions --------------------------------------------------------*/

/* Initialization */
HAL_StatusTypeDef PMBus_Host_Init(void);
HAL_StatusTypeDef PMBus_Host_DeInit(void);

/* Device management */
HAL_StatusTypeDef PMBus_SetAddress(uint8_t address);
uint8_t PMBus_GetAddress(void);
HAL_StatusTypeDef PMBus_SetPage(uint8_t page);
uint8_t PMBus_GetPage(void);

/* Power control */
HAL_StatusTypeDef PMBus_SetOperation(uint8_t operation);
uint8_t PMBus_GetOperation(void);
HAL_StatusTypeDef PMBus_PowerOn(void);
HAL_StatusTypeDef PMBus_PowerOff(void);
HAL_StatusTypeDef PMBus_ClearFaults(void);

/* Voltage control */
HAL_StatusTypeDef PMBus_SetVout(double voltage_v);
double PMBus_GetVout(void);
double PMBus_ReadVout(void);
uint8_t PMBus_GetVoutMode(void);

/* Current reading */
double PMBus_ReadIout(void);

/* Power reading */
double PMBus_ReadPin(void);
double PMBus_ReadPout(void);

/* Temperature reading */
double PMBus_ReadTemperature1(void);
double PMBus_ReadTemperature2(void);

/* Status reading */
uint8_t PMBus_ReadStatusByte(void);
uint16_t PMBus_ReadStatusWord(void);
uint8_t PMBus_ReadStatusVout(void);
uint8_t PMBus_ReadStatusIout(void);
uint8_t PMBus_ReadStatusInput(void);
uint8_t PMBus_ReadStatusTemperature(void);

/* Input voltage reading */
double PMBus_ReadVin(void);
double PMBus_ReadIin(void);

/* Manufacturer info */
HAL_StatusTypeDef PMBus_ReadMfrId(char* buffer, uint8_t max_len);
HAL_StatusTypeDef PMBus_ReadMfrModel(char* buffer, uint8_t max_len);
HAL_StatusTypeDef PMBus_ReadMfrRevision(char* buffer, uint8_t max_len);
HAL_StatusTypeDef PMBus_ReadMfrSerial(char* buffer, uint8_t max_len);

/* Low-level access */
HAL_StatusTypeDef PMBus_WriteByte(uint8_t cmd, uint8_t data);
HAL_StatusTypeDef PMBus_WriteWord(uint8_t cmd, uint16_t data);
HAL_StatusTypeDef PMBus_ReadByteCmd(uint8_t cmd, uint8_t* data);
HAL_StatusTypeDef PMBus_ReadWordCmd(uint8_t cmd, uint16_t* data);
HAL_StatusTypeDef PMBus_ReadBlockCmd(uint8_t cmd, uint8_t* data, uint8_t* len);
HAL_StatusTypeDef PMBus_SendCommand(uint8_t cmd);

/* SCPI command callbacks */
scpi_result_t SCPI_PMBus_Init(scpi_t* context);
scpi_result_t SCPI_PMBus_SetAddress(scpi_t* context);
scpi_result_t SCPI_PMBus_GetAddressQ(scpi_t* context);
scpi_result_t SCPI_PMBus_SetPage(scpi_t* context);
scpi_result_t SCPI_PMBus_GetPageQ(scpi_t* context);

scpi_result_t SCPI_PMBus_PowerOn(scpi_t* context);
scpi_result_t SCPI_PMBus_PowerOff(scpi_t* context);
scpi_result_t SCPI_PMBus_SetOperation(scpi_t* context);
scpi_result_t SCPI_PMBus_GetOperationQ(scpi_t* context);
scpi_result_t SCPI_PMBus_ClearFaults(scpi_t* context);

scpi_result_t SCPI_PMBus_SetVoltage(scpi_t* context);
scpi_result_t SCPI_PMBus_GetVoltageQ(scpi_t* context);
scpi_result_t SCPI_PMBus_MeasureVoltageQ(scpi_t* context);

scpi_result_t SCPI_PMBus_MeasureCurrentQ(scpi_t* context);
scpi_result_t SCPI_PMBus_MeasurePowerQ(scpi_t* context);
scpi_result_t SCPI_PMBus_MeasureTemperatureQ(scpi_t* context);

scpi_result_t SCPI_PMBus_GetStatusByteQ(scpi_t* context);
scpi_result_t SCPI_PMBus_GetStatusWordQ(scpi_t* context);

scpi_result_t SCPI_PMBus_MeasureVinQ(scpi_t* context);
scpi_result_t SCPI_PMBus_MeasureIinQ(scpi_t* context);

scpi_result_t SCPI_PMBus_GetMfrIdQ(scpi_t* context);
scpi_result_t SCPI_PMBus_GetMfrModelQ(scpi_t* context);
scpi_result_t SCPI_PMBus_GetMfrSerialQ(scpi_t* context);

/* Raw register access */
scpi_result_t SCPI_PMBus_WriteReg(scpi_t* context);
scpi_result_t SCPI_PMBus_ReadRegQ(scpi_t* context);

#ifdef __cplusplus
}
#endif

#endif /* __PMBUS_HOST_H */
