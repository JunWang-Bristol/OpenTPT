#!/usr/bin/env bash
set -euo pipefail

GCC_PATH="${GCC_PATH:-/c/Users/Alfonso/OpenTPT/arm-toolchain/bin}"
CC="$GCC_PATH/arm-none-eabi-gcc"
CP="$GCC_PATH/arm-none-eabi-objcopy"
SZ="$GCC_PATH/arm-none-eabi-size"

TARGET=TPT_SCPI_Server
BUILD_DIR=build

CPU="-mcpu=cortex-m33"
FPU="-mfpu=fpv5-sp-d16"
FLOAT_ABI="-mfloat-abi=hard"
MCU="$CPU -mthumb $FPU $FLOAT_ABI"

C_SOURCES=(
  Core/Src/main.c
  Core/Src/tpt-scpi.c
  Core/Src/stm32h5xx_it.c
  Core/Src/syscalls.c
  Core/Src/sysmem.c
  Core/Src/system_stm32h5xx.c
  Middlewares/Third_Party/libscpi/src/error.c
  Middlewares/Third_Party/libscpi/src/expression.c
  Middlewares/Third_Party/libscpi/src/fifo.c
  Middlewares/Third_Party/libscpi/src/ieee488.c
  Middlewares/Third_Party/libscpi/src/lexer.c
  Middlewares/Third_Party/libscpi/src/minimal.c
  Middlewares/Third_Party/libscpi/src/parser.c
  Middlewares/Third_Party/libscpi/src/units.c
  Middlewares/Third_Party/libscpi/src/utils.c
)

ASM_SOURCES=( Core/Startup/startup_stm32h503rbtx.s )

C_DEFS="-DSTM32H503xx -DHSE_VALUE=24000000U"
C_INCLUDES="-ICore/Inc -IDrivers/CMSIS/Device/ST/STM32H5xx/Include -IDrivers/CMSIS/Include -IMiddlewares/Third_Party/libscpi/inc"

CFLAGS="$MCU $C_DEFS $C_INCLUDES -Wall -fdata-sections -ffunction-sections -g3 -O2"
ASFLAGS="$MCU -g3"

LDSCRIPT=STM32H503RBTX_FLASH.ld
LDFLAGS="$MCU -specs=nano.specs -T$LDSCRIPT -lc -lm -lnosys -Wl,-Map=$BUILD_DIR/$TARGET.map,--cref -Wl,--gc-sections -u _printf_float"

mkdir -p "$BUILD_DIR"

OBJS=()

for src in "${C_SOURCES[@]}"; do
  base=$(basename "$src" .c)
  obj="$BUILD_DIR/$base.o"
  echo "CC  $src"
  "$CC" -c $CFLAGS -o "$obj" "$src"
  OBJS+=("$obj")
done

for src in "${ASM_SOURCES[@]}"; do
  base=$(basename "$src" .s)
  obj="$BUILD_DIR/$base.o"
  echo "AS  $src"
  "$CC" -x assembler-with-cpp -c $ASFLAGS -o "$obj" "$src"
  OBJS+=("$obj")
done

echo "LD  $BUILD_DIR/$TARGET.elf"
"$CC" "${OBJS[@]}" $LDFLAGS -o "$BUILD_DIR/$TARGET.elf"

echo "CP  $BUILD_DIR/$TARGET.hex"
"$CP" -O ihex "$BUILD_DIR/$TARGET.elf" "$BUILD_DIR/$TARGET.hex"

echo "CP  $BUILD_DIR/$TARGET.bin"
"$CP" -O binary -S "$BUILD_DIR/$TARGET.elf" "$BUILD_DIR/$TARGET.bin"

"$SZ" "$BUILD_DIR/$TARGET.elf"
