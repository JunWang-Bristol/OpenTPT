/**
  ******************************************************************************
  * @file    pmbus_host.c
  * @brief   PMBus host implementation for controlling CoolX600 power supply
  *          This module provides SCPI commands to control the power supply
  *          via PMBus protocol.
  ******************************************************************************
  */

/* Includes ------------------------------------------------------------------*/
#include "pmbus_host.h"
#include <string.h>
#include <stdio.h>
#include <math.h>

/* Private defines -----------------------------------------------------------*/
#define PMBUS_TIMEOUT_MS    100

/* PMBus Linear11 format constants */
#define LINEAR11_MANTISSA_MASK   0x07FF
#define LINEAR11_EXPONENT_MASK   0xF800
#define LINEAR11_EXPONENT_SHIFT  11

/* Private variables ---------------------------------------------------------*/
PMBus_HostTypeDef pmbus_host = {0};

/* Command table for PMBus operations */
static st_command_t pmbus_cmd_read_byte = {
    .cmnd_code = 0x00,
    .cmnd_query = READ,
    .cmnd_master_Tx_size = 1,
    .cmnd_master_Rx_size = 1
};

static st_command_t pmbus_cmd_read_word = {
    .cmnd_code = 0x00,
    .cmnd_query = READ,
    .cmnd_master_Tx_size = 1,
    .cmnd_master_Rx_size = 2
};

static st_command_t pmbus_cmd_write_byte = {
    .cmnd_code = 0x00,
    .cmnd_query = WRITE,
    .cmnd_master_Tx_size = 2,
    .cmnd_master_Rx_size = 0
};

static st_command_t pmbus_cmd_write_word = {
    .cmnd_code = 0x00,
    .cmnd_query = WRITE,
    .cmnd_master_Tx_size = 3,
    .cmnd_master_Rx_size = 0
};

static st_command_t pmbus_cmd_send_byte = {
    .cmnd_code = 0x00,
    .cmnd_query = WRITE,
    .cmnd_master_Tx_size = 1,
    .cmnd_master_Rx_size = 0
};

static st_command_t pmbus_cmd_read_block = {
    .cmnd_code = 0x00,
    .cmnd_query = BLOCK_READ,
    .cmnd_master_Tx_size = 1,
    .cmnd_master_Rx_size = 32  /* Will be adjusted based on block count */
};

/* Private function prototypes -----------------------------------------------*/
static double Linear11_ToDouble(uint16_t linear11);
static uint16_t Double_ToLinear11(double value, int8_t exp);
static double Linear16_ToDouble(uint16_t linear16, int8_t vout_mode);
static uint16_t Double_ToLinear16(double value, int8_t vout_mode);
static HAL_StatusTypeDef PMBus_WaitReady(uint32_t timeout_ms);

/* Private functions ---------------------------------------------------------*/

/**
 * @brief Convert PMBus Linear11 format to double
 * @param linear11 The Linear11 encoded value
 * @return The decoded floating-point value
 */
static double Linear11_ToDouble(uint16_t linear11)
{
    int16_t mantissa;
    int8_t exponent;
    
    /* Extract mantissa (11-bit, signed) */
    mantissa = (int16_t)(linear11 & LINEAR11_MANTISSA_MASK);
    if (mantissa > 1023) {
        mantissa -= 2048;  /* Sign extend */
    }
    
    /* Extract exponent (5-bit, signed) */
    exponent = (int8_t)((linear11 >> LINEAR11_EXPONENT_SHIFT) & 0x1F);
    if (exponent > 15) {
        exponent -= 32;  /* Sign extend */
    }
    
    return (double)mantissa * pow(2.0, (double)exponent);
}

/**
 * @brief Convert double to PMBus Linear11 format
 * @param value The value to encode
 * @param exp The exponent to use (typically -8 to -12 for most values)
 * @return The Linear11 encoded value
 */
static uint16_t Double_ToLinear11(double value, int8_t exp)
{
    int16_t mantissa;
    uint16_t result;
    
    mantissa = (int16_t)(value / pow(2.0, (double)exp));
    
    /* Clamp mantissa to 11-bit signed range */
    if (mantissa > 1023) mantissa = 1023;
    if (mantissa < -1024) mantissa = -1024;
    
    result = (uint16_t)(mantissa & LINEAR11_MANTISSA_MASK);
    result |= (uint16_t)((exp & 0x1F) << LINEAR11_EXPONENT_SHIFT);
    
    return result;
}

/**
 * @brief Convert PMBus Linear16 format to double (for VOUT)
 * @param linear16 The Linear16 encoded value
 * @param vout_mode The VOUT_MODE value (contains exponent)
 * @return The decoded voltage value
 */
static double Linear16_ToDouble(uint16_t linear16, int8_t vout_mode)
{
    int8_t exponent = (vout_mode & 0x1F);
    if (exponent > 15) {
        exponent -= 32;  /* Sign extend */
    }
    return (double)linear16 * pow(2.0, (double)exponent);
}

/**
 * @brief Convert double to PMBus Linear16 format (for VOUT)
 * @param value The voltage value
 * @param vout_mode The VOUT_MODE value (contains exponent)
 * @return The Linear16 encoded value
 */
static uint16_t Double_ToLinear16(double value, int8_t vout_mode)
{
    int8_t exponent = (vout_mode & 0x1F);
    if (exponent > 15) {
        exponent -= 32;  /* Sign extend */
    }
    return (uint16_t)(value / pow(2.0, (double)exponent));
}

/**
 * @brief Wait for PMBus stack to become ready
 */
static HAL_StatusTypeDef PMBus_WaitReady(uint32_t timeout_ms)
{
    uint32_t tickstart = HAL_GetTick();
    
    while (!STACK_SMBUS_IsReady(&pmbus_host.context)) {
        if ((HAL_GetTick() - tickstart) > timeout_ms) {
            return HAL_TIMEOUT;
        }
        
        /* Check for errors */
        if (STACK_SMBUS_IsBlockingError(&pmbus_host.context)) {
            pmbus_host.context.StateMachine &= ~SMBUS_ERROR_CRITICAL;
            return HAL_ERROR;
        }
        if (STACK_SMBUS_IsCmdError(&pmbus_host.context)) {
            pmbus_host.context.StateMachine &= ~SMBUS_COM_ERROR;
            return HAL_ERROR;
        }
    }
    
    return HAL_OK;
}

/* Exported functions --------------------------------------------------------*/

/**
 * @brief Initialize the PMBus host interface
 * @retval HAL_OK on success
 */
HAL_StatusTypeDef PMBus_Host_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    
    if (pmbus_host.initialized) {
        return HAL_OK;  /* Already initialized */
    }
    
    /* Enable GPIO clock */
    __HAL_RCC_GPIOB_CLK_ENABLE();
    
    /* Enable I2C2 clock */
    __HAL_RCC_I2C2_CLK_ENABLE();
    
    /* Configure GPIO pins for I2C2 */
    GPIO_InitStruct.Pin = PMBUS_SCL_PIN | PMBUS_SDA_PIN;
    GPIO_InitStruct.Mode = GPIO_MODE_AF_OD;
    GPIO_InitStruct.Pull = GPIO_NOPULL;  /* External pull-ups required */
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
    GPIO_InitStruct.Alternate = PMBUS_GPIO_AF;
    HAL_GPIO_Init(PMBUS_GPIO_PORT, &GPIO_InitStruct);
    
    /* Configure SMBUS handle */
    pmbus_host.hsmbus.Instance = PMBUS_I2C_INSTANCE;
    pmbus_host.hsmbus.Init.Timing = PMBUS_TIMING_100K;
    pmbus_host.hsmbus.Init.AnalogFilter = SMBUS_ANALOGFILTER_ENABLE;
    pmbus_host.hsmbus.Init.OwnAddress1 = 0x00;  /* Host doesn't need address */
    pmbus_host.hsmbus.Init.AddressingMode = SMBUS_ADDRESSINGMODE_7BIT;
    pmbus_host.hsmbus.Init.DualAddressMode = SMBUS_DUALADDRESS_DISABLE;
    pmbus_host.hsmbus.Init.OwnAddress2 = 0x00;
    pmbus_host.hsmbus.Init.OwnAddress2Masks = SMBUS_OA2_NOMASK;
    pmbus_host.hsmbus.Init.GeneralCallMode = SMBUS_GENERALCALL_DISABLE;
    pmbus_host.hsmbus.Init.NoStretchMode = SMBUS_NOSTRETCH_DISABLE;
    pmbus_host.hsmbus.Init.PacketErrorCheckMode = SMBUS_PEC_DISABLE;
    pmbus_host.hsmbus.Init.PeripheralMode = SMBUS_PERIPHERAL_MODE_SMBUS_HOST;
    pmbus_host.hsmbus.Init.SMBusTimeout = PMBUS_TIMEOUT_DEFAULT;
    pmbus_host.hsmbus.pBuffPtr = pmbus_host.context.Buffer;
    
    if (HAL_SMBUS_Init(&pmbus_host.hsmbus) != HAL_OK) {
        return HAL_ERROR;
    }
    
    /* Configure NVIC for I2C2 */
    HAL_NVIC_SetPriority(I2C2_ER_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(I2C2_ER_IRQn);
    HAL_NVIC_SetPriority(I2C2_EV_IRQn, 1, 1);
    HAL_NVIC_EnableIRQ(I2C2_EV_IRQn);
    
    /* Initialize SMBUS stack context */
    pmbus_host.context.Device = &pmbus_host.hsmbus;
    pmbus_host.context.CMD_table = (st_command_t*)PMBUS_COMMANDS_TAB;
    pmbus_host.context.CMD_tableSize = PMBUS_COMMANDS_TAB_SIZE;
    pmbus_host.context.StateMachine = SMBUS_SMS_NONE;
    pmbus_host.context.OwnAddress = 0x00;
    pmbus_host.context.CurrentCommand = NULL;
    
    if (STACK_SMBUS_Init(&pmbus_host.context) != HAL_OK) {
        return HAL_ERROR;
    }
    
    /* Initialize default device */
    pmbus_host.devices[0].address = COOLX600_DEFAULT_ADDR;
    pmbus_host.devices[0].page = 0;
    pmbus_host.devices[0].online = 0;
    pmbus_host.device_count = 1;
    pmbus_host.current_device = 0;
    pmbus_host.initialized = 1;
    
    return HAL_OK;
}

/**
 * @brief Deinitialize the PMBus host interface
 */
HAL_StatusTypeDef PMBus_Host_DeInit(void)
{
    if (!pmbus_host.initialized) {
        return HAL_OK;
    }
    
    HAL_NVIC_DisableIRQ(I2C2_ER_IRQn);
    HAL_NVIC_DisableIRQ(I2C2_EV_IRQn);
    
    HAL_SMBUS_DeInit(&pmbus_host.hsmbus);
    
    HAL_GPIO_DeInit(PMBUS_GPIO_PORT, PMBUS_SCL_PIN | PMBUS_SDA_PIN);
    
    __HAL_RCC_I2C2_CLK_DISABLE();
    
    pmbus_host.initialized = 0;
    
    return HAL_OK;
}

/**
 * @brief Set the PMBus device address
 */
HAL_StatusTypeDef PMBus_SetAddress(uint8_t address)
{
    if (address > 0x77 || address < 0x08) {
        return HAL_ERROR;  /* Invalid I2C address */
    }
    pmbus_host.devices[pmbus_host.current_device].address = address;
    return HAL_OK;
}

/**
 * @brief Get the current PMBus device address
 */
uint8_t PMBus_GetAddress(void)
{
    return pmbus_host.devices[pmbus_host.current_device].address;
}

/**
 * @brief Set the PMBus page (for multi-rail power supplies)
 */
HAL_StatusTypeDef PMBus_SetPage(uint8_t page)
{
    HAL_StatusTypeDef status = PMBus_WriteByte(PMBC_PAGE, page);
    if (status == HAL_OK) {
        pmbus_host.devices[pmbus_host.current_device].page = page;
    }
    return status;
}

/**
 * @brief Get the current PMBus page
 */
uint8_t PMBus_GetPage(void)
{
    return pmbus_host.devices[pmbus_host.current_device].page;
}

/**
 * @brief Write a byte to a PMBus command register
 */
HAL_StatusTypeDef PMBus_WriteByte(uint8_t cmd, uint8_t data)
{
    uint8_t *piobuf;
    uint16_t address = pmbus_host.devices[pmbus_host.current_device].address;
    
    if (!pmbus_host.initialized) {
        return HAL_ERROR;
    }
    
    piobuf = STACK_SMBUS_GetBuffer(&pmbus_host.context);
    if (piobuf == NULL) {
        return HAL_ERROR;
    }
    
    pmbus_cmd_write_byte.cmnd_code = cmd;
    piobuf[0] = cmd;
    piobuf[1] = data;
    
    STACK_SMBUS_HostCommand(&pmbus_host.context, &pmbus_cmd_write_byte, address, WRITE);
    
    return PMBus_WaitReady(PMBUS_TIMEOUT_MS);
}

/**
 * @brief Write a word to a PMBus command register
 */
HAL_StatusTypeDef PMBus_WriteWord(uint8_t cmd, uint16_t data)
{
    uint8_t *piobuf;
    uint16_t address = pmbus_host.devices[pmbus_host.current_device].address;
    
    if (!pmbus_host.initialized) {
        return HAL_ERROR;
    }
    
    piobuf = STACK_SMBUS_GetBuffer(&pmbus_host.context);
    if (piobuf == NULL) {
        return HAL_ERROR;
    }
    
    pmbus_cmd_write_word.cmnd_code = cmd;
    piobuf[0] = cmd;
    piobuf[1] = (uint8_t)(data & 0xFF);
    piobuf[2] = (uint8_t)((data >> 8) & 0xFF);
    
    STACK_SMBUS_HostCommand(&pmbus_host.context, &pmbus_cmd_write_word, address, WRITE);
    
    return PMBus_WaitReady(PMBUS_TIMEOUT_MS);
}

/**
 * @brief Read a byte from a PMBus command register
 */
HAL_StatusTypeDef PMBus_ReadByteCmd(uint8_t cmd, uint8_t* data)
{
    uint8_t *piobuf;
    HAL_StatusTypeDef status;
    uint16_t address = pmbus_host.devices[pmbus_host.current_device].address;
    
    if (!pmbus_host.initialized || data == NULL) {
        return HAL_ERROR;
    }
    
    piobuf = STACK_SMBUS_GetBuffer(&pmbus_host.context);
    if (piobuf == NULL) {
        return HAL_ERROR;
    }
    
    pmbus_cmd_read_byte.cmnd_code = cmd;
    piobuf[0] = cmd;
    
    STACK_SMBUS_HostCommand(&pmbus_host.context, &pmbus_cmd_read_byte, address, READ);
    
    status = PMBus_WaitReady(PMBUS_TIMEOUT_MS);
    if (status == HAL_OK) {
        *data = piobuf[1];
    }
    
    return status;
}

/**
 * @brief Read a word from a PMBus command register
 */
HAL_StatusTypeDef PMBus_ReadWordCmd(uint8_t cmd, uint16_t* data)
{
    uint8_t *piobuf;
    HAL_StatusTypeDef status;
    uint16_t address = pmbus_host.devices[pmbus_host.current_device].address;
    
    if (!pmbus_host.initialized || data == NULL) {
        return HAL_ERROR;
    }
    
    piobuf = STACK_SMBUS_GetBuffer(&pmbus_host.context);
    if (piobuf == NULL) {
        return HAL_ERROR;
    }
    
    pmbus_cmd_read_word.cmnd_code = cmd;
    piobuf[0] = cmd;
    
    STACK_SMBUS_HostCommand(&pmbus_host.context, &pmbus_cmd_read_word, address, READ);
    
    status = PMBus_WaitReady(PMBUS_TIMEOUT_MS);
    if (status == HAL_OK) {
        *data = (uint16_t)piobuf[1] | ((uint16_t)piobuf[2] << 8);
    }
    
    return status;
}

/**
 * @brief Read a block from a PMBus command register
 */
HAL_StatusTypeDef PMBus_ReadBlockCmd(uint8_t cmd, uint8_t* data, uint8_t* len)
{
    uint8_t *piobuf;
    HAL_StatusTypeDef status;
    uint16_t address = pmbus_host.devices[pmbus_host.current_device].address;
    uint8_t block_len;
    
    if (!pmbus_host.initialized || data == NULL || len == NULL) {
        return HAL_ERROR;
    }
    
    piobuf = STACK_SMBUS_GetBuffer(&pmbus_host.context);
    if (piobuf == NULL) {
        return HAL_ERROR;
    }
    
    pmbus_cmd_read_block.cmnd_code = cmd;
    piobuf[0] = cmd;
    
    STACK_SMBUS_HostCommand(&pmbus_host.context, &pmbus_cmd_read_block, address, READ);
    
    status = PMBus_WaitReady(PMBUS_TIMEOUT_MS);
    if (status == HAL_OK) {
        block_len = piobuf[1];
        if (block_len > *len) {
            block_len = *len;
        }
        memcpy(data, &piobuf[2], block_len);
        *len = block_len;
    }
    
    return status;
}

/**
 * @brief Send a command (no data)
 */
HAL_StatusTypeDef PMBus_SendCommand(uint8_t cmd)
{
    uint8_t *piobuf;
    uint16_t address = pmbus_host.devices[pmbus_host.current_device].address;
    
    if (!pmbus_host.initialized) {
        return HAL_ERROR;
    }
    
    piobuf = STACK_SMBUS_GetBuffer(&pmbus_host.context);
    if (piobuf == NULL) {
        return HAL_ERROR;
    }
    
    pmbus_cmd_send_byte.cmnd_code = cmd;
    piobuf[0] = cmd;
    
    STACK_SMBUS_HostCommand(&pmbus_host.context, &pmbus_cmd_send_byte, address, WRITE);
    
    return PMBus_WaitReady(PMBUS_TIMEOUT_MS);
}

/**
 * @brief Set OPERATION register
 */
HAL_StatusTypeDef PMBus_SetOperation(uint8_t operation)
{
    return PMBus_WriteByte(PMBC_OPERATION, operation);
}

/**
 * @brief Get OPERATION register
 */
uint8_t PMBus_GetOperation(void)
{
    uint8_t operation = 0;
    PMBus_ReadByteCmd(PMBC_OPERATION, &operation);
    return operation;
}

/**
 * @brief Turn power supply output ON
 */
HAL_StatusTypeDef PMBus_PowerOn(void)
{
    /* OPERATION = 0x80: Immediate On */
    return PMBus_SetOperation(0x80);
}

/**
 * @brief Turn power supply output OFF
 */
HAL_StatusTypeDef PMBus_PowerOff(void)
{
    /* OPERATION = 0x00: Immediate Off */
    return PMBus_SetOperation(0x00);
}

/**
 * @brief Clear all faults
 */
HAL_StatusTypeDef PMBus_ClearFaults(void)
{
    return PMBus_SendCommand(PMBC_CLEAR_FAULTS);
}

/**
 * @brief Get VOUT_MODE (contains exponent for Linear16 format)
 */
uint8_t PMBus_GetVoutMode(void)
{
    uint8_t vout_mode = 0;
    PMBus_ReadByteCmd(PMBC_VOUT_MODE, &vout_mode);
    return vout_mode;
}

/**
 * @brief Set output voltage
 */
HAL_StatusTypeDef PMBus_SetVout(double voltage_v)
{
    uint8_t vout_mode = PMBus_GetVoutMode();
    uint16_t vout_cmd = Double_ToLinear16(voltage_v, (int8_t)vout_mode);
    return PMBus_WriteWord(PMBC_VOUNT_COMMAND, vout_cmd);
}

/**
 * @brief Get programmed output voltage
 */
double PMBus_GetVout(void)
{
    uint16_t vout_cmd = 0;
    uint8_t vout_mode = PMBus_GetVoutMode();
    
    if (PMBus_ReadWordCmd(PMBC_VOUNT_COMMAND, &vout_cmd) != HAL_OK) {
        return 0.0;
    }
    
    return Linear16_ToDouble(vout_cmd, (int8_t)vout_mode);
}

/**
 * @brief Read actual output voltage
 */
double PMBus_ReadVout(void)
{
    uint16_t vout = 0;
    uint8_t vout_mode = PMBus_GetVoutMode();
    
    if (PMBus_ReadWordCmd(PMBC_READ_VOUT, &vout) != HAL_OK) {
        return 0.0;
    }
    
    return Linear16_ToDouble(vout, (int8_t)vout_mode);
}

/**
 * @brief Read output current
 */
double PMBus_ReadIout(void)
{
    uint16_t iout = 0;
    
    if (PMBus_ReadWordCmd(PMBC_READ_IOUT, &iout) != HAL_OK) {
        return 0.0;
    }
    
    return Linear11_ToDouble(iout);
}

/**
 * @brief Read input power
 */
double PMBus_ReadPin(void)
{
    uint16_t pin = 0;
    
    if (PMBus_ReadWordCmd(PMBC_READ_PIN, &pin) != HAL_OK) {
        return 0.0;
    }
    
    return Linear11_ToDouble(pin);
}

/**
 * @brief Read output power
 */
double PMBus_ReadPout(void)
{
    uint16_t pout = 0;
    
    if (PMBus_ReadWordCmd(PMBC_READ_POUT, &pout) != HAL_OK) {
        return 0.0;
    }
    
    return Linear11_ToDouble(pout);
}

/**
 * @brief Read temperature sensor 1
 */
double PMBus_ReadTemperature1(void)
{
    uint16_t temp = 0;
    
    if (PMBus_ReadWordCmd(PMBC_READ_TEMPERATURE_1, &temp) != HAL_OK) {
        return 0.0;
    }
    
    return Linear11_ToDouble(temp);
}

/**
 * @brief Read temperature sensor 2
 */
double PMBus_ReadTemperature2(void)
{
    uint16_t temp = 0;
    
    if (PMBus_ReadWordCmd(PMBC_READ_TEMPERATURE_2, &temp) != HAL_OK) {
        return 0.0;
    }
    
    return Linear11_ToDouble(temp);
}

/**
 * @brief Read STATUS_BYTE
 */
uint8_t PMBus_ReadStatusByte(void)
{
    uint8_t status = 0;
    PMBus_ReadByteCmd(PMBC_STATUS_BYTE, &status);
    return status;
}

/**
 * @brief Read STATUS_WORD
 */
uint16_t PMBus_ReadStatusWord(void)
{
    uint16_t status = 0;
    PMBus_ReadWordCmd(PMBC_STATUS_WORD, &status);
    return status;
}

/**
 * @brief Read STATUS_VOUT
 */
uint8_t PMBus_ReadStatusVout(void)
{
    uint8_t status = 0;
    PMBus_ReadByteCmd(PMBC_STATUS_VOUT, &status);
    return status;
}

/**
 * @brief Read STATUS_IOUT
 */
uint8_t PMBus_ReadStatusIout(void)
{
    uint8_t status = 0;
    PMBus_ReadByteCmd(PMBC_STATUS_IOUT, &status);
    return status;
}

/**
 * @brief Read STATUS_INPUT
 */
uint8_t PMBus_ReadStatusInput(void)
{
    uint8_t status = 0;
    PMBus_ReadByteCmd(PMBC_STATUS_INPUT, &status);
    return status;
}

/**
 * @brief Read STATUS_TEMPERATURE
 */
uint8_t PMBus_ReadStatusTemperature(void)
{
    uint8_t status = 0;
    PMBus_ReadByteCmd(PMBC_STATUS_TEMPERATURE, &status);
    return status;
}

/**
 * @brief Read input voltage
 */
double PMBus_ReadVin(void)
{
    uint16_t vin = 0;
    
    if (PMBus_ReadWordCmd(PMBC_READ_VIN, &vin) != HAL_OK) {
        return 0.0;
    }
    
    return Linear11_ToDouble(vin);
}

/**
 * @brief Read input current
 */
double PMBus_ReadIin(void)
{
    uint16_t iin = 0;
    
    if (PMBus_ReadWordCmd(PMBC_READ_IIN, &iin) != HAL_OK) {
        return 0.0;
    }
    
    return Linear11_ToDouble(iin);
}

/**
 * @brief Read Manufacturer ID (block read)
 */
HAL_StatusTypeDef PMBus_ReadMfrId(char* buffer, uint8_t max_len)
{
    uint8_t len = max_len - 1;
    HAL_StatusTypeDef status = PMBus_ReadBlockCmd(PMBC_MFR_ID, (uint8_t*)buffer, &len);
    if (status == HAL_OK) {
        buffer[len] = '\0';
    }
    return status;
}

/**
 * @brief Read Manufacturer Model (block read)
 */
HAL_StatusTypeDef PMBus_ReadMfrModel(char* buffer, uint8_t max_len)
{
    uint8_t len = max_len - 1;
    HAL_StatusTypeDef status = PMBus_ReadBlockCmd(PMBC_MFR_MODEL, (uint8_t*)buffer, &len);
    if (status == HAL_OK) {
        buffer[len] = '\0';
    }
    return status;
}

/**
 * @brief Read Manufacturer Revision (block read)
 */
HAL_StatusTypeDef PMBus_ReadMfrRevision(char* buffer, uint8_t max_len)
{
    uint8_t len = max_len - 1;
    HAL_StatusTypeDef status = PMBus_ReadBlockCmd(PMBC_MFR_REVISION, (uint8_t*)buffer, &len);
    if (status == HAL_OK) {
        buffer[len] = '\0';
    }
    return status;
}

/**
 * @brief Read Manufacturer Serial Number (block read)
 */
HAL_StatusTypeDef PMBus_ReadMfrSerial(char* buffer, uint8_t max_len)
{
    uint8_t len = max_len - 1;
    HAL_StatusTypeDef status = PMBus_ReadBlockCmd(PMBC_MFR_SERIAL, (uint8_t*)buffer, &len);
    if (status == HAL_OK) {
        buffer[len] = '\0';
    }
    return status;
}

/* ========== SCPI Command Callbacks ========== */

/**
 * @brief SCPI: Initialize PMBus interface
 * Pattern: PMBus:INITialize
 */
scpi_result_t SCPI_PMBus_Init(scpi_t* context)
{
    (void)context;
    
    if (PMBus_Host_Init() != HAL_OK) {
        SCPI_ErrorPush(context, SCPI_ERROR_EXECUTION_ERROR);
        return SCPI_RES_ERR;
    }
    
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Set PMBus device address
 * Pattern: PMBus:ADDRess <address>
 */
scpi_result_t SCPI_PMBus_SetAddress(scpi_t* context)
{
    int32_t address;
    
    if (!SCPI_ParamInt32(context, &address, TRUE)) {
        return SCPI_RES_ERR;
    }
    
    if (PMBus_SetAddress((uint8_t)address) != HAL_OK) {
        SCPI_ErrorPush(context, SCPI_ERROR_ILLEGAL_PARAMETER_VALUE);
        return SCPI_RES_ERR;
    }
    
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Query PMBus device address
 * Pattern: PMBus:ADDRess?
 */
scpi_result_t SCPI_PMBus_GetAddressQ(scpi_t* context)
{
    SCPI_ResultInt32(context, PMBus_GetAddress());
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Set PMBus page
 * Pattern: PMBus:PAGE <page>
 */
scpi_result_t SCPI_PMBus_SetPage(scpi_t* context)
{
    int32_t page;
    
    if (!SCPI_ParamInt32(context, &page, TRUE)) {
        return SCPI_RES_ERR;
    }
    
    if (PMBus_SetPage((uint8_t)page) != HAL_OK) {
        SCPI_ErrorPush(context, SCPI_ERROR_EXECUTION_ERROR);
        return SCPI_RES_ERR;
    }
    
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Query PMBus page
 * Pattern: PMBus:PAGE?
 */
scpi_result_t SCPI_PMBus_GetPageQ(scpi_t* context)
{
    SCPI_ResultInt32(context, PMBus_GetPage());
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Turn power supply ON
 * Pattern: OUTPut:STATe ON or OUTPut ON
 */
scpi_result_t SCPI_PMBus_PowerOn(scpi_t* context)
{
    (void)context;
    
    if (PMBus_PowerOn() != HAL_OK) {
        SCPI_ErrorPush(context, SCPI_ERROR_EXECUTION_ERROR);
        return SCPI_RES_ERR;
    }
    
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Turn power supply OFF
 * Pattern: OUTPut:STATe OFF or OUTPut OFF
 */
scpi_result_t SCPI_PMBus_PowerOff(scpi_t* context)
{
    (void)context;
    
    if (PMBus_PowerOff() != HAL_OK) {
        SCPI_ErrorPush(context, SCPI_ERROR_EXECUTION_ERROR);
        return SCPI_RES_ERR;
    }
    
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Set OPERATION register
 * Pattern: PMBus:OPERation <value>
 */
scpi_result_t SCPI_PMBus_SetOperation(scpi_t* context)
{
    int32_t operation;
    
    if (!SCPI_ParamInt32(context, &operation, TRUE)) {
        return SCPI_RES_ERR;
    }
    
    if (PMBus_SetOperation((uint8_t)operation) != HAL_OK) {
        SCPI_ErrorPush(context, SCPI_ERROR_EXECUTION_ERROR);
        return SCPI_RES_ERR;
    }
    
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Query OPERATION register
 * Pattern: PMBus:OPERation?
 */
scpi_result_t SCPI_PMBus_GetOperationQ(scpi_t* context)
{
    SCPI_ResultInt32(context, PMBus_GetOperation());
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Clear faults
 * Pattern: PMBus:CLEar or OUTPut:PROTection:CLEar
 */
scpi_result_t SCPI_PMBus_ClearFaults(scpi_t* context)
{
    (void)context;
    
    if (PMBus_ClearFaults() != HAL_OK) {
        SCPI_ErrorPush(context, SCPI_ERROR_EXECUTION_ERROR);
        return SCPI_RES_ERR;
    }
    
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Set output voltage
 * Pattern: SOURce:VOLTage[:LEVel][:IMMediate] <voltage>
 */
scpi_result_t SCPI_PMBus_SetVoltage(scpi_t* context)
{
    scpi_number_t voltage;
    
    if (!SCPI_ParamNumber(context, scpi_special_numbers_def, &voltage, TRUE)) {
        return SCPI_RES_ERR;
    }
    
    if (voltage.special) {
        SCPI_ErrorPush(context, SCPI_ERROR_ILLEGAL_PARAMETER_VALUE);
        return SCPI_RES_ERR;
    }
    
    /* Convert to volts if necessary */
    double voltage_v = voltage.content.value;
    if (voltage.unit == SCPI_UNIT_VOLT) {
        /* Already in volts */
    } else if (voltage.unit == SCPI_UNIT_NONE) {
        /* Assume volts */
    } else {
        SCPI_ErrorPush(context, SCPI_ERROR_INVALID_SUFFIX);
        return SCPI_RES_ERR;
    }
    
    if (PMBus_SetVout(voltage_v) != HAL_OK) {
        SCPI_ErrorPush(context, SCPI_ERROR_EXECUTION_ERROR);
        return SCPI_RES_ERR;
    }
    
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Query programmed output voltage
 * Pattern: SOURce:VOLTage[:LEVel][:IMMediate]?
 */
scpi_result_t SCPI_PMBus_GetVoltageQ(scpi_t* context)
{
    SCPI_ResultDouble(context, PMBus_GetVout());
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Measure output voltage
 * Pattern: MEASure:VOLTage[:DC]?
 */
scpi_result_t SCPI_PMBus_MeasureVoltageQ(scpi_t* context)
{
    SCPI_ResultDouble(context, PMBus_ReadVout());
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Measure output current
 * Pattern: MEASure:CURRent[:DC]?
 */
scpi_result_t SCPI_PMBus_MeasureCurrentQ(scpi_t* context)
{
    SCPI_ResultDouble(context, PMBus_ReadIout());
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Measure power
 * Pattern: MEASure:POWer[:DC]?
 */
scpi_result_t SCPI_PMBus_MeasurePowerQ(scpi_t* context)
{
    SCPI_ResultDouble(context, PMBus_ReadPout());
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Measure temperature
 * Pattern: MEASure:TEMPerature?
 */
scpi_result_t SCPI_PMBus_MeasureTemperatureQ(scpi_t* context)
{
    SCPI_ResultDouble(context, PMBus_ReadTemperature1());
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Get STATUS_BYTE
 * Pattern: STATus:BYTE?
 */
scpi_result_t SCPI_PMBus_GetStatusByteQ(scpi_t* context)
{
    SCPI_ResultInt32(context, PMBus_ReadStatusByte());
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Get STATUS_WORD
 * Pattern: STATus:WORD?
 */
scpi_result_t SCPI_PMBus_GetStatusWordQ(scpi_t* context)
{
    SCPI_ResultInt32(context, PMBus_ReadStatusWord());
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Measure input voltage
 * Pattern: MEASure:VOLTage:INPut?
 */
scpi_result_t SCPI_PMBus_MeasureVinQ(scpi_t* context)
{
    SCPI_ResultDouble(context, PMBus_ReadVin());
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Measure input current
 * Pattern: MEASure:CURRent:INPut?
 */
scpi_result_t SCPI_PMBus_MeasureIinQ(scpi_t* context)
{
    SCPI_ResultDouble(context, PMBus_ReadIin());
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Get Manufacturer ID
 * Pattern: SYSTem:MFR:ID?
 */
scpi_result_t SCPI_PMBus_GetMfrIdQ(scpi_t* context)
{
    char buffer[32];
    
    if (PMBus_ReadMfrId(buffer, sizeof(buffer)) != HAL_OK) {
        SCPI_ErrorPush(context, SCPI_ERROR_EXECUTION_ERROR);
        return SCPI_RES_ERR;
    }
    
    SCPI_ResultMnemonic(context, buffer);
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Get Manufacturer Model
 * Pattern: SYSTem:MFR:MODel?
 */
scpi_result_t SCPI_PMBus_GetMfrModelQ(scpi_t* context)
{
    char buffer[32];
    
    if (PMBus_ReadMfrModel(buffer, sizeof(buffer)) != HAL_OK) {
        SCPI_ErrorPush(context, SCPI_ERROR_EXECUTION_ERROR);
        return SCPI_RES_ERR;
    }
    
    SCPI_ResultMnemonic(context, buffer);
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Get Manufacturer Serial Number
 * Pattern: SYSTem:MFR:SERial?
 */
scpi_result_t SCPI_PMBus_GetMfrSerialQ(scpi_t* context)
{
    char buffer[32];
    
    if (PMBus_ReadMfrSerial(buffer, sizeof(buffer)) != HAL_OK) {
        SCPI_ErrorPush(context, SCPI_ERROR_EXECUTION_ERROR);
        return SCPI_RES_ERR;
    }
    
    SCPI_ResultMnemonic(context, buffer);
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Write raw PMBus register (byte or word)
 * Pattern: PMBus:REGister <cmd>,<data>[,<size>]
 * size: 1 for byte, 2 for word (default 1)
 */
scpi_result_t SCPI_PMBus_WriteReg(scpi_t* context)
{
    int32_t cmd, data, size = 1;
    
    if (!SCPI_ParamInt32(context, &cmd, TRUE)) {
        return SCPI_RES_ERR;
    }
    
    if (!SCPI_ParamInt32(context, &data, TRUE)) {
        return SCPI_RES_ERR;
    }
    
    /* Optional size parameter */
    SCPI_ParamInt32(context, &size, FALSE);
    
    HAL_StatusTypeDef status;
    if (size == 2) {
        status = PMBus_WriteWord((uint8_t)cmd, (uint16_t)data);
    } else {
        status = PMBus_WriteByte((uint8_t)cmd, (uint8_t)data);
    }
    
    if (status != HAL_OK) {
        SCPI_ErrorPush(context, SCPI_ERROR_EXECUTION_ERROR);
        return SCPI_RES_ERR;
    }
    
    return SCPI_RES_OK;
}

/**
 * @brief SCPI: Read raw PMBus register
 * Pattern: PMBus:REGister? <cmd>[,<size>]
 * size: 1 for byte, 2 for word (default 1)
 */
scpi_result_t SCPI_PMBus_ReadRegQ(scpi_t* context)
{
    int32_t cmd, size = 1;
    
    if (!SCPI_ParamInt32(context, &cmd, TRUE)) {
        return SCPI_RES_ERR;
    }
    
    /* Optional size parameter */
    SCPI_ParamInt32(context, &size, FALSE);
    
    if (size == 2) {
        uint16_t data;
        if (PMBus_ReadWordCmd((uint8_t)cmd, &data) != HAL_OK) {
            SCPI_ErrorPush(context, SCPI_ERROR_EXECUTION_ERROR);
            return SCPI_RES_ERR;
        }
        SCPI_ResultInt32(context, data);
    } else {
        uint8_t data;
        if (PMBus_ReadByteCmd((uint8_t)cmd, &data) != HAL_OK) {
            SCPI_ErrorPush(context, SCPI_ERROR_EXECUTION_ERROR);
            return SCPI_RES_ERR;
        }
        SCPI_ResultInt32(context, data);
    }
    
    return SCPI_RES_OK;
}

/* ========== I2C2 IRQ Handlers ========== */

/**
 * @brief I2C2 Event interrupt handler
 */
void I2C2_EV_IRQHandler(void)
{
    HAL_SMBUS_EV_IRQHandler(&pmbus_host.hsmbus);
}

/**
 * @brief I2C2 Error interrupt handler
 */
void I2C2_ER_IRQHandler(void)
{
    HAL_SMBUS_ER_IRQHandler(&pmbus_host.hsmbus);
}
