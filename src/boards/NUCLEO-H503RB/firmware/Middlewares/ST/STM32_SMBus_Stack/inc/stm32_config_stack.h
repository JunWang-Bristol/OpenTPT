/**
  ******************************************************************************
  * @file    stm32_config_stack.h
  * @author  TPT Project
  * @brief   SMBus/PMBus stack configuration for STM32H5 series
  ******************************************************************************
  */

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef __CONFIG_STACK_H
#define __CONFIG_STACK_H

#ifdef __cplusplus
extern "C"
{
#endif

/* Includes ------------------------------------------------------------------*/

/** @addtogroup STM32_SMBUS_STACK     SMBus 2.0 stack implementation
  * @{
  */

/** @defgroup STM32_SMBUS_STACK_Defines SMBus stack configuration
  * @{
  */

/* Device operates as PMBus Host (Master) to control external power supply */
#define HOST1
/*<! The target is a bus host (master). */

#define DENSE_CMD_TABLE
/*<! Setting indicates that the command code does not equal the table index. */

#define PMBUS12
/*<! Features introduced in PMBus v1.2 are included. */

/* Uncomment if using PMBus 1.3 features */
/* #define PMBUS13 */
/*<! Features introduced in PMBus v1.3 are included. */

/* Uncomment to enable PEC (Packet Error Checking) */
/* #define USE_PEC */
/*<! Enable PEC for data integrity */

/* Define for STM32H5 series (only if not already defined by compiler) */
#ifndef STM32H503xx
#define STM32H503xx
#endif

/**
  * @}
  */

/**
  * @}
  */

#ifdef __cplusplus
}
#endif

#endif /* __CONFIG_STACK_H */
