#!/bin/bash

echo "Install Built-in TCN for Speech Enhancement  "
cp network.c.se network.c
cp network.h.se network.h
cp stai_network.c.se stai_network.c
cp stai_network.h.se stai_network.h
cp  ../../Dpu/ai_model_config.h.se  ../../Dpu/ai_model_config.h
cp  ../../Dpu/user_mel_tables.c.se  ../../Dpu/user_mel_tables.c
cp  ../../Dpu/user_mel_tables.h.se  ../../Dpu/user_mel_tables.h
