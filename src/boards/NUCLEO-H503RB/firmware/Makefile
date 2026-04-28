######################################################################
# Bare-metal Makefile for TPT SCPI Server (NUCLEO-H503RB)
######################################################################

TARGET = TPT_SCPI_Server
BUILD_DIR = build

# Toolchain — override GCC_PATH if arm-none-eabi-gcc is already on PATH.
GCC_PATH ?= /c/ST/STM32CubeIDE_1.17.0/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.12.3.rel1.win32_1.1.0.202410251130/tools/bin

CC  = "$(GCC_PATH)/arm-none-eabi-gcc"
AS  = "$(GCC_PATH)/arm-none-eabi-gcc" -x assembler-with-cpp
LD  = "$(GCC_PATH)/arm-none-eabi-gcc"
CP  = "$(GCC_PATH)/arm-none-eabi-objcopy"
SZ  = "$(GCC_PATH)/arm-none-eabi-size"

# MCU flags
CPU       = -mcpu=cortex-m33
FPU       = -mfpu=fpv5-sp-d16
FLOAT_ABI = -mfloat-abi=hard
MCU       = $(CPU) -mthumb $(FPU) $(FLOAT_ABI)

######################################################################
# Sources
######################################################################

C_SOURCES = \
  Core/Src/main.c \
  Core/Src/tpt-scpi.c \
  Core/Src/stm32h5xx_it.c \
  Core/Src/syscalls.c \
  Core/Src/sysmem.c \
  Core/Src/system_stm32h5xx.c \
  Middlewares/Third_Party/libscpi/src/error.c \
  Middlewares/Third_Party/libscpi/src/expression.c \
  Middlewares/Third_Party/libscpi/src/fifo.c \
  Middlewares/Third_Party/libscpi/src/ieee488.c \
  Middlewares/Third_Party/libscpi/src/lexer.c \
  Middlewares/Third_Party/libscpi/src/minimal.c \
  Middlewares/Third_Party/libscpi/src/parser.c \
  Middlewares/Third_Party/libscpi/src/units.c \
  Middlewares/Third_Party/libscpi/src/utils.c

ASM_SOURCES = \
  Core/Startup/startup_stm32h503rbtx.s

######################################################################
# Includes & Defines
######################################################################

C_DEFS = \
  -DSTM32H503xx \
  -DHSE_VALUE=24000000U

C_INCLUDES = \
  -ICore/Inc \
  -IDrivers/CMSIS/Device/ST/STM32H5xx/Include \
  -IDrivers/CMSIS/Include \
  -IMiddlewares/Third_Party/libscpi/inc

######################################################################
# Compiler / Linker flags
######################################################################

CFLAGS  = $(MCU) $(C_DEFS) $(C_INCLUDES) -Wall -fdata-sections -ffunction-sections -g3 -O2
ASFLAGS = $(MCU) -g3

LDSCRIPT = STM32H503RBTX_FLASH.ld
LDFLAGS  = $(MCU) -specs=nano.specs -T$(LDSCRIPT) \
           -lc -lm -lnosys \
           -Wl,-Map=$(BUILD_DIR)/$(TARGET).map,--cref \
           -Wl,--gc-sections \
           -u _printf_float

######################################################################
# Build rules
######################################################################

OBJECTS  = $(addprefix $(BUILD_DIR)/,$(notdir $(C_SOURCES:.c=.o)))
vpath %.c $(sort $(dir $(C_SOURCES)))

OBJECTS += $(addprefix $(BUILD_DIR)/,$(notdir $(ASM_SOURCES:.s=.o)))
vpath %.s $(sort $(dir $(ASM_SOURCES)))

all: $(BUILD_DIR)/$(TARGET).elf $(BUILD_DIR)/$(TARGET).hex $(BUILD_DIR)/$(TARGET).bin
	$(SZ) $<

$(BUILD_DIR)/%.o: %.c | $(BUILD_DIR)
	$(CC) -c $(CFLAGS) -MMD -MP -MF"$(@:%.o=%.d)" -o $@ $<

$(BUILD_DIR)/%.o: %.s | $(BUILD_DIR)
	$(AS) -c $(ASFLAGS) -o $@ $<

$(BUILD_DIR)/$(TARGET).elf: $(OBJECTS)
	$(LD) $(OBJECTS) $(LDFLAGS) -o $@

$(BUILD_DIR)/%.hex: $(BUILD_DIR)/%.elf
	$(CP) -O ihex $< $@

$(BUILD_DIR)/%.bin: $(BUILD_DIR)/%.elf
	$(CP) -O binary -S $< $@

$(BUILD_DIR):
	mkdir -p $@

clean:
	rm -rf $(BUILD_DIR)

-include $(wildcard $(BUILD_DIR)/*.d)

.PHONY: all clean
