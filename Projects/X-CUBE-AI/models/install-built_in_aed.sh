#!/bin/bash

echo "Install Built-in Yamnet 1024 for Audio event detection "
cp network.c.aed network.c
cp network.h.aed network.h
cp stai_network.c.aed stai_network.c
cp stai_network.h.aed stai_network.h
cp  ../../Dpu/ai_model_config.h.aed  ../../Dpu/ai_model_config.h
cp  ../../Dpu/user_mel_tables.c.aed  ../../Dpu/user_mel_tables.c
cp  ../../Dpu/user_mel_tables.h.aed  ../../Dpu/user_mel_tables.h
