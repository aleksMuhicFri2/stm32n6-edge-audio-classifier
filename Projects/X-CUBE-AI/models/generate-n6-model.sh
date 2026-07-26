#!/bin/bash
set -e

generateCmd="${STEDGEAI_EXE:-C:/ST/STEdgeAI/4.0/Utilities/windows/stedgeai.exe}"

if [ ! -f "$generateCmd" ]; then
  echo "STEdgeAI compiler not found: $generateCmd"
  echo "Set STEDGEAI_EXE to the full path of stedgeai.exe."
  return 1 2>/dev/null || exit 1
fi

"$generateCmd" generate -m "$1" --target stm32n6 \
  --st-neural-art default@user_neural_art.json
cp ./st_ai_output/network.c .
cp ./st_ai_output/network.h .
cp ./st_ai_output/stai_network.c .
cp ./st_ai_output/stai_network.h .
cp ./st_ai_output/network_c_info.json .
cp ./st_ai_output/network_generate_report.txt .
cp ./st_ai_output/network_atonbuf.xSPI2.raw network_data.bin
arm-none-eabi-objcopy -I binary network_data.bin --change-addresses 0x70180000 -O ihex network_data.hex
