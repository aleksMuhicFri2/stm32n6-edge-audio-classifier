#!/bin/bash

hex="STM32N6570-DK/STM32N6_GettingStarted_Audio_"$1"_"$2".hex"
external_loader="$(dirname "$(which STM32_Programmer_CLI)")/ExternalLoader/MX66UW1G45G_STM32N6570-DK.stldr"

echo "please connect the board and switch BOOT1 to Rigth position"
echo "when done,  press a key to continue ..."
read -n 1 -s
echo "flashing the application "$bin

set -x

STM32_Programmer_CLI -c port=swd mode=HOTPLUG ap=1 --extload $external_loader -w $hex

set +x

echo "please switch BOOT1 to Left position and then power cycle the board"
echo "when done, press a key to continue ..."
read -n 1 -s
echo "Flashing done"
