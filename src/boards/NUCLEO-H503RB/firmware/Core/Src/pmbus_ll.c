/**
  ******************************************************************************
  * @file    pmbus_ll.c
  * @brief   Low-Level PMBus driver implementation using I2C registers directly
  *          This driver uses direct register access for I2C/PMBus communication,
  *          avoiding dependency on HAL SMBUS driver files.
  ******************************************************************************
  */

/* Includes ------------------------------------------------------------------*/
#include "pmbus_ll.h"
#include <string.h>
#include <math.h>

/* Private variables ---------------------------------------------------------*/
static uint8_t pmbus_address = PMBUS_DEFAULT_ADDRESS;
static bool pmbus_initialized = false;
static int8_t cached_vout_mode = -13;  /* Default VOUT_MODE exponent (2^-13) */

/* Private function prototypes -----------------------------------------------*/
static PMBus_StatusTypeDef I2C_WaitFlag(uint32_t flag, uint32_t timeout_ms);
static PMBus_StatusTypeDef I2C_WaitTxEmpty(uint32_t timeout_ms);
static PMBus_StatusTypeDef I2C_WaitRxNotEmpty(uint32_t timeout_ms);
static PMBus_StatusTypeDef I2C_WaitStop(uint32_t timeout_ms);
static double Linear11_ToDouble(uint16_t linear11);
static uint16_t Double_ToLinear11(double value, int8_t exp);
static double Linear16_ToDouble(uint16_t linear16, int8_t vout_mode);
static uint16_t Double_ToLinear16(double value, int8_t vout_mode);

/* Private functions ---------------------------------------------------------*/

/**
 * @brief Wait for I2C flag with timeout
 */
static PMBus_StatusTypeDef I2C_WaitFlag(uint32_t flag, uint32_t timeout_ms)
{
    uint32_t tickstart = HAL_GetTick();
    
    while (!(PMBUS_I2C->ISR & flag)) {
        if ((HAL_GetTick() - tickstart) > timeout_ms) {
            return PMBUS_TIMEOUT;
        }
        /* Check for NACK */
        if (PMBUS_I2C->ISR & I2C_ISR_NACKF) {
            PMBUS_I2C->ICR = I2C_ICR_NACKCF;  /* Clear NACK flag */
            return PMBUS_NACK;
        }
    }
    return PMBUS_OK;
}

/**
 * @brief Wait for TX buffer empty
 */
static PMBus_StatusTypeDef I2C_WaitTxEmpty(uint32_t timeout_ms)
{
    return I2C_WaitFlag(I2C_ISR_TXE, timeout_ms);
}

/**
 * @brief Wait for RX buffer not empty
 */
static PMBus_StatusTypeDef I2C_WaitRxNotEmpty(uint32_t timeout_ms)
{
    return I2C_WaitFlag(I2C_ISR_RXNE, timeout_ms);
}

/**
 * @brief Wait for STOP condition detected
 */
static PMBus_StatusTypeDef I2C_WaitStop(uint32_t timeout_ms)
{
    uint32_t tickstart = HAL_GetTick();
    
    while (!(PMBUS_I2C->ISR & I2C_ISR_STOPF)) {
        if ((HAL_GetTick() - tickstart) > timeout_ms) {
            return PMBUS_TIMEOUT;
        }
    }
    PMBUS_I2C->ICR = I2C_ICR_STOPCF;  /* Clear STOP flag */
    return PMBUS_OK;
}

/**
 * @brief Convert PMBus Linear11 format to double
 */
static double Linear11_ToDouble(uint16_t linear11)
{
    int16_t mantissa;
    int8_t exponent;
    
    /* Extract mantissa (11-bit, signed) */
    mantissa = (int16_t)(linear11 & 0x07FF);
    if (mantissa > 1023) {
        mantissa -= 2048;  /* Sign extend */
    }
    
    /* Extract exponent (5-bit, signed) */
    exponent = (int8_t)((linear11 >> 11) & 0x1F);
    if (exponent > 15) {
        exponent -= 32;  /* Sign extend */
    }
    
    return (double)mantissa * pow(2.0, (double)exponent);
}

/**
 * @brief Convert double to PMBus Linear11 format
 */
static uint16_t Double_ToLinear11(double value, int8_t exp)
{
    int16_t mantissa;
    uint16_t result;
    
    mantissa = (int16_t)(value / pow(2.0, (double)exp));
    
    /* Clamp mantissa to 11-bit signed range */
    if (mantissa > 1023) mantissa = 1023;
    if (mantissa < -1024) mantissa = -1024;
    
    result = (uint16_t)(mantissa & 0x07FF);
    result |= (uint16_t)((exp & 0x1F) << 11);
    
    return result;
}

/**
 * @brief Convert PMBus Linear16 format to double (for VOUT)
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
 */
static uint16_t Double_ToLinear16(double value, int8_t vout_mode)
{
    int8_t exponent = (vout_mode & 0x1F);
    if (exponent > 15) {
        exponent -= 32;  /* Sign extend */
    }
    return (uint16_t)(value / pow(2.0, (double)exponent));
}

/* Exported functions --------------------------------------------------------*/

/**
 * @brief Initialize PMBus (I2C2) interface
 */
PMBus_StatusTypeDef PMBus_LL_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    
    if (pmbus_initialized) {
        return PMBUS_OK;
    }
    
    /* Enable clocks */
    PMBUS_GPIO_CLK_ENABLE();
    PMBUS_I2C_CLK_ENABLE();
    
    /* Configure GPIO pins for I2C2 */
    GPIO_InitStruct.Pin = PMBUS_SCL_PIN | PMBUS_SDA_PIN;
    GPIO_InitStruct.Mode = GPIO_MODE_AF_OD;
    GPIO_InitStruct.Pull = GPIO_NOPULL;  /* External pull-ups required! */
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
    GPIO_InitStruct.Alternate = PMBUS_GPIO_AF;
    HAL_GPIO_Init(PMBUS_GPIO_PORT, &GPIO_InitStruct);
    
    /* Disable I2C for configuration */
    PMBUS_I2C->CR1 &= ~I2C_CR1_PE;
    
    /* Configure I2C timing for 100kHz */
    PMBUS_I2C->TIMINGR = PMBUS_I2C_TIMING;
    
    /* Configure I2C: 
     * - 7-bit addressing mode
     * - No analog filter (can enable if needed)
     * - Auto-end disabled (we control STOP)
     */
    PMBUS_I2C->CR1 = I2C_CR1_PE;  /* Enable I2C */
    PMBUS_I2C->CR2 = 0;  /* Clear CR2 */
    
    pmbus_initialized = true;
    
    return PMBUS_OK;
}

/**
 * @brief Deinitialize PMBus interface
 */
PMBus_StatusTypeDef PMBus_LL_DeInit(void)
{
    if (!pmbus_initialized) {
        return PMBUS_OK;
    }
    
    /* Disable I2C */
    PMBUS_I2C->CR1 &= ~I2C_CR1_PE;
    
    /* Deinit GPIO */
    HAL_GPIO_DeInit(PMBUS_GPIO_PORT, PMBUS_SCL_PIN | PMBUS_SDA_PIN);
    
    /* Disable clock */
    PMBUS_I2C_CLK_DISABLE();
    
    pmbus_initialized = false;
    
    return PMBUS_OK;
}

/**
 * @brief Set the PMBus slave address
 */
void PMBus_LL_SetAddress(uint8_t address)
{
    pmbus_address = address;
}

/**
 * @brief Get the current PMBus slave address
 */
uint8_t PMBus_LL_GetAddress(void)
{
    return pmbus_address;
}

/**
 * @brief Send a command byte (no data) - used for commands like CLEAR_FAULTS
 */
PMBus_StatusTypeDef PMBus_LL_SendByte(uint8_t cmd)
{
    PMBus_StatusTypeDef status;
    
    if (!pmbus_initialized) return PMBUS_ERROR;
    
    /* Configure transfer: 1 byte, AUTOEND */
    PMBUS_I2C->CR2 = ((uint32_t)pmbus_address << 1) |  /* Slave address (write) */
                     (1 << I2C_CR2_NBYTES_Pos) |       /* 1 byte */
                     I2C_CR2_AUTOEND |                 /* Auto generate STOP */
                     I2C_CR2_START;                    /* Generate START */
    
    /* Wait for TX buffer empty */
    status = I2C_WaitTxEmpty(PMBUS_TIMEOUT_MS);
    if (status != PMBUS_OK) return status;
    
    /* Send command byte */
    PMBUS_I2C->TXDR = cmd;
    
    /* Wait for STOP */
    return I2C_WaitStop(PMBUS_TIMEOUT_MS);
}

/**
 * @brief Write a byte to a PMBus register
 */
PMBus_StatusTypeDef PMBus_LL_WriteByte(uint8_t cmd, uint8_t data)
{
    PMBus_StatusTypeDef status;
    
    if (!pmbus_initialized) return PMBUS_ERROR;
    
    /* Configure transfer: 2 bytes, AUTOEND */
    PMBUS_I2C->CR2 = ((uint32_t)pmbus_address << 1) |
                     (2 << I2C_CR2_NBYTES_Pos) |
                     I2C_CR2_AUTOEND |
                     I2C_CR2_START;
    
    /* Send command byte */
    status = I2C_WaitTxEmpty(PMBUS_TIMEOUT_MS);
    if (status != PMBUS_OK) return status;
    PMBUS_I2C->TXDR = cmd;
    
    /* Send data byte */
    status = I2C_WaitTxEmpty(PMBUS_TIMEOUT_MS);
    if (status != PMBUS_OK) return status;
    PMBUS_I2C->TXDR = data;
    
    return I2C_WaitStop(PMBUS_TIMEOUT_MS);
}

/**
 * @brief Write a word (16-bit) to a PMBus register
 */
PMBus_StatusTypeDef PMBus_LL_WriteWord(uint8_t cmd, uint16_t data)
{
    PMBus_StatusTypeDef status;
    
    if (!pmbus_initialized) return PMBUS_ERROR;
    
    /* Configure transfer: 3 bytes, AUTOEND */
    PMBUS_I2C->CR2 = ((uint32_t)pmbus_address << 1) |
                     (3 << I2C_CR2_NBYTES_Pos) |
                     I2C_CR2_AUTOEND |
                     I2C_CR2_START;
    
    /* Send command byte */
    status = I2C_WaitTxEmpty(PMBUS_TIMEOUT_MS);
    if (status != PMBUS_OK) return status;
    PMBUS_I2C->TXDR = cmd;
    
    /* Send low byte */
    status = I2C_WaitTxEmpty(PMBUS_TIMEOUT_MS);
    if (status != PMBUS_OK) return status;
    PMBUS_I2C->TXDR = (uint8_t)(data & 0xFF);
    
    /* Send high byte */
    status = I2C_WaitTxEmpty(PMBUS_TIMEOUT_MS);
    if (status != PMBUS_OK) return status;
    PMBUS_I2C->TXDR = (uint8_t)((data >> 8) & 0xFF);
    
    return I2C_WaitStop(PMBUS_TIMEOUT_MS);
}

/**
 * @brief Read a byte from a PMBus register
 */
PMBus_StatusTypeDef PMBus_LL_ReadByte(uint8_t cmd, uint8_t *data)
{
    PMBus_StatusTypeDef status;
    
    if (!pmbus_initialized || data == NULL) return PMBUS_ERROR;
    
    /* Phase 1: Write command byte (no STOP, will do repeated start) */
    PMBUS_I2C->CR2 = ((uint32_t)pmbus_address << 1) |
                     (1 << I2C_CR2_NBYTES_Pos) |
                     I2C_CR2_START;
    
    status = I2C_WaitTxEmpty(PMBUS_TIMEOUT_MS);
    if (status != PMBUS_OK) return status;
    PMBUS_I2C->TXDR = cmd;
    
    /* Wait for transfer complete */
    status = I2C_WaitFlag(I2C_ISR_TC, PMBUS_TIMEOUT_MS);
    if (status != PMBUS_OK) return status;
    
    /* Phase 2: Read 1 byte with repeated START */
    PMBUS_I2C->CR2 = ((uint32_t)pmbus_address << 1) |
                     I2C_CR2_RD_WRN |                  /* Read mode */
                     (1 << I2C_CR2_NBYTES_Pos) |
                     I2C_CR2_AUTOEND |
                     I2C_CR2_START;
    
    /* Read data */
    status = I2C_WaitRxNotEmpty(PMBUS_TIMEOUT_MS);
    if (status != PMBUS_OK) return status;
    *data = (uint8_t)PMBUS_I2C->RXDR;
    
    return I2C_WaitStop(PMBUS_TIMEOUT_MS);
}

/**
 * @brief Read a word (16-bit) from a PMBus register
 */
PMBus_StatusTypeDef PMBus_LL_ReadWord(uint8_t cmd, uint16_t *data)
{
    PMBus_StatusTypeDef status;
    uint8_t low_byte, high_byte;
    
    if (!pmbus_initialized || data == NULL) return PMBUS_ERROR;
    
    /* Phase 1: Write command byte */
    PMBUS_I2C->CR2 = ((uint32_t)pmbus_address << 1) |
                     (1 << I2C_CR2_NBYTES_Pos) |
                     I2C_CR2_START;
    
    status = I2C_WaitTxEmpty(PMBUS_TIMEOUT_MS);
    if (status != PMBUS_OK) return status;
    PMBUS_I2C->TXDR = cmd;
    
    status = I2C_WaitFlag(I2C_ISR_TC, PMBUS_TIMEOUT_MS);
    if (status != PMBUS_OK) return status;
    
    /* Phase 2: Read 2 bytes with repeated START */
    PMBUS_I2C->CR2 = ((uint32_t)pmbus_address << 1) |
                     I2C_CR2_RD_WRN |
                     (2 << I2C_CR2_NBYTES_Pos) |
                     I2C_CR2_AUTOEND |
                     I2C_CR2_START;
    
    /* Read low byte */
    status = I2C_WaitRxNotEmpty(PMBUS_TIMEOUT_MS);
    if (status != PMBUS_OK) return status;
    low_byte = (uint8_t)PMBUS_I2C->RXDR;
    
    /* Read high byte */
    status = I2C_WaitRxNotEmpty(PMBUS_TIMEOUT_MS);
    if (status != PMBUS_OK) return status;
    high_byte = (uint8_t)PMBUS_I2C->RXDR;
    
    *data = (uint16_t)low_byte | ((uint16_t)high_byte << 8);
    
    return I2C_WaitStop(PMBUS_TIMEOUT_MS);
}

/**
 * @brief Read a block from a PMBus register
 */
PMBus_StatusTypeDef PMBus_LL_ReadBlock(uint8_t cmd, uint8_t *data, uint8_t max_len, uint8_t *actual_len)
{
    PMBus_StatusTypeDef status;
    uint8_t block_len;
    uint8_t i;
    
    if (!pmbus_initialized || data == NULL || actual_len == NULL) return PMBUS_ERROR;
    
    /* Phase 1: Write command byte */
    PMBUS_I2C->CR2 = ((uint32_t)pmbus_address << 1) |
                     (1 << I2C_CR2_NBYTES_Pos) |
                     I2C_CR2_START;
    
    status = I2C_WaitTxEmpty(PMBUS_TIMEOUT_MS);
    if (status != PMBUS_OK) return status;
    PMBUS_I2C->TXDR = cmd;
    
    status = I2C_WaitFlag(I2C_ISR_TC, PMBUS_TIMEOUT_MS);
    if (status != PMBUS_OK) return status;
    
    /* Phase 2: Read first byte (block length) - no AUTOEND yet */
    PMBUS_I2C->CR2 = ((uint32_t)pmbus_address << 1) |
                     I2C_CR2_RD_WRN |
                     (1 << I2C_CR2_NBYTES_Pos) |
                     I2C_CR2_START;
    
    status = I2C_WaitRxNotEmpty(PMBUS_TIMEOUT_MS);
    if (status != PMBUS_OK) return status;
    block_len = (uint8_t)PMBUS_I2C->RXDR;
    
    if (block_len > max_len) block_len = max_len;
    *actual_len = block_len;
    
    /* Wait for transfer complete before reading remaining bytes */
    status = I2C_WaitFlag(I2C_ISR_TC, PMBUS_TIMEOUT_MS);
    if (status != PMBUS_OK) return status;
    
    if (block_len > 0) {
        /* Phase 3: Read remaining bytes with AUTOEND */
        PMBUS_I2C->CR2 = ((uint32_t)pmbus_address << 1) |
                         I2C_CR2_RD_WRN |
                         ((uint32_t)block_len << I2C_CR2_NBYTES_Pos) |
                         I2C_CR2_AUTOEND |
                         I2C_CR2_START;
        
        for (i = 0; i < block_len; i++) {
            status = I2C_WaitRxNotEmpty(PMBUS_TIMEOUT_MS);
            if (status != PMBUS_OK) return status;
            data[i] = (uint8_t)PMBUS_I2C->RXDR;
        }
        
        status = I2C_WaitStop(PMBUS_TIMEOUT_MS);
    } else {
        /* Generate STOP for empty block */
        PMBUS_I2C->CR2 |= I2C_CR2_STOP;
        status = I2C_WaitStop(PMBUS_TIMEOUT_MS);
    }
    
    return status;
}

/* ============ High-Level PMBus Functions ============ */

/**
 * @brief Turn power supply ON (OPERATION = 0x80)
 */
PMBus_StatusTypeDef PMBus_LL_PowerOn(void)
{
    return PMBus_LL_WriteByte(PMBUS_CMD_OPERATION, 0x80);
}

/**
 * @brief Turn power supply OFF (OPERATION = 0x00)
 */
PMBus_StatusTypeDef PMBus_LL_PowerOff(void)
{
    return PMBus_LL_WriteByte(PMBUS_CMD_OPERATION, 0x00);
}

/**
 * @brief Clear all faults
 */
PMBus_StatusTypeDef PMBus_LL_ClearFaults(void)
{
    return PMBus_LL_SendByte(PMBUS_CMD_CLEAR_FAULTS);
}

/**
 * @brief Read VOUT_MODE and update cached exponent
 */
static int8_t PMBus_LL_GetVoutMode(void)
{
    uint8_t vout_mode;
    if (PMBus_LL_ReadByte(PMBUS_CMD_VOUT_MODE, &vout_mode) == PMBUS_OK) {
        cached_vout_mode = (int8_t)(vout_mode & 0x1F);
        if (cached_vout_mode > 15) {
            cached_vout_mode -= 32;
        }
    }
    return cached_vout_mode;
}

/**
 * @brief Set output voltage
 */
PMBus_StatusTypeDef PMBus_LL_SetVout(double voltage)
{
    int8_t vout_mode = PMBus_LL_GetVoutMode();
    uint16_t vout_cmd = Double_ToLinear16(voltage, vout_mode);
    return PMBus_LL_WriteWord(PMBUS_CMD_VOUT_COMMAND, vout_cmd);
}

/**
 * @brief Read actual output voltage
 */
double PMBus_LL_ReadVout(void)
{
    uint16_t vout;
    int8_t vout_mode = PMBus_LL_GetVoutMode();
    
    if (PMBus_LL_ReadWord(PMBUS_CMD_READ_VOUT, &vout) != PMBUS_OK) {
        return 0.0;
    }
    return Linear16_ToDouble(vout, vout_mode);
}

/**
 * @brief Read input voltage
 */
double PMBus_LL_ReadVin(void)
{
    uint16_t vin;
    if (PMBus_LL_ReadWord(PMBUS_CMD_READ_VIN, &vin) != PMBUS_OK) {
        return 0.0;
    }
    return Linear11_ToDouble(vin);
}

/**
 * @brief Read output current
 */
double PMBus_LL_ReadIout(void)
{
    uint16_t iout;
    if (PMBus_LL_ReadWord(PMBUS_CMD_READ_IOUT, &iout) != PMBUS_OK) {
        return 0.0;
    }
    return Linear11_ToDouble(iout);
}

/**
 * @brief Read input current
 */
double PMBus_LL_ReadIin(void)
{
    uint16_t iin;
    if (PMBus_LL_ReadWord(PMBUS_CMD_READ_IIN, &iin) != PMBUS_OK) {
        return 0.0;
    }
    return Linear11_ToDouble(iin);
}

/**
 * @brief Read output power
 */
double PMBus_LL_ReadPout(void)
{
    uint16_t pout;
    if (PMBus_LL_ReadWord(PMBUS_CMD_READ_POUT, &pout) != PMBUS_OK) {
        return 0.0;
    }
    return Linear11_ToDouble(pout);
}

/**
 * @brief Read input power
 */
double PMBus_LL_ReadPin(void)
{
    uint16_t pin;
    if (PMBus_LL_ReadWord(PMBUS_CMD_READ_PIN, &pin) != PMBUS_OK) {
        return 0.0;
    }
    return Linear11_ToDouble(pin);
}

/**
 * @brief Read temperature sensor 1
 */
double PMBus_LL_ReadTemp1(void)
{
    uint16_t temp;
    if (PMBus_LL_ReadWord(PMBUS_CMD_READ_TEMP1, &temp) != PMBUS_OK) {
        return 0.0;
    }
    return Linear11_ToDouble(temp);
}

/**
 * @brief Read temperature sensor 2
 */
double PMBus_LL_ReadTemp2(void)
{
    uint16_t temp;
    if (PMBus_LL_ReadWord(PMBUS_CMD_READ_TEMP2, &temp) != PMBUS_OK) {
        return 0.0;
    }
    return Linear11_ToDouble(temp);
}

/**
 * @brief Read STATUS_BYTE register
 */
uint8_t PMBus_LL_ReadStatusByte(void)
{
    uint8_t status = 0;
    PMBus_LL_ReadByte(PMBUS_CMD_STATUS_BYTE, &status);
    return status;
}

/**
 * @brief Read STATUS_WORD register
 */
uint16_t PMBus_LL_ReadStatusWord(void)
{
    uint16_t status = 0;
    PMBus_LL_ReadWord(PMBUS_CMD_STATUS_WORD, &status);
    return status;
}

/**
 * @brief Read Manufacturer ID
 */
PMBus_StatusTypeDef PMBus_LL_ReadMfrId(char *buffer, uint8_t max_len)
{
    uint8_t len = max_len - 1;
    PMBus_StatusTypeDef status = PMBus_LL_ReadBlock(PMBUS_CMD_MFR_ID, (uint8_t*)buffer, len, &len);
    buffer[len] = '\0';
    return status;
}

/**
 * @brief Read Manufacturer Model
 */
PMBus_StatusTypeDef PMBus_LL_ReadMfrModel(char *buffer, uint8_t max_len)
{
    uint8_t len = max_len - 1;
    PMBus_StatusTypeDef status = PMBus_LL_ReadBlock(PMBUS_CMD_MFR_MODEL, (uint8_t*)buffer, len, &len);
    buffer[len] = '\0';
    return status;
}

/**
 * @brief Read Manufacturer Serial Number
 */
PMBus_StatusTypeDef PMBus_LL_ReadMfrSerial(char *buffer, uint8_t max_len)
{
    uint8_t len = max_len - 1;
    PMBus_StatusTypeDef status = PMBus_LL_ReadBlock(PMBUS_CMD_MFR_SERIAL, (uint8_t*)buffer, len, &len);
    buffer[len] = '\0';
    return status;
}
